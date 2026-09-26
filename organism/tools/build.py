#!/usr/bin/env python3
"""Build every view of the organism from its tree of markdown part files.

    python3 tools/build.py           write ORGANISM.md and views/ (and, in the host repository, ../ECOSYSTEM.md)
    python3 tools/build.py --check   rebuild everything in memory; exit 1 if any generated file differs
    python3 tools/build.py --pdf     also print the PDFs in views/ with headless Chrome, when it is installed

Standard library only. The same tree always gives the same bytes.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/kody-w/rapp-work/blob/main/"  # links from the tree into its host repository
MARK = "<!-- GENERATED from organism/ by organism/tools/build.py. Edit the part files and rebuild. -->"
PAGES = {"views/one-page.pdf": 1, "views/lock-in.pdf": 1, "views/rapp-lock-in.pdf": 2}  # printed, with their page counts
WHO = ("you", "engineering", "spec owner", "estate owner")  # who acts on a gap, and who leads a lock-in phase
KINDS = {  # where: (kind, required fields, optional fields)
    "layers": ("layer", "layer name role decides signed_with home health color", "span lines check"),
    "parts": ("part", "name role home health", "layer column beside order span lines check"),
    "crossings": ("crossing", "from to what authorized_by home health arrow label", ""),
    "gaps": ("gap", "id gap home fix status phase who blocks", ""),
    "journeys": ("journey", "id title", ""),
    "invariants.md": ("invariants", "healthy upstream", ""),
    "dogfood.md": ("dogfood", "name health tree loop", ""),
    "health.md": ("health", "name", ""),
    "glossary.md": ("glossary", "name", ""),
    "lock.md": ("lock", "name definition pins cite phases steps", "end"),
    "clean-pull.md": ("pull", "name phase command measured mentions", "door"),
}
LISTS = {"lines", "check", "tree", "loop", "definition", "pins", "phases", "steps", "mentions", "door"}
STATUS = {  # each word of health.md, the first words of every `health` and `status`: (stroke, fill), Open Color
    "in force": ("#2f9e44", "#b2f2bb"), "specified": ("#0c8599", "#c5f6fa"), "experimental": ("#e67700", "#ffe8cc"),
    "candidate": ("#f08c00", "#fff3bf"), "planned": ("#6741d9", "#e5dbff"), "gap": ("#c92a2a", "#ffc9c9"),
    "idea": ("#a61e4d", "#ffdeeb"), "open": ("#868e96", "#e9ecef"), "proposed": ("#3b5bdb", "#dbe4ff"),
    "own shape": ("#495057", "#dee2e6"),
}
FAMILY = {  # layer colors, Open Color families: (stroke, fill)
    "gray": ("#495057", "#e9ecef"), "orange": ("#e67700", "#fff3bf"), "green": ("#2f9e44", "#d3f9d8"),
    "blue": ("#1864ab", "#d0ebff"), "purple": ("#862e9c", "#f3d9fa"),
}
STRIPE = {"gray": "#adb5bd", "orange": "#fcc419", "green": "#69db7c", "blue": "#74c0fc", "purple": "#da77f2"}  # newest
UNSAFE = re.compile(r"""^[][{},#&*!|>'"%@`]|^[-?:] |: | #|:$""")  # plain YAML values cannot hold these


class Refused(Exception):
    """The tree breaks a rule. The message names the file and what to fix."""


def refuse(where, why):
    raise Refused(f"{where}: {why}")


# ---- reading the tree: the Hive agent's tiny frontmatter subset, strictly ----------------------

def scalar(raw, where):
    if raw.startswith('"'):
        if len(raw) < 2 or not raw.endswith('"') or re.search(r'(?<!\\)"', raw[1:-1]):
            refuse(where, 'a quoted value starts and ends with " and writes \\" inside')
        return re.sub(r'\\(["\\])', r"\1", raw[1:-1])
    if UNSAFE.search(raw):
        refuse(where, f"wrap this value in double quotes so the frontmatter stays valid YAML: {raw}")
    return raw


def front(path, where):
    """({field: value or [items]}, body) from the leading --- block."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    end = text.find("\n---\n", 3) if text.startswith("---\n") else -1
    if end < 0:
        refuse(where, "needs a frontmatter block between two --- lines")
    meta, key = {}, None
    for n, line in enumerate(text[4:end].split("\n"), 2):
        name, sep, value = line.partition(":")
        if line.startswith("  - ") and isinstance(meta.get(key), list):
            meta[key].append(scalar(line[4:].strip(), f"{where}:{n}"))
        elif sep and re.fullmatch(r"[a-z][a-z_]*", name) and name not in meta:
            key, meta[name] = name, scalar(value.strip(), f"{where}:{n}") if value.strip() else []
        else:
            refuse(f"{where}:{n}", f"`{name}` appears twice" if sep and name in meta
                   else "expected `field: value`, `field:` or `  - item`")
    return meta, text[end + 5:].strip()


def load(root=ROOT):
    tree = {"root": root.name}
    for place, (kind, need, may) in KINDS.items():
        paths = [root / place] if place.endswith(".md") else sorted((root / place).glob("*.md"))
        if not paths or not paths[0].is_file():
            refuse(f"{root.name}/{place}", "is missing")
        items = []
        for path in paths:
            where = f"{root.name}/{path.relative_to(root).as_posix()}"
            meta, body = front(path, where)
            need_, may_ = set(need.split()), set(may.split())
            if set(meta) - need_ - may_:
                refuse(where, "unknown field(s): " + ", ".join(sorted(set(meta) - need_ - may_)))
            if need_ - set(meta):
                refuse(where, "missing field(s): " + ", ".join(sorted(need_ - set(meta))))
            for field, value in meta.items():
                if field in LISTS and isinstance(value, str):
                    meta[field] = [value]
                elif field not in LISTS and isinstance(value, list):
                    refuse(where, f"`{field}` needs one value on its own line")
                if not meta[field]:
                    refuse(where, f"`{field}` has no items")
            items.append({**meta, "where": where, "stem": path.stem, "body": body})
        tree[kind] = items[0] if place.endswith(".md") else items
    validate(tree)
    return tree


def status(value, where="the tree"):
    """The health word a value starts with, or None for —."""
    if value == "—":
        return None
    for word in sorted(STATUS, key=len, reverse=True):
        if value == word or value.startswith((word + " ", word + ";")):
            return word
    return refuse(where, "`health` and `status` start with one of: " + ", ".join(STATUS) + "; or are —")


def channel(x):
    """The release a layer or part ships in, derived from its health: RAPP/1, the LTS release, exactly when it
    is in force; "outside" for outside knowledge, which keeps its own shape; None for —; else "newest"."""
    word = status(x["health"], x.get("where", "the tree"))
    return None if word is None else {"in force": "RAPP/1", "own shape": "outside"}.get(word, "newest")


def boxes(t):
    """Every layer and part drawn as a box of its own. A layer drawn only as a frame speaks through its parts."""
    return [x for x in t["layer"] if not t["inner"][x["n"]] or x in t["row"][x["n"]]] + t["part"]


def validate(t):
    folder = t["root"]
    for x in t["layer"]:
        m = re.fullmatch(r"(\d)-([a-z0-9]+(?:-[a-z0-9]+)*)", x["stem"])
        if not m or x["layer"] != m[1]:
            refuse(x["where"], "name a layer file <layer>-<id>.md, with <layer> equal to its `layer` field")
        if not re.fullmatch(r"[1-9]", x.get("span", "1")):
            refuse(x["where"], "`span` is a width share from 1 to 9")
        x.update(id=m[2], n=int(m[1]), level=int(m[1]), col=None, span=int(x.get("span", "1")))
        if x["color"] not in FAMILY:
            refuse(x["where"], "`color` is one of: " + ", ".join(FAMILY))
    found = sorted(x["n"] for x in t["layer"])
    if found != list(range(7)):
        refuse(f"{folder}/layers", f"needs exactly one file for each layer 0 to 6; found {found}")
    t["layer"].sort(key=lambda x: x["n"])
    for p in t["part"]:
        side = "column" in p or "beside" in p
        if ("layer" in p) == side or (side and not ("column" in p and "beside" in p)):
            refuse(p["where"], "give either `layer` (a part inside a layer) or `column` with `beside`")
        if side and p["column"] not in ("in", "out", "across"):
            refuse(p["where"], "`column` is in, out or across")
        for field in ("layer", "beside"):
            if field in p and not re.fullmatch(r"[0-6]", p[field]):
                refuse(p["where"], f"`{field}` is a layer number from 0 to 6")
        if not re.fullmatch(r"\d{1,3}", p.get("order", "0")) or not re.fullmatch(r"[1-9]", p.get("span", "1")):
            refuse(p["where"], "`order` is a whole number and `span` a width share from 1 to 9")
        p.update(id=p["stem"], level=int(p.get("layer") or p["beside"]), rank=int(p.get("order", "0")),
                 span=int(p.get("span", "1")),
                 col=("in" if p.get("column") == "in" else "out") if side else None)
    ids = {}
    for x in t["layer"] + t["part"]:
        if x["id"] in ids:
            refuse(x["where"], f"id `{x['id']}` is already used by {ids[x['id']]['where']}")
        ids[x["id"]] = x
    t["ids"] = ids
    t["inner"] = {n: sorted((p for p in t["part"] if p["col"] is None and p["level"] == n),
                            key=lambda p: (p["rank"], p["stem"])) for n in range(7)}
    t["sides"] = sorted((p for p in t["part"] if p["col"]),
                        key=lambda p: (p["col"] != "in", -p["level"], p["rank"], p["stem"]))
    t["row"] = {x["n"]: sorted(t["inner"][x["n"]] + ([x] if t["inner"][x["n"]] and x.get("lines") else []),
                               key=lambda p: channel(p) == "newest")  # RAPP/1 cells first, then the newest lane
                for x in t["layer"]}  # the cells drawn in a layer: its parts, then its own words if it has any
    gaps = set()
    for g in t["gap"]:
        m = re.fullmatch(r"G([1-9][0-9]?)", g["id"])
        if not m or g["stem"] != f"G{int(m[1]):02d}":
            refuse(g["where"], "a gap's `id` is G<number>, in a file named G<two digits>.md (G1 in G01.md)")
        gaps.add(g["id"])
        status(g["status"], g["where"])
        if not re.fullmatch(r"[1-5]", g["phase"]) or g["who"] not in WHO or g["blocks"] not in ids:
            refuse(g["where"], "`phase` is 1 to 5, `who` is one of " + ", ".join(WHO)
                   + ", and `blocks` names the layer or part the gap holds back")
        g["phase"] = int(g["phase"])
    for j in t["journey"]:
        if not re.fullmatch(r"E[1-9][0-9]?", j["id"]) or j["stem"] != j["id"]:
            refuse(j["where"], "a journey's `id` is E<number>, in a file named E<number>.md")
        j["steps"] = [line[2:] for line in j["body"].splitlines() if line.startswith("- ")]
        if not j["steps"]:
            refuse(j["where"], "list the steps in the body as `- ` lines")
    t["journey"].sort(key=lambda j: int(j["id"][1:]))
    lock, by_id, cited = t["lock"], {g["id"]: g for g in t["gap"]}, set()
    lock["plan"] = []
    for k, item in enumerate(lock["phases"], 1):
        title, _, rest = item.partition(": ")
        who, _, note = rest.partition(", ")
        if not title or who not in WHO:
            refuse(lock["where"], "each phase reads `Title: who` or `Title: who, note`, with who one of " + ", ".join(WHO))
        lock["plan"].append(dict(n=k, title=title, who=who, note=note, steps=[],
                                 gaps=[g for g in t["gap"] if g["phase"] == k]))
    if len(lock["plan"]) != 5:
        refuse(lock["where"], "`phases` lists exactly five phases, in order")
    for item in lock["steps"]:
        m = re.fullmatch(r"([1-5]): (.+)", item)
        if not m:
            refuse(lock["where"], "each step reads `<phase, 1 to 5>: words`")
        for ref in re.findall(r"\bG[0-9]+\b", m[2]):
            if ref not in by_id or by_id[ref]["phase"] != int(m[1]):
                refuse(lock["where"], f"a phase {m[1]} step names {ref}, which is no phase {m[1]} gap")
            cited.add(ref)
        lock["plan"][int(m[1]) - 1]["steps"].append(m[2])
    for g in t["gap"]:
        if g["id"] not in cited:
            refuse(g["where"], f"no phase {g['phase']} step in lock.md names {g['id']}; add it to one")
    for ph in lock["plan"]:
        if not ph["steps"]:
            refuse(lock["where"], f"phase {ph['n']} has no step")
    lock["goal"] = None  # where the lock-in ends: one part, and what reaching it means
    if "end" in lock:
        pid, sep, words = lock["end"].partition(": ")
        if not sep or not words or pid not in {p["id"] for p in t["part"]}:
            refuse(lock["where"], "`end` reads `<part id>: words`, and names a part in parts/")
        lock["goal"] = (ids[pid], words)
    pull = t["pull"]
    if not re.fullmatch(r"[1-5]", pull["phase"]) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pull["measured"]):
        refuse(pull["where"], "`phase` is 1 to 5, and `measured` is the date of the count, YYYY-MM-DD")
    pull["phase"], pull["counts"] = int(pull["phase"]), []
    for item in pull["mentions"]:
        m = re.fullmatch(r"(\S+): (\d+)", item)
        if not m:
            refuse(pull["where"], "each `mentions` item reads `<repository>: <files that mention it>`")
        pull["counts"].append((m[1], int(m[2])))
    pull["doors"] = []
    for item in pull.get("door", []):  # the front door: how people find RAPP/1, each item led by its health word
        word, sep, text = item.partition(": ")
        if not sep or word not in STATUS:
            refuse(pull["where"], "each `door` item reads `<health word>: words`, the word one of " + ", ".join(STATUS))
        pull["doors"].append((word, text))
    if not any(pull["name"].lower() in step.lower() for step in lock["plan"][pull["phase"] - 1]["steps"]):
        refuse(pull["where"], f"no phase {pull['phase']} step in lock.md says “{pull['name'].lower()}”; add it to one")
    for x in t["layer"] + t["part"] + t["crossing"] + [t["dogfood"]]:
        status(x["health"], x["where"])
        for ref in re.findall(r"\bG[0-9]+\b", x["health"]):
            if ref not in gaps:
                refuse(x["where"], f"`health` names {ref}, which has no file in gaps/")
    for x in boxes(t):  # RAPP/1 holds only what is in force; everything newest needs a step that graduates it
        if channel(x) == "RAPP/1" and re.search(r"\bexperimental\b", x["health"], re.I):
            refuse(x["where"], "is in force, so it ships in RAPP/1, where nothing is experimental; give the "
                   "experimental piece a part of its own")
        if channel(x) == "newest" and not any(re.search(rf"\b{re.escape(x['name'])}\b", step, re.I)
                                              for step in lock["steps"]):
            refuse(x["where"], f"{x['name']} is not in RAPP/1 yet ({status(x['health'])}); name it in a lock.md "
                   "step that graduates it")
    for kind in ("invariants", "health", "glossary"):
        x = t[kind]
        rules = [re.fullmatch(r"- \*\*(.+?)\*\*\s*(.*)", line) for line in x["body"].splitlines() if line]
        if not rules or not all(rules):
            refuse(x["where"], "write each line of the body as `- **Lead.** More words.`")
        x["rules"] = [(m[1], m[2]) for m in rules]
    words = [lead.rstrip(":") for lead, _ in t["health"]["rules"]]
    if words != list(STATUS):
        refuse(t["health"]["where"], "the health words must be, in order: " + ", ".join(STATUS))
    for field in ("tree", "loop"):
        if not all(": " in item for item in t["dogfood"][field]):
            refuse(t["dogfood"]["where"], f"each `{field}` item reads `name: words`")
    for c in t["crossing"]:
        ends = []
        for field in ("from", "to"):
            if c[field] not in ids:
                refuse(c["where"], f"`{field}` names `{c[field]}`, which is no layer or part here; "
                       "known: " + ", ".join(sorted(ids)))
            ends.append(ids[c[field]])
        sides = [e for e in ends if e["col"]]
        if len(sides) == 2:
            refuse(c["where"], "a crossing touches the stack; it cannot join two parts beside it")
        if sides:
            c.update(side=sides[0], center=ends[1] if sides[0] is ends[0] else ends[0])
            c["top"] = c["bottom"] = c["center"]["level"]
            allowed = ("in", "out", "both")
        else:
            if abs(ends[0]["level"] - ends[1]["level"]) != 1:
                refuse(c["where"], "a crossing inside the stack joins two adjacent layers")
            c["upper"], c["lower"] = sorted(ends, key=lambda e: -e["level"])
            c["top"], c["bottom"] = c["upper"]["level"], c["lower"]["level"]
            allowed = ("down", "up", "both")
        if c["arrow"] not in allowed:
            refuse(c["where"], "`arrow` here is one of: " + ", ".join(allowed))
        one_way = (("down" if ends[0] is c["upper"] else "up") if not sides
                   else ("in" if ends[0] is c["side"] else "out"))
        if c["arrow"] not in ("both", one_way):
            refuse(c["where"], f"`arrow: {c['arrow']}` points against `from` → `to`; use `{one_way}` or `both`")
        c["gap"] = next(iter(re.findall(r"\bG[0-9]+\b", c["health"])), "")
        c["red"], c["dim"] = status(c["health"]) == "gap", status(c["health"]) == "candidate"
    t["crossing"].sort(key=lambda c: (-c["top"], -c["bottom"], c["stem"]))


# ---- words ---------------------------------------------------------------------------------------

def plain(md):
    """Markdown to plain words: links keep their text; code and bold marks drop."""
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md).replace("`", "").replace("**", "")


def smart(text):
    """Typographic quotes and apostrophes, for the drawn views."""
    return re.sub(r'"([^"]*)"', "\u201c\\1\u201d", text).replace("'", "\u2019")


def inline(md):
    """Markdown inline (links, code, bold) to HTML."""
    s = html.escape(smart(re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", md)), quote=False)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s))


def wrap(text, width):  # a " ·" stays with the word before it, when that still fits
    for glued in (text.replace(" \u00b7", "\u00a0\u00b7"), text):
        rows = [r.replace("\u00a0", " ") for r in textwrap.wrap(glued, width, break_long_words=False,
                                                                 break_on_hyphens=False)] or [""]
        if max(map(len, rows)) <= width:
            break
    return rows


def lower1(text):
    return text[0].lower() + text[1:] if text[1:2].islower() else text


def tagline(x):
    """A layer whose role starts with a short phrase and a colon takes that phrase as its title."""
    head, sep, _ = x["role"].partition(": ")
    return lower1(plain(head)) if sep and len(head) <= 40 else ""


def leads(t):
    """The invariants' bold leads, as one running phrase."""
    return [plain(lead).rstrip(".,;:") if k == 0 else lower1(plain(lead).rstrip(".,;:"))
            for k, (lead, _) in enumerate(t["invariants"]["rules"])]


def items(x, width):
    return [row for line in x.get("lines", []) for row in wrap(plain(line), width)]


def joined(x):
    """A box's lines as one run of text: sentences and → steps flow on; other phrases take a ·."""
    out = ""
    for line in (smart(plain(line)) for line in x.get("lines", [])):
        glue = " " if out.endswith((".", "!", "?", "\u201d")) or line.startswith("\u2192") else "\u00a0\u00b7 "
        out += (glue if out else "") + line
    return out


def locks(t):
    """Each layer's lock status: the gaps that hold back it or its parts, then its newest parts that no gap
    covers. Returns {layer: (label, [gap and part ids])}, the label "N to graduate", "in RAPP/1", or
    "nothing to graduate" for a layer with nothing to ship."""
    out = {}
    for x in t["layer"]:
        n = x["n"]
        drawn = ([x] if not t["inner"][n] or x in t["row"][n] else []) + t["inner"][n] + [
            p for p in t["sides"] if p["level"] == n]  # a layer drawn only as a frame speaks through its parts
        gaps = [g for g in t["gap"] if g["blocks"] in {x["id"]} | {p["id"] for p in drawn}]
        named = {g["id"] for g in gaps} | {g["blocks"] for g in gaps}
        loose = [p for p in drawn if channel(p) == "newest"
                 and not ({p["id"], *re.findall(r"\bG[0-9]+\b", p["health"])} & named)]
        items = [g["id"] for g in gaps] + [p["id"] for p in loose]
        out[n] = (f"{len(items)} to graduate" if items else "in RAPP/1" if any(channel(p) == "RAPP/1" for p in drawn)
                  else "nothing to graduate", items)
    return out


def spots(t, n, xs, ranges, mid, step):
    """Where the crossings between layer n and n - 1 are drawn: inside both boxes they join, at a cell's own
    place when one is free, else at another cell's place inside both, else in the middle. The crossing with
    the fewest such places goes first, so every arrow can still land inside both of its boxes."""
    gap = [c for c in t["crossing"] if c.get("upper") and c["top"] == n]
    cells = [p for p in t["row"][n] + t["row"][n - 1] if p["id"] in xs]

    def fits(x, c):
        return all(e["id"] not in ranges or ranges[e["id"]][0] <= x <= ranges[e["id"]][1]
                   for e in (c["upper"], c["lower"]))

    def options(c):
        ends = [e for e in (c["upper"], c["lower"]) if e["id"] in xs]
        out = [(xs[e["id"]], e) for e in ends if fits(xs[e["id"]], c)]
        out += [(xs[p["id"]], ends[0] if ends else None) for p in cells if fits(xs[p["id"]], c)]
        return [q for k, q in enumerate(out) if q[0] not in [o[0] for o in out[:k]]]

    placed = []
    for c in sorted(gap, key=lambda c: (len(options(c)) or len(cells) + 1, c["stem"])):
        free = [q for q in options(c) if all(abs(q[0] - o[0]) >= step for o in placed)]
        x, e = free[0] if free else (options(c) or [(mid, None)])[0]
        while any(abs(x - o[0]) < step for o in placed):
            x += step
        placed.append((x, c, e))
    return sorted(placed, key=lambda q: q[0])


# ---- the text graph ------------------------------------------------------------------------------

def graph_txt(t):
    """99 columns: the stack in the middle, what comes in on the left, what goes out or across on the right."""
    W, LW, C, CW, R = 99, 19, 30, 46, 78
    RW, MID, IN = W - R, C + CW // 2, CW - 4
    grid, cells, spans, avoid, sides, low = [], {}, {}, set(), [], {"in": -2, "out": -2}

    def put(r, c, s):
        while len(grid) <= r:
            grid.append([" "] * W)
        if c + len(s) > W:
            refuse(f"{t['root']}/views/graph.txt", f"`{s.strip()}` runs past column {W}; shorten it")
        grid[r][c:c + len(s)] = s

    def fit(rows, width, x):
        for row in rows:
            if len(row) > width:
                refuse(x["where"], f"`{row}` is wider than its box in the text graph ({width}); shorten it")
        return rows

    def tag(x):
        s = status(x["health"])
        return "" if s is None else "[" + ("exp" if s == "experimental" else s) + "]"

    def foot(x, width):  # a box's last rows: its health tag, and "newest" when it is not in RAPP/1 yet
        s = (tag(x) + (" newest" if channel(x) == "newest" else "")).strip()
        return wrap(s, width) if s else []

    def titled(x, pill, width):  # "n · NAME, tagline  [pill]", or the tagline on a row of its own
        name, line = f"{x['n']} \u00b7 {x['name'].upper()}", tagline(x)
        if line and len(name) + len(line) + len(pill) + 3 <= width:
            name, line = f"{name}, {line}", ""
        return [name.ljust(width - len(pill)) + pill] + (wrap(line, width) if line else [])

    def frame(r, c, w, rows, h):
        put(r, c, "\u250c" + "\u2500" * (w - 2) + "\u2510")
        for i in range(1, h - 1):
            put(r + i, c, "\u2502 " + (rows[i - 1] if i <= len(rows) else "").ljust(w - 4) + " \u2502")
        put(r + h - 1, c, "\u2514" + "\u2500" * (w - 2) + "\u2518")

    for n, inner in t["row"].items():
        if inner:  # cells share the width by `span`, on a grid that lines up across layers
            units = sum(p["span"] for p in inner)
            unit, extra = divmod(CW - 2 - (units - 1), units)
            x = C + 1
            for k, p in enumerate(inner):
                w = unit * p["span"] + p["span"] - 1 + (extra if k == len(inner) - 1 else 0)
                cells[p["id"]] = (x, w)
                x += w + 1
    put(0, 0, "THE RAPP/1 ORGANISM  \u00b7  read it top (6) to bottom (0)")
    r, lock = 2, {n: f"[{label}]" if items or label == "in RAPP/1" else "" for n, (label, items) in locks(t).items()}
    for layer in reversed(t["layer"]):
        n, inner, need = layer["n"], t["row"][layer["n"]], 0
        for sb in sides:  # a part from above that reaches down to this layer ends just inside it
            if sb["open"] == n:
                sb["bottom"], sb["open"] = max(sb["bottom"], r + 2), None
                low[sb["col"]] = max(low[sb["col"]], sb["bottom"])
        for p in (p for p in t["sides"] if p["level"] == n):
            if any(sb["open"] is not None and sb["col"] == p["col"] for sb in sides):
                refuse(p["where"], "sits where a taller part beside it still reaches; move one of them")
            same = bool(sides) and sides[-1]["col"] == p["col"] and sides[-1]["part"]["level"] == n
            top = max(r, low[p["col"]] + (1 if same else 2))
            width = (LW if p["col"] == "in" else RW) - 4
            rows, marks = wrap(p["name"].upper(), width), {}
            if p["col"] == "out":  # no room for words between the stack and the right column: under the name
                for c in (c for c in t["crossing"] if c.get("side") is p):
                    marks[c["stem"]] = len(rows)
                    rows += wrap({"in": "\u25c4 ", "out": "\u25ba ", "both": "\u25c4\u25ba "}[c["arrow"]]
                                 + plain(c["label"]), width)
            rows = fit(rows + items(p, width) + foot(p, width), width, p)
            below = [c["center"]["level"] for c in t["crossing"] if c.get("side") is p and c["top"] < n]
            sides.append(dict(part=p, col=p["col"], top=top, rows=rows, bottom=top + len(rows) + 1, marks=marks,
                              open=min(below) if below else None))
            if not below:
                low[p["col"]] = sides[-1]["bottom"]
            need = max(need, top - r + 3)  # the layer grows until each part beside it overlaps it
        if not inner:
            rows = fit(titled(layer, lock[n], IN) + items(layer, IN) + foot(layer, IN), IN, layer)
            bottom = r + max(len(rows) + 2, need) - 1
            frame(r, C, CW, rows, bottom - r + 1)
        else:
            heads = titled(layer, lock[n], IN)
            cols = [fit(wrap(p["name"].upper(), cells[p["id"]][1] - 2) + items(p, cells[p["id"]][1] - 2)
                        + foot(p, cells[p["id"]][1] - 2), cells[p["id"]][1] - 2, p) for p in inner]
            depth = max([len(col) for col in cols] + [need - len(heads) - 3])
            widths = [cells[p["id"]][1] for p in inner]
            frame(r, C, CW, heads, len(heads) + 2)
            sep = r + len(heads) + 1
            avoid.add(sep)
            put(sep, C, "\u251c" + "\u252c".join("\u2500" * w for w in widths) + "\u2524")
            for i in range(depth):
                put(sep + 1 + i, C, "\u2502" + "\u2502".join(
                    " " + (col[i] if i < len(col) else "").ljust(w - 1) for col, w in zip(cols, widths)) + "\u2502")
            bottom = sep + depth + 1
            put(bottom, C, "\u2514" + "\u2534".join("\u2500" * w for w in widths) + "\u2518")
        for x in [layer, *inner]:
            spans[x["id"]] = (r, bottom)
        r = bottom + 1
        gap = [c for c in t["crossing"] if c.get("upper") and c["top"] == n]
        if n == 0 or not gap:
            r += 0 if n == 0 else 1
            continue
        wide = all(sb["bottom"] < r and sb["open"] is None for sb in sides if sb["col"] == "out")
        placed = spots(t, n, {k: x + 3 for k, (x, w) in cells.items()},  # a cell's arrow sits by its left edge
                       {k: (x, x + w - 1) for k, (x, w) in cells.items()}, MID, 4)
        x, c, end = placed[-1]
        room = (W - 1 if wide else R - 2) - x - 1
        if end and room < 12:  # the last label needs 12 columns: slide its arrow left inside its own cell
            placed[-1] = (max(cells[end["id"]][0] + 1, x - (12 - room)), c, end)
        texts = []
        for k, (x, c, end) in enumerate(placed):
            stop = placed[k + 1][0] - 2 if k + 1 < len(placed) else (W - 1 if wide else R - 2)
            texts.append(fit(wrap(plain(c["label"]), stop - x - 1), stop - x - 1, c))
        depth = max(2, *(len(rows) for rows in texts))
        for (x, c, end), rows in zip(placed, texts):
            line = "\u250a" if c["red"] else "\u254e" if c["dim"] else "\u2502"
            if end is c["upper"]:
                put(r - 1, x, "\u252c")
            for i in range(depth):
                head = (i == 0 and c["arrow"] in ("up", "both")) or (i == depth - 1 and c["arrow"] in ("down", "both"))
                put(r + i, x, ("\u25b2" if i == 0 else "\u25bc") if head else line)
                if i < len(rows):
                    put(r + i, x + 2, rows[i])
        r += depth
    for sb in sides:
        frame(sb["top"], 0 if sb["col"] == "in" else R, LW if sb["col"] == "in" else RW, sb["rows"],
              sb["bottom"] - sb["top"] + 1)
    for c in (c for c in t["crossing"] if c.get("side")):
        sb = next(s for s in sides if s["part"] is c["side"])
        top, bottom = spans[c["center"]["id"]]
        rows = [i for i in range(max(sb["top"], top) + 1, min(sb["bottom"], bottom)) if i not in avoid]
        if not rows:
            refuse(c["where"], "its side part does not sit beside its layer in the text graph; change `beside`")
        left = sb["col"] == "in"
        width = C - LW if left else R - C - CW
        label = plain(c["label"])
        s = list("\u2500" + label + "\u2500" * (width - len(label) - 1) if len(label) + 3 <= width
                 else "\u2500" * width)
        if c["arrow"] == "both" or (c["arrow"] == "in") == left:
            s[-1] = "\u25ba"
        if c["arrow"] == "both" or (c["arrow"] == "in") != left:
            s[0] = "\u25c4"
        row = sb["top"] + 1 + sb["marks"].get(c["stem"], -99)
        row = row if row in rows else rows[(len(rows) - 1) // 2]
        put(row, LW if left else C + CW, "".join(s))
        inner = (LW if left else RW) - 4
        words, x0 = wrap(label, inner), (2 if left else R + 2)
        free = all("".join(grid[i][x0:x0 + inner]).strip() == "" for i in range(row - len(words), row))
        if left and len(label) + 3 > width and free and row - len(words) > sb["top"] and max(map(len, words)) <= inner:
            for i, w in enumerate(words):  # too long for the gap: inside the box, just above the arrow
                put(row - len(words) + i, x0 + (inner - len(w) if left else 0), w)
    r = len(grid) + 1
    used, down = {status(x["health"]) for x in boxes(t)} - {None}, [c for c in t["crossing"] if c.get("upper")]
    put(r, 0, "health: " + " ".join(tag({"health": w}) for w in STATUS if w in used))  # only the marks drawn above
    put(r + 1, 0, "   ".join(filter(None, ("[exp] = experimental" if "experimental" in used else "",
                                          "\u250a gap: no specification allows it" if any(c["red"] for c in down) else "",
                                          "\u254e candidate" if any(c["dim"] for c in down) else "",
                                          "words: health.md"))))
    put(r + 2, 0, "[in force] = RAPP/1 (LTS) \u00b7 newest = not in RAPP/1 yet \u00b7 [N to graduate] = the gaps and parts left")
    return "\n".join("".join(row).rstrip() for row in grid) + "\n"


# ---- the drawing: one layout, drawn as SVG and as Excalidraw -------------------------------------

EM = {c: w for w, cs in ((.222, "ijl'\u2019"), (.278, " tf.,:;!I/[]|\u00b7"), (.333, "r-()\"\u201c\u201d"),
                         (.5, "cksvxyzJ?*"), (.611, "TZF"), (.667, "ABEKPSVXY&"), (.722, "CDHNRUw"), (.778, "GOQ"),
                         (.833, "mM"), (.944, "W"), (1.0, "\u2014\u2192\u2265")) for c in cs}  # Helvetica widths


def em(text):
    return sum(EM.get(c, 0.556) for c in text)


def fitwrap(text, px, size):
    """Greedy word wrap by estimated Helvetica width; a " ·" stays with the word before it."""
    rows = []
    for word in text.replace(" \u00b7", "\u00a0\u00b7").split(" "):
        if rows and em(rows[-1] + " " + word) * size <= px:
            rows[-1] += " " + word
        else:
            rows.append(word)
    return [row.replace("\u00a0", " ") for row in rows] or [""]


def drawing(t):
    """One layout as a list of shapes, which the SVG and the Excalidraw views both draw. Each shape names
    the box it belongs to (`g`), and texts and arrows name what they attach to (`on`, `a`, `b`)."""
    W, TOP, LX, LW, CX, CW, RX, RW, KX = 1840, 160, 30, 300, 470, 760, 1370, 300, 1692  # wide gaps: arrow words
    mid, stack, shapes, span, cells = CX + CW // 2, list(reversed(t["layer"])), [], {}, {}
    frame = {x["n"]: x["id"] + (":frame" if x in t["row"][x["n"]] else "") for x in t["layer"]}

    def rows(x, px):
        return [row for line in x.get("lines", []) for row in fitwrap(smart(plain(line)), px - 24, 13.5)]

    def home(x, px=CW):  # the drawing also names each layer's home
        return [] if x["home"] == "\u2014" else fitwrap(smart(plain("Home: " + x["home"])), px - 24, 13.5)

    def need(x, px):  # the height a box needs for its words
        return 58 + 20 * len(rows(x, px) + (home(x, px) if x in t["layer"] else []))

    def shape(k, g, **kw):
        shapes.append(dict(k=k, g=g, **kw))

    def text(g, x, y, s, size, bold=False, color="#000000", middle=False, on=None):
        shape("text", g, x=round(x), y=round(y), s=s, size=size, bold=bold, color=color, middle=middle, on=on)

    def rect(g, x, y, w, h, stroke, fill, rx=10, dash=False, width=2, id=None, hatch=None, dot=False):
        shape("rect", g, id=id or g, x=x, y=y, w=w, h=h, stroke=stroke, fill=fill, rx=rx, dash=dash, width=width,
              hatch=hatch, dot=dot)

    def line(g, pts, c, a, b):
        shape("line", g, id=g, pts=pts, red=c["red"], dim=c["dim"], both=c["arrow"] == "both", a=a, b=b)

    def box(g, x, y, w, h, s, f, title, lines, tag, num=None, frame=False, hatch=None, neither=False):
        if frame:  # a layer with cells: a thin solid frame around them
            rect(g, x - 8, y - 8, w + 16, h + 16, s, None, 14, width=1.2)
        else:  # in neither release: white, with a dotted edge
            rect(g, x, y, w, h, s, "#ffffff" if neither else f, hatch=hatch, dot=neither)
        span[g] = (y - 8, y + h + 8) if frame else (y, y + h)
        if num is not None:  # a white disc in the layer's color, so the number reads on any fill
            shape("circle", g, id=f"{g}:num", x=x - 23, y=y + 30, r=12, fill="#ffffff", stroke=s)
            text(g, x - 23, y + 35, str(num), 14, True, "#000000", True, on=f"{g}:num")
        if title:
            text(g, x + 14, y + 28, title, 17, True, on=g)
        for i, row in enumerate(lines):
            text(g, x + 14, y + 54 + 20 * i, row, 13.5, on=g)
        if tag:  # top right, or bottom right when the title leaves no room
            tw = round(16 + 7.4 * len(tag))
            ty = y + 10 if em(title) * 17 * 1.08 + tw + 34 <= w else y + h - 32
            rect(g, x + w - tw - 10, ty, tw, 22, *STATUS[tag], 11, width=1, id=f"{g}:tag")
            text(g, x + w - 10 - tw / 2, ty + 15, tag, 12, middle=True, on=f"{g}:tag")

    text("head", 30, 52, "The RAPP/1 organism, top to bottom", 30, True)
    text("head", 30, 84, "Center: the layers, from you (6, top) down to bytes (0, bottom). "
         "Left: what comes in. Right: what goes out or across.", 15)
    for k, word in enumerate(STATUS):  # the legend: every health word, then the two dashed arrows
        x, y = 1190 + 97 * (k % 5), 18 + 30 * (k // 5)
        rect("legend", x, y, 90, 22, *STATUS[word], 11, width=1, id=f"legend:{word}")
        text("legend", x + 45, y + 15, word, 12, middle=True, on=f"legend:{word}")
    for k, (word, why) in enumerate((("gap", "gap: no specification allows it"), ("candidate", "candidate"))):
        x = 1190 + 290 * k
        line(f"legend:{word}:line", [(x, 94), (x + 36, 94)], {"red": k == 0, "dim": k == 1, "arrow": "in"}, None, None)
        text("legend", x + 44, 99, why, 12.5)
    for k, (lane, why) in enumerate((("rapp1", "RAPP/1 (LTS): in force"), ("newest", "newest: not in RAPP/1 yet"),
                                     ("neither", "in neither: you, outside knowledge"))):
        rect("legend", 1190 + 200 * k, 112, 36, 18, FAMILY["gray"][0], "#ffffff" if lane == "neither" else
             FAMILY["gray"][1], 4, width=1.5, id=f"legend:{lane}", hatch=STRIPE["gray"] if lane == "newest" else None,
             dot=lane == "neither")
        text("legend", 1190 + 200 * k + 44, 126, why, 12.5)
    for n, inner in t["row"].items():  # cells share the width by `span`, on a grid that lines up across layers
        units, x = sum(p["span"] for p in inner), CX
        for p in inner:
            w = round((CW - 20 * (units - 1)) / units * p["span"] + 20 * (p["span"] - 1))
            cells[p["id"]], x = (x, w), x + w + 20
    band = {x["n"]: max([118] + [need(p, cells[p["id"]][1]) for p in t["row"][x["n"]]]
                        + ([] if t["row"][x["n"]] else [need(x, CW)])) for x in t["layer"]}
    ys, y, labels = {}, TOP, []
    for layer in stack:  # the bands, and the room each gap needs for its labels
        ys[layer["n"]] = y
        if layer["n"] == 0:
            break
        placed, here = spots(t, layer["n"], {k: x + 50 for k, (x, w) in cells.items()},
                             {k: (x, x + w) for k, (x, w) in cells.items()}, mid, 220), []
        for k, (x, c, end) in enumerate(placed):
            stop = placed[k + 1][0] - 20 if k + 1 < len(placed) else CX + CW + 8
            here.append((x, c, fitwrap(smart(plain(c["label"])), stop - x - 12, 12.5)))
        gap = max([62] + [24 + 17 * (len(words) - 1) + 21 for _, _, words in here])
        labels += [(*q, gap) for q in here]
        y += band[layer["n"]] + gap
    for layer in stack:
        n, (s, f), inner = layer["n"], FAMILY[layer["color"]], t["row"][layer["n"]]
        title = smart(layer["name"] + (f" \u2014 {tagline(layer)}" if tagline(layer) else ""))
        box(frame[n], CX, ys[n], CW, band[n], s, f, "" if inner else title, [] if inner else rows(layer, CW)
            + home(layer), None if inner else status(layer["health"]), n, bool(inner),
            hatch=STRIPE[layer["color"]] if not inner and channel(layer) == "newest" else None,
            neither=not inner and channel(layer) in (None, "outside"))
        for p in inner:
            x, w = cells[p["id"]]
            box(p["id"], x, ys[n], w, band[n], s, f, title if p is layer else smart(p["name"]),
                rows(p, w) + (home(p, w) if p is layer else []), status(p["health"]),
                hatch=STRIPE[layer["color"]] if channel(p) == "newest" else None)
    for n, (label, items) in locks(t).items():  # the lock column: square chips, unlike the round health tags
        ks = "#495057" if items else "#2f9e44" if label == "in RAPP/1" else "#868e96"
        rect("lock", KX, ys[n] + band[n] // 2 - 12, 128, 24, ks, "#ffffff", 4, width=1.5, id=f"lock:{n}",
             dash=not items and label != "in RAPP/1")
        text("lock", KX + 64, ys[n] + band[n] // 2 + 4, label, 12.5, bold=bool(items), middle=True, on=f"lock:{n}")
    text("lock", KX + 64, TOP - 14, "into RAPP/1 (LTS)", 12.5, color="#495057", middle=True)
    for x, c, words, gap in labels:
        up, low = c["upper"]["id"], c["lower"]["id"]
        y1, y2 = span[up][1], span[low][0]
        line(c["stem"], [(x, y2), (x, y1)] if c["arrow"] == "up" else [(x, y1), (x, y2)], c,
             *((low, up) if c["arrow"] == "up" else (up, low)))
        for i, row in enumerate(words):
            text(c["stem"], x + 12, y1 + (gap - 17 * (len(words) - 1)) / 2 + 4 + 17 * i, row, 12.5, on=c["stem"])
    for col, bx, bw in (("in", LX, LW), ("out", RX, RW)):
        prev = -10 ** 6
        for n in range(6, -1, -1):
            group = [p for p in t["sides"] if p["col"] == col and p["level"] == n]
            hs = [58 + 20 * len(rows(p, bw)) for p in group]
            top = max(ys[n] if len(group) < 2 else ys[n] + (band[n] - sum(hs) - 20 * (len(group) - 1)) // 2, prev + 20)
            for p, h in zip(group, hs):
                for c in (c for c in t["crossing"] if c.get("side") is p and c["top"] < n):
                    h = max(h, ys[c["center"]["level"]] + 90 - top)  # reach every layer it crosses to
                box(p["id"], bx, top, bw, h, *FAMILY["gray"], smart(p["name"]), rows(p, bw), status(p["health"]),
                    hatch=STRIPE["gray"] if channel(p) == "newest" else None, neither=channel(p) == "outside")
                prev, top = top + h, top + h + 20
    for c in (c for c in t["crossing"] if c.get("side")):
        left, level = c["side"]["col"] == "in", c["center"]["level"]
        row, target = t["row"][level], c["center"]["id"]
        if row and (c["center"] not in row or c["center"] is not (row[0] if left else row[-1])):
            target = frame[level]  # not a cell at this edge: the arrow meets its layer's frame
        (a, b), (u, v) = span[c["side"]["id"]], span[target]
        lo, hi = max(a, u), min(b, v)
        if hi - lo < 24:
            refuse(c["where"], "its side part does not sit beside its layer in the drawing; change `beside`")
        y = max(lo + 12, hi - 30) if left else (lo + hi) // 2  # on the left, below the layer numbers
        pad = 8 if row else 0  # a layer with cells has a frame 8 outside its band: the arrow starts there
        near, far = (CX - pad, LX + LW) if left else (CX + CW + pad, RX)
        ends = (c["side"]["id"], target) if c["arrow"] == "in" else (target, c["side"]["id"])
        line(c["stem"], [(far, y), (near, y)] if c["arrow"] == "in" else [(near, y), (far, y)], c, *ends)
        a, b = (far + 6, near - 38) if left else (near + 6, far - 6)  # on the left, clear of the layer numbers
        words = fitwrap(smart(plain(c["label"])), b - a, 11)  # the words sit on the arrow
        for i, row_ in enumerate(words):
            text(c["stem"], (a + b) / 2, y - 7 - 13 * (len(words) - 1 - i), row_, 11, color="#495057",
                 middle=True, on=c["stem"])
    foot = max(b for _, b in span.values()) + 40
    text("foot", 30, foot, "Drawn from the organism/ tree by tools/build.py \u00b7 the tree is the source; this "
         "picture is a view \u00b7 health words: health.md \u00b7 experimental", 12.5, color="#495057")
    return dict(W=W, H=foot + 30, shapes=shapes)


def svg(d):
    e, W, H = html.escape, d["W"], d["H"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'font-family="Helvetica, Arial, sans-serif">', "<defs>"]
    o += [f'<marker id="{m}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
          f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
          for m, c in (("ah", "#343a40"), ("ahr", "#c92a2a"), ("ahg", "#868e96"))]
    hatches = sorted({(s["fill"], s["hatch"]) for s in d["shapes"] if s["k"] == "rect" and s["hatch"]})
    o += [f'<pattern id="h{f[1:]}{h[1:]}" width="9" height="9" patternUnits="userSpaceOnUse" '
          f'patternTransform="rotate(45)"><rect width="9" height="9" fill="{f}"/><rect width="2.5" height="9" '
          f'fill="{h}"/></pattern>' for f, h in hatches]  # newest: the box's fill, striped
    o += ["</defs>", f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
    for s in d["shapes"]:
        if s["k"] == "rect":
            dash = ' stroke-dasharray="6 4"' if s["dash"] else ""
            fill = f'url(#h{s["fill"][1:]}{s["hatch"][1:]})' if s["hatch"] else s["fill"] or "none"
            dash = ' stroke-dasharray="2 3"' if s["dot"] else dash
            o.append(f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="{s["rx"]}" '
                     f'fill="{fill}" stroke="{s["stroke"]}" stroke-width="{s["width"]}"{dash}/>')
        elif s["k"] == "circle":
            o.append(f'<circle cx="{s["x"]}" cy="{s["y"]}" r="{s["r"]}" fill="{s["fill"]}" stroke="{s["stroke"]}" '
                     'stroke-width="2.5"/>')
        elif s["k"] == "text":
            more = (' font-weight="700"' if s["bold"] else "") + (' text-anchor="middle"' if s["middle"] else "")
            more += f' fill="{s["color"]}"' if s["color"] != "#000000" else ""
            o.append(f'<text x="{s["x"]}" y="{s["y"]}" font-size="{s["size"]}"{more}>{e(s["s"])}</text>')
        else:
            (x1, y1), (x2, y2) = s["pts"]
            color, m, dash = (("#c92a2a", "ahr", "8 6") if s["red"] else ("#868e96", "ahg", "5 5") if s["dim"]
                              else ("#343a40", "ah", ""))
            more = (f' stroke-dasharray="{dash}"' if dash else "") + (f' marker-start="url(#{m})"' if s["both"] else "")
            o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5"{more} '
                     f'marker-end="url(#{m})"/>')
    return "\n".join(o + ["</svg>"]) + "\n"


def excalidraw(d):
    """The same shapes as Excalidraw elements. Words are bound to their box or arrow (`containerId`), arrows to
    the boxes they join (`startBinding`, `endBinding`), and each box is grouped with its tag and number."""
    els, index, texts = [], {}, {}
    for sh in d["shapes"]:
        if sh["k"] == "text" and sh["on"]:
            texts.setdefault(sh["on"], []).append(sh)

    def add(kind, sh, x, y, w, h, **kw):
        n = len(els) + 1
        el = {"id": sh.get("id") or f"{sh['g']}:{n}", "type": kind, "x": x, "y": y, "width": w, "height": h,
              "angle": 0, "strokeColor": "#000000", "backgroundColor": "transparent", "fillStyle": "solid",
              "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [sh["g"]],
              "frameId": None, "roundness": None, "seed": n, "version": 1, "versionNonce": n, "isDeleted": False,
              "boundElements": [], "updated": 1, "link": None, "locked": False, **kw}
        els.append(el)
        index[el["id"]] = el
        return el

    def words(sh, owner, x, y, w, h, **kw):  # one text element: free, or bound to its owner
        text = "\n".join(part["s"] for part in texts.get(owner["id"], [])) if owner else sh["s"]
        size = texts[owner["id"]][-1]["size"] if owner else sh["size"]
        color = texts[owner["id"]][0]["color"] if owner else sh["color"]
        el = add("text", {"g": sh["g"]}, x, y, w, round(size * 1.25 * (text.count("\n") + 1)), text=text,
                 originalText=text, fontSize=size, fontFamily=2, containerId=owner["id"] if owner else None,
                 lineHeight=1.25, autoResize=True, strokeWidth=1, strokeColor=color, **kw)
        if owner:
            owner["boundElements"].append({"id": el["id"], "type": "text"})

    for sh in d["shapes"]:
        if sh["k"] == "rect":
            el = add("rectangle", sh, sh["x"], sh["y"], sh["w"], sh["h"], strokeColor=sh["stroke"],
                     strokeWidth=sh["width"], backgroundColor=sh["hatch"] or sh["fill"] or "transparent",
                     fillStyle="hachure" if sh["hatch"] else "solid",  # newest: striped
                     strokeStyle="dotted" if sh["dot"] else "dashed" if sh["dash"] else "solid", roundness={"type": 3})
            if sh["id"] in texts:
                small = texts[sh["id"]][0]["middle"]
                words(sh, el, sh["x"] + 5, sh["y"] + 5, sh["w"] - 10, sh["h"] - 10, textAlign="center" if small
                      else "left", verticalAlign="middle" if small else "top")
        elif sh["k"] == "circle":
            el = add("ellipse", sh, sh["x"] - sh["r"], sh["y"] - sh["r"], 2 * sh["r"], 2 * sh["r"],
                     strokeColor=sh["stroke"], backgroundColor=sh["fill"])
            words(sh, el, el["x"] + 4, el["y"] + 4, el["width"] - 8, el["height"] - 8, textAlign="center",
                  verticalAlign="middle")
        elif sh["k"] == "text" and not sh["on"]:
            w = round(em(sh["s"]) * sh["size"] * (1.08 if sh["bold"] else 1)) + 10
            words(sh, None, sh["x"] - w // 2 if sh["middle"] else sh["x"], round(sh["y"] - sh["size"]), w, 0,
                  textAlign="center" if sh["middle"] else "left", verticalAlign="top")
    for sh in (sh for sh in d["shapes"] if sh["k"] == "line"):
        (x1, y1), (x2, y2) = sh["pts"]
        el = add("arrow", sh, x1, y1, x2 - x1, y2 - y1, points=[[0, 0], [x2 - x1, y2 - y1]],
                 strokeColor="#c92a2a" if sh["red"] else "#868e96" if sh["dim"] else "#343a40",
                 strokeStyle="dashed" if sh["red"] or sh["dim"] else "solid", lastCommittedPoint=None,
                 startBinding=None, endBinding=None, startArrowhead="arrow" if sh["both"] else None,
                 endArrowhead="arrow", elbowed=False)
        for end, key in ((sh["a"], "startBinding"), (sh["b"], "endBinding")):
            if end:
                el[key] = {"elementId": end, "focus": 0, "gap": 1}
                index[end]["boundElements"].append({"id": el["id"], "type": "arrow"})
        if sh["id"] in texts:
            n = len(texts[sh["id"]])
            w = round(max(em(part["s"]) for part in texts[sh["id"]]) * 12.5) + 10
            words(sh, el, (x1 + x2) / 2 - w / 2, (y1 + y2) / 2 - 8 * n, w, 0, textAlign="center",
                  verticalAlign="middle")
    for el in els:
        el["boundElements"] = el["boundElements"] or None
    return json.dumps({"type": "excalidraw", "version": 2, "source": "organism/tools/build.py", "elements": els,
                       "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}},
                      indent=1, ensure_ascii=False) + "\n"


# ---- the printable pages: US Letter landscape, one sheet each ------------------------------------

CSS = """@page { size: 11in 8.5in; margin: 0.25in; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #111; font-size: 7.4pt; line-height: 1.2;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 10.5in; min-height: 7.96in; display: flex; flex-direction: column; gap: 0.06in; }
header { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { font-size: 16pt; margin: 0; letter-spacing: -0.2px; }
.sub { font-size: 8.2pt; color: #333; margin-top: 2px; }
.legend { display: grid; grid-template-columns: auto auto; column-gap: 12px; row-gap: 3px; align-items: center;
          justify-items: end; font-size: 7pt; white-space: nowrap; }
.chip { display: inline-block; border: 1px solid; border-radius: 9px; padding: 0 6px; font-size: 6.4pt; line-height: 1.45;
        white-space: nowrap; font-weight: 600; }
.lm { display: inline-block; margin: 0 2px 0 5px; font-weight: 700; font-size: 8.6pt; line-height: 1; color: #868e96;
      vertical-align: -1pt; } .lm.red { color: #c92a2a; }
.lm .mk { display: inline-block; height: 6.2pt; border-left: 1.4px dotted; margin: 0 3px 0 1px; vertical-align: -0.6pt; }
.org { display: grid; grid-template-columns: 1.9in 1fr 2.3in; column-gap: 0.13in; }
.org > .layer, .org > .device, .org > .conn { grid-column: 2; }
.sides { display: flex; flex-direction: column; justify-content: center; gap: 3px; }
.sides > .side:only-child { flex: 1; }
.layer, .side, .cell { position: relative; }
.layer { border: 1.6px solid var(--s); background: var(--f); border-radius: 7px; padding: 2px 7px 3px 7px; }
.h { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
.h .chip { flex: none; margin-top: 1px; }
.t { font-weight: 700; font-size: 7.9pt; } .layer .t, .device .t { font-size: 8.4pt; }
.n { display: inline-block; width: 14px; height: 14px; border-radius: 50%; color: #111; background: #fff;
     border: 1.5px solid var(--s); text-align: center; font-size: 7.2pt; line-height: 11px; margin-right: 5px;
     font-weight: 700; }
.device { border: 1px solid var(--s); border-radius: 8px; padding: 2px 5px 4px 5px; }
.cells { display: grid; gap: 5px; margin-top: 2px; }
.cell { background: var(--f); border: 1.4px solid var(--s); border-radius: 6px; padding: 2px 6px 3px 6px; }
.conn { font-size: 6.9pt; color: #222; min-height: 0.15in; display: flex; align-items: center; justify-content: center;
        gap: 0.4in; }
.conn > span { position: relative; top: -0.5pt; }  /* centers the arrows and words between the frames */
.conn.at { display: grid; column-gap: 5px; padding: 0 6px; } .conn.at > span { justify-self: start; padding-left: 4px; white-space: nowrap; }
.conn b { font-size: 8.6pt; line-height: 1; color: #343a40; margin-right: 3px; }
.conn .red { color: #a61e1e; } .conn .red b { color: #c92a2a; } .conn .dim b { color: #868e96; }
.conn .mk { display: inline-block; height: 6.2pt; border-left: 1.4px dotted; margin: 0 3px 0 1px; vertical-align: -0.6pt; }
.side { border: 1.4px solid #495057; background: #f1f3f5; border-radius: 7px; padding: 2px 7px 3px 7px; font-size: 7.1pt; }
.side[data-a]::after { content: attr(data-a); position: absolute; top: 36%; font-size: 8pt; line-height: 1; color: #343a40;
                       font-weight: 700; }  /* 8pt, centred in the 0.13in gap, clear of both borders */
.side.in[data-a]::after { right: calc(-0.065in - 4pt - 1px); } .side.out[data-a]::after { left: calc(-0.065in - 4pt - 1px); }
.side.dim[data-a]::after { color: #868e96; } .side.red[data-a]::after { color: #c92a2a; }
.side .h .xl { flex: 1; font-size: 6.4pt; color: #343a40; white-space: nowrap; margin-top: 1.6px; }
.side.in .h .xl { text-align: right; }
.xa { position: relative; z-index: 1; font-size: 6.4pt; color: #343a40; white-space: nowrap; align-self: center; }
.xa.first { align-self: center; }
.xa b { font-size: 8pt; font-weight: 700; color: #343a40; margin: 0; vertical-align: -0.3pt; }
.xa.in b { margin-left: 3.5pt; } .xa.out b { margin-right: 3.5pt; }
.xa.in { justify-self: end; margin-right: calc(-0.065in - 4pt); } .xa.out { justify-self: start; margin-left: calc(-0.065in - 4pt); }
.xa.dim b { color: #868e96; } .xa.red b { color: #c92a2a; }
.bottom { display: grid; grid-template-columns: 1.6fr 1.12fr 0.78fr; gap: 0.1in; flex: 1; }
.panel { border: 1.4px solid #adb5bd; border-radius: 8px; padding: 4px 8px; background: #fcfcfd; }
.panel h2 { font-size: 9pt; margin: 0 0 3px 0; display: flex; align-items: center; justify-content: space-between; }
pre.tree { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 6.5pt; line-height: 1.25; margin: 2px 0 4px 0;
           background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 3px 5px; white-space: pre; }
.loop { display: flex; align-items: stretch; gap: 2px; margin: 3px 0; }
.step { flex: 1; border: 1.3px solid #2f9e44; background: #ebfbee; border-radius: 6px; padding: 2px 3px; font-size: 6.4pt; }
.step b { display: block; font-size: 7pt; }
.loopa { align-self: center; font-weight: 700; color: #343a40; font-size: 7pt; } .loopa:last-child { font-size: 10pt; }
code { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 94%; }
ul.inv { margin: 0; padding-left: 12px; font-size: 7.1pt; } ul.inv li { margin: 0 0 2px 0; }
footer { font-size: 6.4pt; color: #555; display: flex; justify-content: space-between; gap: 0.3in; margin-top: auto; }
"""


LOCK_CSS = """.chip.lock { background: #fff; border-color: #495057; border-radius: 2px; } .ref { font-size: 6.6pt; font-weight: 600; color: #495057; }
.chip.lock.done { border-color: #2f9e44; } .chip.lock.none { border-color: #868e96; border-style: dashed; font-weight: 500; }
.newest { background-image: repeating-linear-gradient(135deg, var(--h) 0 1.6px, transparent 1.6px 6px); }
.side.newest { --h: #adb5bd; }
.layer.neither, .side.neither { background: #fff; border-style: dotted; }
.legend .lane { justify-self: start; color: #333; }
.sw { display: inline-block; width: 17px; height: 9px; border: 1px solid #495057; border-radius: 2px; background-color: #e9ecef;
      vertical-align: -1.5px; margin: 0 3px 0 6px; --h: #adb5bd; } .sw:first-child { margin-left: 0; }
.sw.neither { background: #fff; border-style: dotted; }
.legend .chip.lock { margin-right: 3px; } .legend.only { grid-template-columns: auto; }
.h .chips { display: flex; gap: 3px; flex: none; }
.plan .ph { padding: 1.5px 4px 1px 4px; border-bottom: 1px solid #edf0f2; } .plan .ph.you { background: #fff4e6; }
.plan .who { color: #495057; } .plan .gs { display: inline-block; } .plan .gs .g { margin-top: 1px; } .note { margin-top: 4px; font-size: 7pt; color: #333; }
.note.lead { margin: 0 0 3px 0; }
.g { display: inline-block; border: 1px solid; border-radius: 7px; padding: 0 4px; font-size: 6pt; line-height: 1.35;
     font-weight: 700; margin: 0 1px 1px 0; }
.lockin h1 { font-size: 16pt; } .lockin .panel { font-size: 7.8pt; } .lockin .panel h2 { font-size: 10pt; }
.page.lockin { gap: 0.028in; }
.decide { border: 2px solid #e67700; background: #fff4e6; border-radius: 9px; padding: 3px 10px 4px 10px; }
.decide h2 { font-size: 10pt; margin: 0 0 3px 0; }
.decide ol { margin: 0; padding-left: 16px; font-size: 8.3pt; } .decide li { margin: 0; }
.two { display: grid; grid-template-columns: 1.25fr 1fr; gap: 0.12in; }
.two ul { margin: 0; padding-left: 13px; } .two li { margin: 0 0 2px 0; }
.pins { margin-top: 3px; } .pins .p { display: inline-block; border: 1px solid #862e9c; background: #f8f0fc;
        border-radius: 7px; padding: 0 3px; margin: 0 1px 2px 0; font-size: 6.8pt; line-height: 1.42; }
.cite { margin-top: 1px; font-size: 7pt; color: #495057; }
table.status { border-collapse: collapse; width: 100%; font-size: 7.4pt; }
table.status td { padding: 0 3px; border-bottom: 1px solid #edf0f2; vertical-align: middle; }
table.status .chip { line-height: 1.3; } table.status .g { line-height: 1.25; }
table.status td:first-child { width: 1.2in; white-space: nowrap; } table.status td:nth-child(2) { width: 1.05in; }
.phases { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.08in; }
.phase { border: 1.4px solid #adb5bd; border-radius: 8px; padding: 3px 7px 4px 7px; background: #fcfcfd; font-size: 7.3pt; }
.phase h3 { font-size: 9.6pt; margin: 0; } .phase .who { color: #495057; margin-bottom: 2px; }
.phase ul { margin: 0 0 2px 0; padding-left: 12px; } .phase li { margin: 0 0 1px 0; } .phase code { white-space: nowrap; }
li .g { margin: 0 1px; padding: 0 3px; line-height: 1.12; vertical-align: 0.4px; }  /* a gap chip inside a step keeps its line */
.nw { white-space: nowrap; }
.strip { border: 1.4px solid #adb5bd; border-radius: 8px; padding: 2px 8px 3px 8px; background: #fcfcfd; font-size: 7.4pt; }
.strip .door { margin-top: 1px; } .strip .chip { font-size: 6.2pt; line-height: 1.25; }
.strip .m { display: inline-block; border: 1px solid #adb5bd; background: #f1f3f5; border-radius: 6px; padding: 0 4px;
            margin: 0 1px 1px 0; font-size: 7pt; line-height: 1.3; white-space: nowrap; }
.register { display: grid; grid-template-columns: 1.12fr 1fr; column-gap: 0.25in; align-items: start; }
table.reg { border-collapse: collapse; width: 100%; font-size: 7.1pt; line-height: 1.02; }
table.reg td { padding: 0 3px; border-bottom: 1px solid #edf0f2; vertical-align: middle; }
table.reg td:first-child { font-weight: 700; width: 28px; } table.reg td:nth-child(3) { width: 66px; }
table.reg td:last-child { text-align: right; white-space: nowrap; width: 90px; color: #343a40; }
table.reg .chip { font-size: 6.1pt; line-height: 1.12; }
.end { border: 2px solid #343a40; background: #f8f9fa; border-radius: 9px; padding: 3px 10px 4px 10px; font-size: 7.6pt; }
.end .eh { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.end .eh > b { font-size: 10pt; } .end .eh .chip { align-self: center; } .end .ew { font-size: 8.6pt; font-weight: 700; }
.end .ec { margin-top: 1px; line-height: 1.4; } .end .ek { display: inline-block; border: 1px solid #495057; background: #fff;
          border-radius: 5px; padding: 0 4px; line-height: 1.35; white-space: nowrap; }
.end .ea { font-weight: 700; color: #343a40; margin: 0 3px; }
.plan .ph.end1 { border-bottom: 0; } .plan .ph.end1 .chip { font-size: 6pt; line-height: 1.3; }
"""


def pages(t):
    """The printable pages, as (title, body): the map, then what it takes to lock RAPP/1, the LTS release."""
    e, lk, gaps, lock = html.escape, locks(t), {g["id"]: g for g in t["gap"]}, t["lock"]

    def chip(value):
        s = status(value)
        return "" if s is None else f'<span class="chip s-{s.replace(" ", "-")}">{e(s)}</span>'

    def lockchip(n):
        label, items = lk[n]
        kind = "" if items else " done" if label == "in RAPP/1" else " none"
        return f'<span class="chip lock{kind}">{e(label)}</span>'

    def pill(health, text):  # a small chip in the colors of a health word
        s, f = STATUS[status(health)]
        return f'<span class="g" style="background:{f};border-color:{s}">{e(text)}</span>'

    def gapchip(g):
        return pill(g["status"], g["id"])

    def itemchip(item):  # a gap, or a newest part that no gap covers
        return gapchip(gaps[item]) if item in gaps else pill(t["ids"][item]["health"], smart(t["ids"][item]["name"]))

    def lane(x):  # newest parts are striped; RAPP/1 parts stay plain; what ships in neither is dotted and white
        return {"newest": " newest", "outside": " neither", None: " neither"}.get(channel(x), "")

    def glyph(c, col):  # the arrow between a side part and the stack, pointing the way the crossing goes
        return {"both": "\u2194", "in": "\u2192" if col == "in" else "\u2190",
                "out": "\u2190" if col == "in" else "\u2192"}[c["arrow"]]

    def kind(c):
        return " red" if c["red"] else " dim" if c["dim"] else ""

    def titled(p):  # a side part's one crossing to its own layer, when its words fit in the title row
        own = [c for c in t["crossing"] if c.get("side") is p and c["center"]["level"] == p["level"]]
        room = (136.8 if p["col"] == "in" else 165.6) - 12.6 - em(smart(p["name"])) * 7.9 * 1.08 - 8
        room -= em(status(p["health"]) or "") * 6.4 * 1.05 + 10
        return own[0] if len(own) == 1 and em(smart(plain(own[0]["label"]))) * 6.4 <= room else None

    def box(x):
        title = smart(x["name"]) + (f" \u2014 {smart(tagline(x))}" if tagline(x) else "")
        row = t["row"][x["n"]]
        if not row:
            return (f'<div class="layer f-{x["color"]}{lane(x)}"><div class="h"><span class="t"><span class="n">{x["n"]}'
                    f'</span>{e(title)}</span><span class="chips">{chip(x["health"])}{lockchip(x["n"])}</span></div>'
                    f'<div>{e(joined(x))}</div></div>')
        cells = "".join(f'<div class="cell{lane(p)}"><div class="h"><span class="t">{e(smart(p["name"]))}'
                        f'</span>{chip(p["health"])}</div><div>{e(joined(p))}</div></div>' for p in row)
        return (f'<div class="device f-{x["color"]}"><div class="h"><span class="t"><span class="n">{x["n"]}</span>'
                f'{e(title)}</span>{lockchip(x["n"])}</div><div class="cells" style="grid-template-columns: '
                f'{" ".join(str(p["span"]) + "fr" for p in row)}">{cells}</div></div>')

    def side(p):  # its crossing's words ride in the title row when they fit; other arrows are drawn apart
        c = titled(p)
        arrow = f' data-a="{glyph(c, p["col"])}"' if c else ""
        words = f'<span class="xl">{e(smart(plain(c["label"])))}</span>' if c else ""
        rows = "<br>".join(e(smart(plain(line))) for line in p.get("lines", []))  # one row per line
        return (f'<div class="side {p["col"]}{lane(p)}{kind(c) if c else ""}"{arrow}><div class="h"><span class="t">'
                f'{e(smart(p["name"]))}</span>{words}{chip(p["health"])}</div><div>{rows}</div></div>')

    def conn(n):
        def at(end, cells):  # where a cell's middle sits across its layer, from 0 (left) to 1 (right)
            if end not in cells:
                return None
            k = cells.index(end)
            return (sum(p["span"] for p in cells[:k]) + end["span"] / 2) / sum(p["span"] for p in cells)

        def order(c):  # a label sits over the cell it reaches below, else by the cell it leaves above
            low, up = at(c["lower"], t["row"][n - 1]), at(c["upper"], t["row"][n])
            return (low if low is not None else up if up is not None else 0.5, up if up is not None else 0.5)
        def lanes(gap):  # each crossing's own column, in the row above or below: its end's cell, or a free one
            for row in (t["row"][n], t["row"][n - 1]):
                own = {c["stem"]: row.index(end) for c in gap for end in (c["upper"], c["lower"]) if end in row}
                if len(row) < len(gap) or len(set(own.values())) != len(own):
                    continue
                for k, c in enumerate(gap):
                    free = [col for col in range(len(row)) if col not in own.values()]
                    if c["stem"] not in own and free:
                        before = [own[x["stem"]] for x in gap[:k] if x["stem"] in own]
                        after = [col for col in free if not before or col > max(before)]
                        own[c["stem"]] = after[0] if after else free[0]
                if len(own) == len(gap):
                    return row, own
            return None
        gap = sorted((c for c in t["crossing"] if c.get("upper") and c["top"] == n), key=order)
        spans = []
        for c in gap:
            arrow, label = {"down": "\u25bc", "up": "\u25b2", "both": "\u25b2\u25bc"}[c["arrow"]], e(smart(plain(c["label"])))
            mark = '<i class="mk"></i>' if kind(c) else ""  # a dotted line, like the legend's mark
            spans.append((c, f'<b>{mark}{arrow}</b>{label}'))
        placed = lanes(gap) if len(gap) > 1 else None
        if not placed:  # one crossing, or no cell for each: the words sit in the middle
            return '<div class="conn">' + "".join(f'<span class="{kind(c).strip()}">{w}</span>' for c, w in spans) + "</div>"
        row, own = placed  # several: each starts at its own cell and ends where the next one starts
        used = sorted(own.values())
        cells = "".join(f'<span class="{kind(c).strip()}" style="grid-column: {own[c["stem"]] + 1} / '
                        f'{next((u for u in used if u > own[c["stem"]]), len(row)) + 1}">{w}</span>' for c, w in spans)
        columns = " ".join("minmax(0, %dfr)" % p["span"] for p in row)  # columns never grow to fit their words
        return (f'<div class="conn at" style="grid-template-columns: {columns}">'
                f'{cells}</div>')

    def steps(ph):  # each gap a step names is drawn as its chip, in the colors of its status, glued to its marks
        def chipped(m):
            return f'<span class="nw">{m[1]}{gapchip(gaps[m[2]])}{m[3]}</span>' if m[2] in gaps else m[0]
        return "".join("<li>" + re.sub(r"(\(?)\b(G[0-9]+)\b([),;:.]?)", chipped, inline(step)) + "</li>"
                       for step in ph["steps"])

    def who(ph):
        return e(ph["who"] + (f", {ph['note']}" if ph["note"] else ""))

    def grid_row(n):  # the stack's grid rows: layer 6, its crossings, layer 5, ... layer 0
        return 2 * (6 - n) + 1

    beside, org, taken, near = {}, [], set(), {}  # the parts beside each layer sit on its own row; a pair also takes the
    for p in t["sides"]:  # crossing rows above and below it, so each arrow still points at its own layer
        beside.setdefault((p["col"], p["level"]), []).append(p)
    for (col, n), group in sorted(beside.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        r = grid_row(n)
        apart = [c for p in group for c in t["crossing"] if c.get("side") is p and c is not titled(p)]
        reach = [grid_row(c["center"]["level"]) for c in apart]
        rows = range(r, r + 1) if len(group) == 1 else range(r - (n < 6), r + 1 + (n > 0))
        rows = range(min([rows[0]] + reach), max([rows[-1]] + reach) + 1)  # down to every layer it crosses to
        if len(group) > 2 or taken & {(col, k) for k in rows}:
            refuse(group[-1]["where"], "leaves no room beside the stack on the one-pager; change `beside`")
        taken |= {(col, k) for k in rows}
        place = f'grid-column: {1 if col == "in" else 3}'
        here = near.setdefault(n, [])  # read after its own layer: the grid places it, the page order follows it
        here.append(f'<div class="sides" style="grid-row: {rows[0]} / {rows[-1] + 1}; {place}">'
                    + "".join(side(p) for p in group) + "</div>")
        for c in apart:  # an arrow of its own, on the row of the layer it meets, with its words beside it
            words, a = e(smart(plain(c["label"]))), f'<b>{glyph(c, col)}</b>'
            first = " first" if grid_row(c["center"]["level"]) == rows[0] else ""
            here.append(f'<div class="xa {col}{kind(c)}{first}" style="grid-row: {grid_row(c["center"]["level"])}; '
                        f'{place}">' + (f"{words} {a}" if col == "in" else f"{a} {words}") + "</div>")
    for x in reversed(t["layer"]):
        org.append(box(x))
        org.extend(near.get(x["n"], []))
        if x["n"]:
            org.append(conn(x["n"]))
    d, plan, pull = t["dogfood"], lock["plan"], t["pull"]
    tree = [item.split(": ", 1) for item in d["tree"]]
    pad = max(len(a) for a, _ in tree) + 2
    loop = '<span class="loopa">\u2192</span>'.join(
        f'<div class="step"><b>{k} {inline(step.split(": ", 1)[0])}</b>{inline(step.split(": ", 1)[1])}</div>'
        for k, step in enumerate(d["loop"], 1))
    rules = "".join(f"<li><b>{inline(lead)[::-1].replace(' ', chr(160), 1)[::-1]}</b></li>"
                    for lead, _ in t["invariants"]["rules"])  # one line each; the last two words stay together
    dashed = {"gap": '<span class="lm red"><i class="mk"></i>\u25bc</span>',  # the marks the page draws
              "candidate": '<span class="lm">\u2192</span>'}
    words = [" ".join(dashed.get(k, "") + chip(k) for k in list(STATUS)[i:i + 5]) for i in (0, 5)]
    lanes = ['<span class="sw"></span>RAPP/1 (LTS): in force<span class="sw newest"></span>newest'
             '<span class="sw neither"></span>in neither',
             '<span class="chip lock">N to graduate</span>what a layer still needs']
    legend = "".join(f'<span class="lane">{a}</span><div>{b}</div>' for a, b in zip(lanes, words))
    plain_legend = "".join(f'<div>{" ".join(chip(k) for k in list(STATUS)[i:i + 5])}</div>' for i in (0, 5))
    summary = "".join(
        f'<div class="ph{" you" if ph["who"] == "you" else ""}"><b>{ph["n"]} {e(ph["title"])}</b> '
        f'<span class="who">\u00b7 {e(ph["who"])}</span> <span class="gs">'
        f'{"".join(gapchip(g) for g in ph["gaps"]) or e(str(len(ph["steps"])) + " steps, no gaps")}</span></div>'
        for ph in plan)
    short = lock["name"].partition(": ")[0]
    ending = end_line = ""
    if lock["goal"]:  # the page ends where RAPP/1 LTS ends: one part, reached by the steps its role names
        goal, words = lock["goal"]
        lead, sep, route = goal["role"].partition(": ")
        hops = route.split(" \u2192 ") if sep and "\u2192" in route else []
        flow = (inline(lead) + ": " + '<span class="ea">\u2192</span>'.join(
            f'<span class="ek">{inline(hop)}</span>' for hop in hops)) if hops else inline(goal["role"])
        ending = (f'<section class="end"><div class="eh"><b>Where it ends: the {e(smart(goal["name"]))}</b>'
                  f'{chip(goal["health"])}<span class="ew">{inline(words)}.</span></div>'
                  f'<div class="ec">{flow}</div></section>')
        end_line = (f'<div class="ph end1"><b>\u21b3 It ends as the {e(smart(goal["name"]))}</b> '
                    f'<span class="gs">{chip(goal["health"])}</span></div>')
    foot = ("<footer><span>Experimental map, generated from organism/ \u00b7 details: ECOSYSTEM.md and CONSTITUTION.md in "
            "kody-w/rapp-work, branch experimental/rapp-work-constitution</span>"
            "<span>Specifications decide; these pages only point at them.</span></footer>")
    head = (f'<header><div><h1>{{}}</h1><div class="sub">{{}}</div></div>'
            f'<div class="legend">{legend}</div></header>')
    lock_head = (f'<header><div><h1>{{}}</h1><div class="sub">{{}}</div></div>'
                 f'<div class="legend only">{plain_legend}</div></header>')  # page 2 shows health words only
    the_map = f"""<div class="page">
{head.format("The RAPP/1 organism, on one page", "Read it top (6) to bottom (0). Left: what comes in. Right: what goes out or across.")}
<section class="org">
{chr(10).join(org)}
</section>
<section class="bottom">
<div class="panel"><h2>{e(smart(d["name"]))} {chip(d["health"])}</h2>
<pre class="tree">{e(chr(10).join(smart(a).ljust(pad) + smart(b) for a, b in tree))}</pre>
<div class="loop">{loop}<span class="loopa">\u21bb</span></div>
<div>{inline(d["body"])}</div></div>
<div class="panel"><h2>{e(short)} <span class="ref">details: the lock-in page \u2192</span></h2>
<div class="note lead">{inline(". ".join(lock["definition"]) + ".")}</div>
<div class="plan">{summary}{end_line}</div></div>
<div class="panel"><h2>What holds everywhere</h2>
<ul class="inv">{rules}</ul></div>
</section>
{foot}
</div>"""
    one = plan[0]
    status_rows = "".join(
        f'<tr><td><b>{x["n"]} {e(smart(x["name"]))}</b></td><td>{lockchip(x["n"])}</td>'
        f'<td>{"".join(itemchip(item) for item in lk[x["n"]][1])}</td></tr>'
        for x in reversed(t["layer"]))
    none = [repo for repo, k in pull["counts"] if not k]  # the repositories with no mention share one chip
    counts = "".join(f'<span class="m">{e(repo)} <b>{k}</b></span>' for repo, k in pull["counts"] if k) + (
        f'<span class="m">{e(" · ".join(none))} <b>0</b></span>' if none else "")
    doors = " \u00b7 ".join(f"{chip(word)} {inline(text)}" for word, text in pull["doors"])
    mentions = (f'<section class="strip"><b>{pull["phase"]} \u00b7 {e(smart(pull["name"]))}:</b> files that mention '
                f'\u201cexperimental\u201d ({inline(pull["command"])}, {e(pull["measured"])}): {counts} '
                f'{inline(pull["body"])}' + (f'<div class="door"><b>One front door:</b> {doors}</div>' if doors else "")
                + "</section>")
    cards = "".join(f'<div class="phase"><h3>{ph["n"]} \u00b7 {e(ph["title"])}</h3><div class="who">{who(ph)}</div>'
                    f'<ul>{steps(ph)}</ul></div>' for ph in plan[1:])
    words_in = [sum(len(plain(step)) + 24 + 5 * len(re.findall(r"\bG[0-9]+\b", step)) for step in ph["steps"]) + 60
                for ph in plan[1:]]  # a gap chip is wider than its id
    widths = " ".join(f"{k / min(words_in):.2f}fr" for k in words_in)  # wider cards for longer phases: even heights
    rows = [f'<tr><td>{e(g["id"])}</td><td>{inline(g["gap"])}</td><td>{chip(g["status"])}</td>'
            f'<td>{g["phase"]} \u00b7 {e(g["who"])}</td></tr>' for g in t["gap"]]
    half = (len(rows) + 1) // 2  # two columns, the first a little wider
    register = "".join(f'<table class="reg">{"".join(part)}</table>' for part in (rows[:half], rows[half:]))
    pins = "".join(f'<span class="p">{inline(pin)}</span>' for pin in lock["pins"])
    the_lock = f"""<div class="page lockin">
{lock_head.format(e(smart(lock["name"])), inline(lock["body"]))}
<section class="decide"><h2>Your decisions first \u00b7 phase {one["n"]}, {e(one["title"])} \u00b7 {who(one)}</h2>
<ol>{steps(one)}</ol></section>
<section class="two">
<div class="panel"><h2>{e(short)} is</h2><ul>{"".join(f"<li>{inline(item)}.</li>" for item in lock["definition"])}</ul>
<div class="pins"><b>It pins:</b> {pins}</div><div class="cite">{inline(lock["cite"])}.</div></div>
<div class="panel"><h2>Each layer, top to bottom: in RAPP/1, or what it needs to graduate</h2><table class="status">{status_rows}</table></div>
</section>
<section class="phases" style="grid-template-columns: {widths}">{cards}</section>
{mentions}
<section class="panel"><h2>Gap register: each gap, its phase and who acts</h2>
<div class="register">{register}</div></section>
{ending}
{foot}
</div>"""
    return [("The RAPP/1 organism, on one page", the_map), (smart(lock["name"]), the_lock)]


def document(title, *bodies):
    css = CSS + LOCK_CSS + "".join(f".s-{k.replace(' ', '-')} {{ background: {f}; border-color: {s}; }}\n"
                                   for k, (s, f) in STATUS.items())
    css += "".join(f".f-{k} {{ --s: {s}; --f: {f}; --h: {STRIPE[k]}; }}\n" for k, (s, f) in FAMILY.items())
    css += ".page + .page { break-before: page; }\n"
    return (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>{html.escape(title)}</title>\n'
            "<!-- Generated from organism/ by tools/build.py. Edit the part files and rebuild. -->\n"
            f"<style>\n{css}</style>\n</head>\n<body>\n" + "\n".join(bodies) + "\n</body>\n</html>\n")


# ---- the genome and the long-form map ------------------------------------------------------------

def arrow(c):
    return "\u2194" if c["arrow"] == "both" else "\u2192"


def table(head, rows):
    return ["", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def to_lock(t, n):
    """A layer's lock status in words: its label, then what is left, by gap id or part name."""
    label, left = locks(t)[n]
    names = [x if re.fullmatch(r"G[0-9]+", x) else t["ids"][x]["name"] for x in left]
    return label + (f" ({', '.join(names)})" if names else "")


def lock_plan(t, steps=True):
    """The lock-in phases as table rows: phase, who acts, [the steps,] the gaps it closes."""
    return [[f"{ph['n']}. {ph['title']}", ph["who"] + (f", {ph['note']}" if ph["note"] else "")]
            + (["; ".join(ph["steps"])] if steps else [])
            + [", ".join(g["id"] for g in ph["gaps"]) or "\u2014"] for ph in t["lock"]["plan"]]


def pins(lock):
    return ", ".join(lock["pins"][:-1]) + ", and " + lock["pins"][-1]


def mentions(t, short=False):
    """The clean-pull check in one line: the date, each repository's files, what the numbers mean, the front door."""
    pull, counts = t["pull"], ", ".join(f"{repo} {k}" for repo, k in t["pull"]["counts"])
    door = " \u00b7 ".join(f"**{word}:** {text}" for word, text in pull["doors"])
    door = f" One front door: {door}." if door else ""
    if short:  # the genome keeps the gist; clean-pull.md, the lock-in page and ECOSYSTEM.md keep every count
        hits = [(k, repo) for repo, k in pull["counts"] if k]
        return (f"on {pull['measured']}, {len(hits)} of {len(pull['counts'])} default branches mentioned "
                f"\u201cexperimental\u201d (most: {max(hits)[1]}, {max(hits)[0]} files): mentions, not problems. "
                "The file also lists the front door, where people find RAPP/1.")
    return (f"on {pull['measured']}, {pull['command']} counted the files on each default branch that mention "
            f"\u201cexperimental\u201d: {counts}. {pull['body']}{door}")


def genome(t, graph):
    def ref(x, folder):
        return f"[{x['name']}]({folder}/{x['stem']}.md)"

    def brief(value):  # the genome shows the health word and its gaps; the files keep the nuance
        refs = sorted(set(re.findall(r"\bG[0-9]+\b", value)), key=lambda g: int(g[1:]))
        return (status(value) or "\u2014") + (f" ({', '.join(refs)})" if refs else "")

    inv, d, gaps = t["invariants"], t["dogfood"], sorted(t["gap"], key=lambda g: int(g["id"][1:]))
    L = ["<!-- GENERATED by tools/build.py from the part files in this folder. Do not edit by hand. -->", "",
         "# The RAPP/1 organism", "",
         "The whole organism on one page, generated from this folder's part files, one fact per file. "
         "Specifications decide; it only points at them. Experimental.", "",
         "**To change it,** edit a part file, then run `python3 tools/build.py` (`--check` proves nothing "
         "drifted).", "", "```text", graph.rstrip("\n"), "```", "", "## Health words", ""]
    L += [f"- **{word}** {meaning}" for word, meaning in t["health"]["rules"]]
    L += ["", "## Layers, top to bottom"]
    L += table(["#", "Layer", "What it is", "Health", "Into RAPP/1"],
               [[str(x["n"]), ref(x, "layers"), x["role"], brief(x["health"]), to_lock(t, x["n"])]
                for x in reversed(t["layer"])])
    L += ["", "## Parts"] + table(["Part", "Where", "What it is", "Health", "Channel"], [
        [ref(p, "parts"), f"{p['column']}, beside {p['level']}" if p["col"] else f"inside {p['level']}",
         p["role"], brief(p["health"]), channel(p)] for p in [p for n in range(6, -1, -1) for p in t["inner"][n]] + t["sides"]])
    L += ["", "## Crossings"] + table(["From \u2192 to", "What crosses", "Authorized by", "Health"], [
        [f"[{t['ids'][c['from']]['name']} {arrow(c)} {t['ids'][c['to']]['name']}](crossings/{c['stem']}.md)",
         c["what"], c["authorized_by"], brief(c["health"])] for c in t["crossing"]])
    L += ["", "## Gaps (fixes in each file)"] + table(
        ["ID", "Gap", "Status"], [[f"[{g['id']}](gaps/{g['stem']}.md)", g["gap"], status(g["status"])] for g in gaps])
    lock = t["lock"]
    L += ["", f"## {lock['name']}", ""] + [f"- {item}." for item in lock["definition"]]
    L += ["", f"It pins {pins(lock)} (RAPP/1 \u00a7\u00a711.1, 13.3; `rapp-cicd/1` \u00a72). Why, and every step: [lock.md](lock.md)."]
    L += table(["Phase", "Who acts", "Gaps it closes"], lock_plan(t, steps=False))
    L += ["", f"**{t['pull']['name']}** ([clean-pull.md](clean-pull.md)): {mentions(t, short=True)}"]
    if lock["goal"]:
        goal, words = lock["goal"]
        L += ["", f"**Where it ends: the [{goal['name']}](parts/{goal['stem']}.md)** ({status(goal['health'])}): "
              f"{words}. {goal['role']}."]
    L += ["", "## Journeys"] + table(
        ["ID", "Journey"], [[f"[{j['id']}](journeys/{j['id']}.md)", j["title"]] for j in t["journey"]])
    L += ["", "## What holds everywhere", ""] + [f"- **{lead}** {rest}".rstrip() for lead, rest in inv["rules"]]
    L += ["", f"[{d['name']}](dogfood.md) ({d['health']}): where the organism is tried for real. "
          "Other words: [glossary.md](glossary.md).",
          "", "## How to adapt it", "",
          "- **Change a fact:** edit the one file that holds it; every view follows.",
          "- **Move a part:** change its `beside` or `layer`.",
          "- **Add a crossing:** add a file to `crossings/`; the builder checks its ends and direction.",
          f"- {inv['upstream']}", ""]
    return "\n".join(L)


def ecosystem(t):
    inv, gaps = t["invariants"], sorted(t["gap"], key=lambda g: int(g["id"][1:]))
    L = [MARK, "", "# The RAPP/1 organism, top to bottom", "",
         "> **Generated from [`organism/`](organism/).** Do not edit this file by hand: edit the part files there, "
         "then run `python3 organism/tools/build.py`. The same organism on one page is its genome, "
         "[`organism/ORGANISM.md`](organism/ORGANISM.md).", "",
         "**Status: experimental map.** It describes what exists and what is proposed, and changes nothing by "
         "itself. Specifications decide; this map only points at them. Where they disagree, the specification "
         "wins. It is a companion to the draft [`CONSTITUTION.md`](CONSTITUTION.md).", "",
         "![The RAPP/1 organism, top to bottom](organism/views/organism.svg)", "",
         "**How to read the graph:**",
         "- The **center column** stacks the layers from you (6, top) down to bytes (0, bottom).",
         "- The **left column** is what flows in: outside knowledge and reviewed agents.",
         "- The **right column** is what goes out or across: public copies and other organizations, and the "
         "release rings whose evidence comes back in.",
         "- **Tags** show health, in the words of [`organism/health.md`](organism/health.md). A red dashed arrow "
         "is a crossing no specification allows yet; a gray dashed one is a candidate.",
         "- **Plain boxes** in force are RAPP/1, the LTS release people pull. **Striped boxes** are newest: not in "
         "RAPP/1 yet. Inside each layer, the RAPP/1 cells come first and the newest cells after them. **Dotted white "
         "boxes** ship in neither: you, and outside knowledge.",
         "- The **far right column** says what each layer still needs to graduate into RAPP/1 (section 7).", "",
         "The graph is drawn from the tree, like its other views: [Excalidraw](organism/views/organism.excalidraw), "
         "[text](organism/views/graph.txt), [one printable page](organism/views/one-page.html) and "
         "[what it takes to lock RAPP/1 LTS](organism/views/lock-in.html).", "",
         "## 1. The layers, top to bottom"]
    L += table(["#", "Layer", "What it is", "Who decides", "Signed with", "Home", "Health"],
               [[str(x["n"]), f"**{x['name']}**", x["role"], x["decides"], x["signed_with"], x["home"], x["health"]]
                for x in reversed(t["layer"])])
    for x in (x for x in reversed(t["layer"]) if t["inner"][x["n"]]):
        L += ["", f"Inside layer {x['n']}, {x['name']}:"] + table(["Part", "What it is", "Home", "Health", "Channel"], [
            [f"**{p['name']}**", p["role"], p["home"], p["health"], channel(p)] for p in t["inner"][x["n"]]])
    L += ["", "Beside the stack:"] + table(["Column", "Part", "What it is", "Home", "Health", "Channel"], [
        [p["column"].capitalize(), f"**{p['name']}**", p["role"], p["home"], p["health"], channel(p)]
        for p in t["sides"]])
    L += ["", "## 2. Crossings: how anything moves between layers", "",
          "Every arrow in the graph is one row here, pointing the same way. Transport carries bytes; signatures "
          "decide (Constitution Article 7)."]
    L += table(["From \u2192 to", "What crosses", "Authorized by", "Home", "Health"], [
        [f"{t['ids'][c['from']]['name']} {arrow(c)} {t['ids'][c['to']]['name']}", c["what"], c["authorized_by"],
         c["home"], f"**{c['health']}**" if c["red"] else c["health"]] for c in t["crossing"]])
    L += ["", "## 3. End to end, through every layer", ""]
    for k, j in enumerate(t["journey"], 1):
        L += [f"{k}. **{j['title']}**"] + [f"   - {step}" for step in j["steps"]]
    L += ["", "## 4. What holds everywhere", ""] + [f"- **{lead}** {rest}".rstrip() for lead, rest in inv["rules"]]
    checks = {}
    for x in [y for layer in t["layer"] for y in [layer, *t["inner"][layer["n"]]]] + t["sides"]:
        for item in x.get("check", []):
            checks.setdefault(item, []).append(x["name"])
    L += ["", "## 5. Keeping it healthy", "", inv["healthy"]]
    L += table(["Layer or part", "Check"], [[", ".join(names), item] for item, names in checks.items()])
    L += ["", "## 6. Gap register"] + table(["ID", "Gap", "Home", "Fix", "Status", "Phase", "Who acts"], [
        [g["id"], g["gap"], g["home"], g["fix"], g["status"], str(g["phase"]), g["who"]] for g in gaps])
    lock, pull = t["lock"], t["pull"]
    L += ["", inv["upstream"], "", f"## 7. {lock['name']}", ""] + [f"- {item}." for item in lock["definition"]]
    L += ["", f"It pins {pins(lock)}. {lock['cite']}.", "", lock["body"]]
    L += ["", "The five phases, in order:"] + table(["Phase", "Who acts", "Steps", "Gaps it closes"], lock_plan(t))
    L += ["", f"**{pull['name']}** (phase {pull['phase']}): {mentions(t)}"]
    L += ["", "What each layer still needs, top to bottom:"] + table(["Layer", "Into RAPP/1"], [
        [f"{x['n']} {x['name']}", to_lock(t, x["n"])] for x in reversed(t["layer"])])
    if lock["goal"]:
        goal, words = lock["goal"]
        L += ["", f"**Where it ends: the {goal['name']}** ({goal['health']}): {words}. {goal['role']}."]
    L += ["", "## 8. Words", ""]
    L += [f"- **{term}** {meaning}" for term, meaning in t["glossary"]["rules"]]
    L += [""]
    return "\n".join(L).replace("](" + REPO, "](")  # links into the host repository become relative


# ---- build, check, print -------------------------------------------------------------------------

def build(t, root=ROOT):
    """Every generated file, as {path: bytes}. The host map is kept only where it already carries MARK."""
    graph, d, (the_map, the_lock) = graph_txt(t), drawing(t), pages(t)
    out = {root / "ORGANISM.md": genome(t, graph), root / "views/graph.txt": graph,
           root / "views/organism.svg": svg(d), root / "views/organism.excalidraw": excalidraw(d),
           root / "views/one-page.html": document(*the_map), root / "views/lock-in.html": document(*the_lock)}
    host = root.parent / "ECOSYSTEM.md"
    if host.is_file() and host.read_text(encoding="utf-8").startswith(MARK):
        out[host] = ecosystem(t)
    return {path: text.encode("utf-8") for path, text in out.items()}


def show(path, root=ROOT):
    return path.relative_to(root.parent).as_posix()


def check(root=ROOT):
    outputs = build(load(root), root)
    stale = [path for path, data in outputs.items() if not path.is_file() or path.read_bytes() != data]
    views = root / "views"
    extra = sorted(p for p in views.iterdir() if p not in outputs and p.relative_to(root).as_posix() not in PAGES
                   and not p.name.startswith(".")) if views.is_dir() else []
    for path in stale:
        print(f"stale: {show(path, root)} differs from the tree; run python3 tools/build.py")
    for path in extra:
        print(f"stray: {show(path, root)} is not a view the builder makes; remove it")
    if stale or extra:
        return 1
    print(f"organism: all {len(outputs)} generated files match the tree")
    return 0


def chrome():
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return str(mac)
    return next((shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser") if shutil.which(n)), None)


def pdf(root=ROOT):
    """Print the map, the lock-in page and both together with headless Chrome; prove each page count."""
    exe = chrome()
    if exe is None:
        print("no Chrome or Chromium found: the PDFs were not printed")
        return 0
    with tempfile.TemporaryDirectory() as scratch:
        both = Path(scratch) / "rapp-lock-in.html"
        both.write_text(document("RAPP/1 LTS: the map, and what it takes to lock it", *(b for _, b in pages(load(root)))),
                        encoding="utf-8")
        sources = {"views/one-page.pdf": root / "views/one-page.html", "views/lock-in.pdf": root / "views/lock-in.html",
                   "views/rapp-lock-in.pdf": both}
        for name, source in sources.items():
            out = root / name
            out.unlink(missing_ok=True)
            try:
                subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                                f"--print-to-pdf={out}", source.as_uri()], capture_output=True, timeout=120, check=False)
            except subprocess.TimeoutExpired:
                pass
            if not out.is_file():
                refuse(show(out, root), "Chrome did not print it")
            count = len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", out.read_bytes()))
            if count != PAGES[name]:
                refuse(show(out, root), f"has {count} pages, not {PAGES[name]}: every page must fit one US Letter "
                       "landscape sheet")
            print(f"printed {show(out, root)}: {count} page{'s' if count > 1 else ''}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build every view of the organism from its part files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="rebuild in memory; exit 1 if anything drifted")
    mode.add_argument("--pdf", action="store_true", help="also print the PDFs in views/ with headless Chrome")
    args = parser.parse_args(argv)
    try:
        if args.check:
            return check()
        outputs = build(load())
        for path, data in outputs.items():
            if not path.is_file() or path.read_bytes() != data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        print("built from the tree: " + ", ".join(show(path) for path in outputs))
        return pdf() if args.pdf else 0
    except Refused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
