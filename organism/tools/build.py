#!/usr/bin/env python3
"""Build every view of the organism from its tree of markdown part files.

    python3 tools/build.py           write ORGANISM.md and views/ (and, in the host repository, ../ECOSYSTEM.md)
    python3 tools/build.py --check   rebuild everything in memory; exit 1 if any generated file differs
    python3 tools/build.py --pdf     also print views/one-page.pdf with headless Chrome, when it is installed

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
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/kody-w/rapp-work/blob/main/"  # links from the tree into its host repository
MARK = "<!-- GENERATED from organism/ by organism/tools/build.py. Edit the part files and rebuild. -->"
PDF = "views/one-page.pdf"
KINDS = {  # where: (kind, required fields, optional fields)
    "layers": ("layer", "layer name role decides signed_with home health color", "lines check"),
    "parts": ("part", "name role home health", "layer column beside order lines check"),
    "crossings": ("crossing", "from to what authorized_by home health arrow label", ""),
    "gaps": ("gap", "id gap home fix status", ""),
    "journeys": ("journey", "id title", ""),
    "invariants.md": ("invariants", "healthy upstream", ""),
    "dogfood.md": ("dogfood", "name health tree loop", ""),
}
LISTS = {"lines", "check", "tree", "loop"}
STATUS = {  # the first words of every `health` and `status`: (stroke, fill) in Open Color
    "in force": ("#2f9e44", "#b2f2bb"), "experimental": ("#e67700", "#ffe8cc"),
    "candidate": ("#e67700", "#ffe8cc"), "proposed": ("#f08c00", "#fff3bf"),
    "open": ("#868e96", "#e9ecef"), "planned": ("#6741d9", "#e5dbff"),
    "gap": ("#c92a2a", "#ffc9c9"), "own shape": ("#495057", "#dee2e6"),
}
FAMILY = {  # layer colors, Open Color families: (stroke, fill)
    "gray": ("#495057", "#e9ecef"), "orange": ("#e67700", "#fff3bf"), "green": ("#2f9e44", "#d3f9d8"),
    "blue": ("#1864ab", "#d0ebff"), "purple": ("#862e9c", "#f3d9fa"),
}
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


def validate(t):
    folder = t["root"]
    for x in t["layer"]:
        m = re.fullmatch(r"(\d)-([a-z0-9]+(?:-[a-z0-9]+)*)", x["stem"])
        if not m or x["layer"] != m[1]:
            refuse(x["where"], "name a layer file <layer>-<id>.md, with <layer> equal to its `layer` field")
        x.update(id=m[2], n=int(m[1]), level=int(m[1]), col=None)
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
        if not re.fullmatch(r"\d{1,3}", p.get("order", "0")):
            refuse(p["where"], "`order` is a whole number")
        p.update(id=p["stem"], level=int(p.get("layer") or p["beside"]), rank=int(p.get("order", "0")),
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
    gaps = set()
    for g in t["gap"]:
        m = re.fullmatch(r"G([1-9][0-9]?)", g["id"])
        if not m or g["stem"] != f"G{int(m[1]):02d}":
            refuse(g["where"], "a gap's `id` is G<number>, in a file named G<two digits>.md (G1 in G01.md)")
        gaps.add(g["id"])
        status(g["status"], g["where"])
    for j in t["journey"]:
        if not re.fullmatch(r"E[1-9][0-9]?", j["id"]) or j["stem"] != j["id"]:
            refuse(j["where"], "a journey's `id` is E<number>, in a file named E<number>.md")
        j["steps"] = [line[2:] for line in j["body"].splitlines() if line.startswith("- ")]
        if not j["steps"]:
            refuse(j["where"], "list the steps in the body as `- ` lines")
    t["journey"].sort(key=lambda j: int(j["id"][1:]))
    for x in t["layer"] + t["part"] + t["crossing"] + [t["dogfood"]]:
        status(x["health"], x["where"])
        for ref in re.findall(r"\bG[0-9]+\b", x["health"]):
            if ref not in gaps:
                refuse(x["where"], f"`health` names {ref}, which has no file in gaps/")
    inv = t["invariants"]
    rules = [re.fullmatch(r"- \*\*(.+?)\*\*\s*(.*)", line) for line in inv["body"].splitlines() if line]
    if not rules or not all(rules):
        refuse(inv["where"], "write each rule in the body as `- **Lead.** More words.`")
    inv["rules"] = [(m[1], m[2]) for m in rules]
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
        c["gap"] = next(iter(re.findall(r"\bG[0-9]+\b", c["health"])), "")
        c["red"] = status(c["health"]) == "gap"
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


def wrap(text, width):  # a " ·" stays with the word before it
    rows = textwrap.wrap(text.replace(" \u00b7", "\u00a0\u00b7"), width, break_long_words=False, break_on_hyphens=False)
    return [row.replace("\u00a0", " ") for row in rows] or [""]


def lower1(text):
    return text[0].lower() + text[1:] if text[1:2].islower() else text


def tagline(x):
    """A layer whose role starts with a short phrase and a colon takes that phrase as its title."""
    head, sep, _ = x["role"].partition(": ")
    return lower1(plain(head)) if sep and len(head) <= 40 else ""


def leads(t):
    """The invariants' bold leads, as one running phrase."""
    return [lead.rstrip(".,;:") if k == 0 else lower1(lead.rstrip(".,;:"))
            for k, (lead, _) in enumerate(t["invariants"]["rules"])]


def items(x, width):
    return [row for line in x.get("lines", []) for row in wrap(plain(line), width)]


def joined(x):
    """A box's lines as one run of text: sentences and → steps flow on; other phrases take a ·."""
    out = ""
    for line in (smart(plain(line)) for line in x.get("lines", [])):
        glue = " " if out.endswith((".", "!", "?", "\u201d")) or line.startswith("\u2192") else " \u00b7 "
        out += (glue if out else "") + line
    return out


def spots(t, n, xs, mid, step):
    """Where the crossings between layer n and n - 1 are drawn: at their sub-part if they have one,
    else in the middle, or at a free sub-part when others take the middle."""
    gap = [c for c in t["crossing"] if c.get("upper") and c["top"] == n]
    ends = {c["stem"]: next((e for e in (c["upper"], c["lower"]) if e["id"] in xs), None) for c in gap}
    used = {xs[e["id"]] for e in ends.values() if e}
    spare = [xs[p["id"]] for p in t["inner"][n] + t["inner"][n - 1] if xs[p["id"]] not in used]
    placed = []
    for c in gap:
        e = ends[c["stem"]]
        x = xs[e["id"]] if e else spare.pop(0) if used and spare else mid
        while x in [q[0] for q in placed]:
            x += step
        placed.append((x, c, e))
    return sorted(placed, key=lambda q: q[0])


# ---- the text graph ------------------------------------------------------------------------------

def graph_txt(t):
    """99 columns: the stack in the middle, what comes in on the left, what goes out or across on the right."""
    W, LW, C, CW, R = 99, 19, 30, 46, 79
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

    for n, inner in t["inner"].items():
        if inner:
            base, extra = divmod(CW - 2 - (len(inner) - 1), len(inner))
            x = C + 1
            for k, p in enumerate(inner):
                w = base + (1 if k >= len(inner) - extra else 0)
                cells[p["id"]] = (x, w)
                x += w + 1
    put(0, 0, "THE RAPP/1 ORGANISM  \u00b7  read it bottom (0) to top (6)")
    r = 2
    for layer in reversed(t["layer"]):
        n, inner = layer["n"], t["inner"][layer["n"]]
        if not inner:
            rows = fit(titled(layer, tag(layer), IN) + items(layer, IN), IN, layer)
            frame(r, C, CW, rows, len(rows) + 2)
            bottom = r + len(rows) + 1
        else:
            heads = titled(layer, "", IN)
            cols = [fit(wrap(p["name"].upper(), cells[p["id"]][1] - 2) + items(p, cells[p["id"]][1] - 2) + [tag(p)],
                        cells[p["id"]][1] - 2, p) for p in inner]
            depth = max(len(col) for col in cols)
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
        for sb in sides:
            if sb["open"] == n:
                sb["bottom"], sb["open"] = max(sb["bottom"], r + 2), None
                low[sb["col"]] = max(low[sb["col"]], sb["bottom"])
        for p in (p for p in t["sides"] if p["level"] == n):
            if any(sb["open"] is not None and sb["col"] == p["col"] for sb in sides):
                refuse(p["where"], "sits where a taller part beside it still reaches; move one of them")
            same = bool(sides) and sides[-1]["col"] == p["col"] and sides[-1]["part"]["level"] == n
            top = max(r, low[p["col"]] + (1 if same else 2))
            width = (LW if p["col"] == "in" else RW) - 4
            rows = fit(wrap(p["name"].upper(), width) + items(p, width) + [tag(p)], width, p)
            below = [c["center"]["level"] for c in t["crossing"] if c.get("side") is p and c["top"] < n]
            sides.append(dict(part=p, col=p["col"], top=top, rows=rows, bottom=top + len(rows) + 1,
                              open=min(below) if below else None))
            if not below:
                low[p["col"]] = sides[-1]["bottom"]
        r = bottom + 1
        gap = [c for c in t["crossing"] if c.get("upper") and c["top"] == n]
        if n == 0 or not gap:
            r += 0 if n == 0 else 1
            continue
        wide = all(sb["bottom"] < r and sb["open"] is None for sb in sides if sb["col"] == "out")
        placed = spots(t, n, {k: x + w // 2 for k, (x, w) in cells.items()}, MID, 4)
        texts = []
        for k, (x, c, end) in enumerate(placed):
            stop = placed[k + 1][0] - 2 if k + 1 < len(placed) else (W - 1 if wide else R - 2)
            note = [f"GAP {c['gap']}: no spec yet"] if c["red"] else []
            texts.append(fit(wrap(plain(c["label"]), stop - x - 1) + note, stop - x - 1, c))
        depth = max(2, *(len(rows) for rows in texts))
        for (x, c, end), rows in zip(placed, texts):
            line = "\u250a" if c["red"] else "\u2502"
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
        put(rows[(len(rows) - 1) // 2], LW if left else C + CW, "".join(s))
    r = len(grid) + 1
    put(r, 0, "[in force] specified and running   [exp] experimental   \u250a GAP: no spec allows it yet")
    put(r + 1, 0, "In by signed copy (left) \u00b7 out by approved copy (right) \u00b7 transport carries, signatures decide")
    return "\n".join("".join(row).rstrip() for row in grid) + "\n"


# ---- the drawing: one layout, drawn as SVG and as Excalidraw -------------------------------------

def per(px, size=13.5):
    return int(px / (size * 0.52))  # characters of Helvetica that fit in px


def drawing(t):
    """One layout as a list of shapes, which the SVG and the Excalidraw views both draw."""
    W, TOP, LX, LW, CX, CW, RX, RW = 1500, 132, 30, 300, 370, 760, 1170, 300
    mid, stack, shapes, span, cells = CX + CW // 2, list(reversed(t["layer"])), [], {}, {}

    def rows(x, px):
        return [row for line in x.get("lines", []) for row in wrap(smart(plain(line)), per(px - 28))]

    def home(x):  # the drawing also names each layer's home
        return [] if x["home"] == "\u2014" else wrap(smart(plain("Home: " + x["home"])), per(CW - 28))

    def shape(k, g, **kw):
        shapes.append(dict(k=k, g=g, **kw))

    def text(g, x, y, s, size, bold=False, color="#000000", middle=False):
        shape("text", g, x=round(x), y=round(y), s=s, size=size, bold=bold, color=color, middle=middle)

    def rect(g, x, y, w, h, stroke, fill, rx=10, dash=False, width=2):
        shape("rect", g, x=x, y=y, w=w, h=h, stroke=stroke, fill=fill, rx=rx, dash=dash, width=width)

    def box(g, x, y, w, h, s, f, title, lines, tag, num=None, frame=False):
        rect(g, x - 8, y - 8, w + 16, h + 16, s, None, 14, True) if frame else rect(g, x, y, w, h, s, f)
        span[g] = (y - 8, y + h + 8) if frame else (y, y + h)
        if num is not None:
            shape("circle", g, x=x - 22, y=y + 30, r=14, fill=s)
            text(g, x - 22, y + 35, str(num), 14, True, "#ffffff", True)
        if title:
            text(g, x + 14, y + 28, title, 17, True)
        for i, line in enumerate(lines):
            text(g, x + 14, y + 54 + 20 * i, line, 13.5)
        if tag:
            ts, tf = STATUS[tag]
            tw = round(16 + 7.4 * len(tag))
            rect(g, x + w - tw - 10, y + 10, tw, 22, ts, tf, 11, width=1)
            text(g, x + w - 10 - tw / 2, y + 25, tag, 12, middle=True)

    text("head", 30, 52, "The RAPP/1 organism, bottom to top", 30, True)
    text("head", 30, 84, "Center: the layers, from bytes (0, bottom) to you (6, top). "
         "Left: what comes in. Right: what goes out or across.", 15)
    for k, word in enumerate(("in force", "experimental", "gap")):
        rect("legend", 1010 + 130 * k, 30, 118, 26, *STATUS[word], 13, width=1)
        text("legend", 1069 + 130 * k, 48, word, 13, middle=True)
    shape("line", "legend", pts=[(1010, 76), (1050, 76)], red=True, both=False)
    text("legend", 1060, 81, "a crossing no specification allows yet", 13)
    for n, inner in t["inner"].items():
        w = (CW - 20 * (len(inner) - 1)) // len(inner) if inner else 0
        cells.update({p["id"]: (CX + k * (w + 20), w) for k, p in enumerate(inner)})
    band = max([118] + [58 + 20 * len(rows(x, CW) + home(x)) for x in t["layer"] if not t["inner"][x["n"]]]
               + [58 + 20 * len(rows(p, cells[p["id"]][1])) for inner in t["inner"].values() for p in inner])
    ys, y, labels = {}, TOP, []
    for layer in stack:  # the bands, and the room each gap needs for its labels
        ys[layer["n"]] = y
        if layer["n"] == 0:
            break
        placed, here = spots(t, layer["n"], {k: x + 50 for k, (x, w) in cells.items()}, mid, 220), []
        for k, (x, c, end) in enumerate(placed):
            stop = placed[k + 1][0] - 20 if k + 1 < len(placed) else CX + CW + 30
            note = [f"gap {c['gap']} \u2014 no specification allows this yet"] if c["red"] else []
            here.append((x, c, wrap(smart(plain(c["label"])), per(stop - x - 12, 12.5)) + note))
        gap = max([62] + [24 + 17 * (len(words) - 1) + 21 for _, _, words in here])
        labels += [(*q, gap) for q in here]
        y += band + gap
    for layer in stack:
        n, (s, f), inner = layer["n"], FAMILY[layer["color"]], t["inner"][layer["n"]]
        title = smart(layer["name"] + (f" \u2014 {tagline(layer)}" if tagline(layer) else ""))
        box(layer["id"], CX, ys[n], CW, band, s, f, "" if inner else title, [] if inner else rows(layer, CW)
            + home(layer), None if inner else status(layer["health"]), n, bool(inner))
        for p in inner:
            box(p["id"], cells[p["id"]][0], ys[n], cells[p["id"]][1], band, s, f, smart(p["name"]),
                rows(p, cells[p["id"]][1]), status(p["health"]))
    for x, c, text_rows, gap in labels:
        up, low = c["upper"], c["lower"]
        y1, y2 = span[up["id"]][1], span[low["id"]][0]
        shape("line", c["stem"], pts=[(x, y2), (x, y1)] if c["arrow"] == "up" else [(x, y1), (x, y2)],
              red=c["red"], both=c["arrow"] == "both")
        for i, row in enumerate(text_rows):
            text(c["stem"], x + 12, y1 + (gap - 17 * (len(text_rows) - 1)) / 2 + 4 + 17 * i, row, 12.5)
    for col, bx, bw in (("in", LX, LW), ("out", RX, RW)):
        prev = -10 ** 6
        for n in range(6, -1, -1):
            group = [p for p in t["sides"] if p["col"] == col and p["level"] == n]
            hs = [58 + 20 * len(rows(p, bw)) for p in group]
            top = max(ys[n] if len(group) < 2 else ys[n] + (band - sum(hs) - 20 * (len(group) - 1)) // 2, prev + 20)
            for p, h in zip(group, hs):
                for c in (c for c in t["crossing"] if c.get("side") is p and c["top"] < n):
                    h = max(h, ys[c["center"]["level"]] + 90 - top)  # reach every layer it crosses to
                box(p["id"], bx, top, bw, h, *FAMILY["gray"], smart(p["name"]), rows(p, bw), status(p["health"]))
                prev, top = top + h, top + h + 20
    for c in (c for c in t["crossing"] if c.get("side")):
        (a, b), (u, v) = span[c["side"]["id"]], span[c["center"]["id"]]
        lo, hi, left = max(a, u), min(b, v), c["side"]["col"] == "in"
        if hi - lo < 24:
            refuse(c["where"], "its side part does not sit beside its layer in the drawing; change `beside`")
        y = max(lo + 12, hi - 30) if left else (lo + hi) // 2  # on the left, below the layer numbers
        pad = 8 if u < ys[c["center"]["level"]] else 0  # a container's frame sits 8 outside its band
        near, far = (CX - pad, LX + LW) if left else (CX + CW + pad, RX)
        shape("line", c["stem"], pts=[(far, y), (near, y)] if c["arrow"] == "in" else [(near, y), (far, y)],
              red=c["red"], both=c["arrow"] == "both")
    foot = max(b for _, b in span.values()) + 40
    notes = wrap("Holds everywhere: " + " \u00b7 ".join(smart(x) for x in leads(t)), per(W - 60, 14))
    for i, row in enumerate(notes):
        text("foot", 30, foot + 24 * i, row, 14)
    text("foot", 30, foot + 24 * len(notes), "Drawn from the organism/ tree by tools/build.py \u00b7 the tree "
         "is the source; this picture is a view \u00b7 experimental", 12.5, color="#495057")
    return dict(W=W, H=foot + 24 * len(notes) + 40, shapes=shapes)


def svg(d):
    e, W, H = html.escape, d["W"], d["H"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         'font-family="Helvetica, Arial, sans-serif">', "<defs>"]
    o += [f'<marker id="{m}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
          f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
          for m, c in (("ah", "#343a40"), ("ahr", "#c92a2a"))]
    o += ["</defs>", f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>']
    for s in d["shapes"]:
        if s["k"] == "rect":
            dash = ' stroke-dasharray="6 4"' if s["dash"] else ""
            o.append(f'<rect x="{s["x"]}" y="{s["y"]}" width="{s["w"]}" height="{s["h"]}" rx="{s["rx"]}" '
                     f'fill="{s["fill"] or "none"}" stroke="{s["stroke"]}" stroke-width="{s["width"]}"{dash}/>')
        elif s["k"] == "circle":
            o.append(f'<circle cx="{s["x"]}" cy="{s["y"]}" r="{s["r"]}" fill="{s["fill"]}"/>')
        elif s["k"] == "text":
            more = (' font-weight="700"' if s["bold"] else "") + (' text-anchor="middle"' if s["middle"] else "")
            more += f' fill="{s["color"]}"' if s["color"] != "#000000" else ""
            o.append(f'<text x="{s["x"]}" y="{s["y"]}" font-size="{s["size"]}"{more}>{e(s["s"])}</text>')
        else:
            (x1, y1), (x2, y2) = s["pts"]
            color, m = ("#c92a2a", "ahr") if s["red"] else ("#343a40", "ah")
            more = (' stroke-dasharray="8 6"' if s["red"] else "") + (f' marker-start="url(#{m})"' if s["both"] else "")
            o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5"{more} '
                     f'marker-end="url(#{m})"/>')
    return "\n".join(o + ["</svg>"]) + "\n"


def excalidraw(d):
    """The same shapes as Excalidraw elements: sized text, black; each box grouped with its words."""
    els = []

    def add(kind, s, x, y, w, h, **kw):
        n = len(els) + 1
        els.append({"id": f"{s['g']}-{n}", "type": kind, "x": x, "y": y, "width": w, "height": h, "angle": 0,
                    "strokeColor": "#000000", "backgroundColor": "transparent", "fillStyle": "solid",
                    "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100, "groupIds": [s["g"]],
                    "frameId": None, "roundness": None, "seed": n, "version": 1, "versionNonce": n,
                    "isDeleted": False, "boundElements": None, "updated": 1, "link": None, "locked": False, **kw})

    for s in d["shapes"]:
        if s["k"] == "rect":
            add("rectangle", s, s["x"], s["y"], s["w"], s["h"], strokeColor=s["stroke"], strokeWidth=s["width"],
                backgroundColor=s["fill"] or "transparent", strokeStyle="dashed" if s["dash"] else "solid",
                roundness={"type": 3})
        elif s["k"] == "circle":
            add("ellipse", s, s["x"] - s["r"], s["y"] - s["r"], 2 * s["r"], 2 * s["r"], strokeColor=s["fill"],
                backgroundColor=s["fill"])
        elif s["k"] == "text":
            w = round(len(s["s"]) * s["size"] * (0.6 if s["bold"] else 0.56)) + 10
            add("text", s, s["x"] - w // 2 if s["middle"] else s["x"], round(s["y"] - s["size"]), w,
                round(s["size"] * 1.25), text=s["s"], originalText=s["s"], fontSize=s["size"], fontFamily=2,
                textAlign="center" if s["middle"] else "left", verticalAlign="top", containerId=None,
                lineHeight=1.25, autoResize=True, strokeWidth=1)
        else:
            (x1, y1), (x2, y2) = s["pts"]
            add("arrow", s, x1, y1, x2 - x1, y2 - y1, points=[[0, 0], [x2 - x1, y2 - y1]],
                strokeColor="#c92a2a" if s["red"] else "#343a40", strokeStyle="dashed" if s["red"] else "solid",
                lastCommittedPoint=None, startBinding=None, endBinding=None,
                startArrowhead="arrow" if s["both"] else None, endArrowhead="arrow", elbowed=False)
    return json.dumps({"type": "excalidraw", "version": 2, "source": "organism/tools/build.py", "elements": els,
                       "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None}, "files": {}},
                      indent=1, ensure_ascii=False) + "\n"


# ---- the one-pager: US Letter landscape, one page ------------------------------------------------

CSS = """@page { size: 11in 8.5in; margin: 0.28in; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #111; font-size: 7.4pt; line-height: 1.2;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { width: 10.44in; min-height: 7.9in; display: flex; flex-direction: column; gap: 0.06in; }
header { display: flex; align-items: flex-end; justify-content: space-between; }
h1 { font-size: 16pt; margin: 0; letter-spacing: -0.2px; }
.sub { font-size: 8.2pt; color: #333; margin-top: 2px; }
.legend { display: flex; flex-direction: column; gap: 3px; align-items: flex-end; font-size: 7pt; white-space: nowrap; }
.chip { display: inline-block; border: 1px solid; border-radius: 9px; padding: 0 6px; font-size: 6.4pt; line-height: 1.45;
        white-space: nowrap; font-weight: 600; }
.gapline { display: inline-block; width: 26px; border-top: 2px dashed #c92a2a; vertical-align: middle; margin-right: 3px; }
.org { display: grid; grid-template-columns: 1.62in 1fr 1.78in; column-gap: 0.13in; }
.layer, .side, .cell { position: relative; }
.layer { border: 1.6px solid var(--s); background: var(--f); border-radius: 7px; padding: 2px 7px 3px 7px; }
.h { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
.h .chip { flex: none; margin-top: 1px; }
.t { font-weight: 700; font-size: 7.9pt; } .layer .t, .device .t { font-size: 8.4pt; }
.n { display: inline-block; width: 14px; height: 14px; border-radius: 50%; color: #fff; background: var(--s);
     text-align: center; font-size: 7.2pt; line-height: 14px; margin-right: 5px; font-weight: 700; }
.device { border: 1.6px dashed var(--s); border-radius: 8px; padding: 2px 5px 4px 5px; }
.cells { display: grid; gap: 5px; margin-top: 2px; }
.cell { background: var(--f); border: 1.4px solid var(--s); border-radius: 6px; padding: 2px 6px 3px 6px; }
.conn { font-size: 6.9pt; color: #222; height: 0.155in; display: flex; align-items: center; justify-content: center;
        gap: 0.4in; }
.conn b { font-size: 8.6pt; color: #343a40; margin-right: 3px; }
.conn .red { color: #a61e1e; } .conn .red b { color: #c92a2a; }
.side { border: 1.4px solid #495057; background: #f1f3f5; border-radius: 7px; padding: 2px 7px 3px 7px; font-size: 7.1pt; }
.side[data-a]::after { content: attr(data-a); position: absolute; top: 34%; font-size: 12pt; color: #343a40; font-weight: 700; }
.side.in[data-a]::after { right: -0.145in; } .side.out[data-a]::after { left: -0.155in; }
.bottom { display: grid; grid-template-columns: 1.25fr 1.15fr 0.9fr; gap: 0.12in; flex: 1; }
.panel { border: 1.4px solid #adb5bd; border-radius: 8px; padding: 4px 8px; background: #fcfcfd; }
.panel h2 { font-size: 9pt; margin: 0 0 3px 0; display: flex; align-items: center; justify-content: space-between; }
pre.tree { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 6.5pt; line-height: 1.25; margin: 2px 0 4px 0;
           background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 3px 5px; white-space: pre; }
.loop { display: flex; align-items: stretch; gap: 3px; margin: 3px 0; }
.step { flex: 1; border: 1.3px solid #2f9e44; background: #ebfbee; border-radius: 6px; padding: 2px 4px; font-size: 6.6pt; }
.step b { display: block; font-size: 7.2pt; }
.loopa { align-self: center; font-weight: 700; color: #343a40; }
table.gaps { border-collapse: collapse; width: 100%; font-size: 6.4pt; line-height: 1.12; }
table.gaps td { padding: 0.3px 3px; border-bottom: 1px solid #edf0f2; vertical-align: middle; }
table.gaps .chip { font-size: 5.8pt; line-height: 1.2; padding: 0 5px; }
table.gaps td:first-child { font-weight: 700; width: 24px; } table.gaps td:last-child { text-align: right; width: 58px; }
code { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 94%; }
ul.inv { margin: 0; padding-left: 12px; font-size: 7.1pt; } ul.inv li { margin: 0 0 2px 0; }
footer { font-size: 6.4pt; color: #555; display: flex; justify-content: space-between; gap: 0.3in; }
"""


def one_page(t):
    e = html.escape

    def chip(value):
        s = status(value)
        return "" if s is None else f'<span class="chip s-{s.replace(" ", "-")}">{e(s)}</span>'

    def box(x):
        title = smart(x["name"]) + (f" \u2014 {smart(tagline(x))}" if tagline(x) else "")
        inner = t["inner"][x["n"]]
        if not inner:
            return (f'<div class="layer f-{x["color"]}"><div class="h"><span class="t"><span class="n">{x["n"]}</span>'
                    f'{e(title)}</span>{chip(x["health"])}</div><div>{e(joined(x))}</div></div>')
        cells = "".join(f'<div class="cell"><div class="h"><span class="t">{e(smart(p["name"]))}</span>'
                        f'{chip(p["health"])}</div><div>{e(joined(p))}</div></div>' for p in inner)
        return (f'<div class="device f-{x["color"]}"><div class="h"><span class="t"><span class="n">{x["n"]}</span>'
                f'{e(title)}</span></div><div class="cells" style="grid-template-columns: repeat({len(inner)}, 1fr)">'
                f'{cells}</div></div>')

    def side(p):
        if p is None:
            return "<div></div>"
        ways = {c["arrow"] for c in t["crossing"] if c.get("side") is p}
        inward, outward = bool(ways & {"in", "both"}), bool(ways & {"out", "both"})
        glyph = "\u2194" if inward and outward else "\u2192" if inward == (p["col"] == "in") else "\u2190"
        arrow = f' data-a="{glyph}"' if ways else ""
        return (f'<div class="side {p["col"]}"{arrow}><div class="h"><span class="t">{e(smart(p["name"]))}</span>'
                f'{chip(p["health"])}</div><div>{e(joined(p))}</div></div>')

    def conn(n):
        inner = t["inner"][n] + t["inner"][n - 1]
        order = lambda c: next((k for k, p in enumerate(inner) if p in (c["upper"], c["lower"])), len(inner) / 2)
        spans = []
        for c in sorted((c for c in t["crossing"] if c.get("upper") and c["top"] == n), key=order):
            glyph, label = {"down": "\u25bc", "up": "\u25b2", "both": "\u25b2\u25bc"}[c["arrow"]], e(smart(plain(c["label"])))
            spans.append(f'<span class="red"><b>\u250a{glyph}</b>{label} \u2014 <b>GAP {c["gap"]}</b>: no specification '
                         "allows it yet</span>" if c["red"] else f"<span><b>{glyph}</b>{label}</span>")
        return f'<div></div><div class="conn">{"".join(spans)}</div><div></div>'

    slot = {}
    for col in ("in", "out"):
        for p in (p for p in t["sides"] if p["col"] == col):
            n = p["level"]
            while (col, n) in slot:
                n -= 1
            if n < 0:
                refuse(p["where"], "leaves no room beside the stack on the one-pager; change `beside`")
            slot[(col, n)] = p
    org = []
    for x in reversed(t["layer"]):
        org += [side(slot.get(("in", x["n"]))), box(x), side(slot.get(("out", x["n"])))]
        if x["n"]:
            org.append(conn(x["n"]))
    d = t["dogfood"]
    tree = [item.split(": ", 1) for item in d["tree"]]
    pad = max(len(a) for a, _ in tree) + 2
    loop = '<span class="loopa">\u2192</span>'.join(
        f'<div class="step"><b>{k} {inline(step.split(": ", 1)[0])}</b>{inline(step.split(": ", 1)[1])}</div>'
        for k, step in enumerate(d["loop"], 1))
    gaps = "".join(f'<tr><td>{e(g["id"])}</td><td>{inline(g["gap"])}</td><td>{chip(g["status"])}</td></tr>'
                   for g in sorted(t["gap"], key=lambda g: int(g["id"][1:])))
    rules = "".join(f"<li><b>{inline(lead)}</b> {inline(rest)}</li>" for lead, rest in t["invariants"]["rules"])
    css = CSS + "".join(f".s-{k.replace(' ', '-')} {{ background: {f}; border-color: {s}; }}\n"
                        for k, (s, f) in STATUS.items())
    css += "".join(f".f-{k} {{ --s: {s}; --f: {f}; }}\n" for k, (s, f) in FAMILY.items())
    legend = " ".join(chip(k) for k in ("in force", "experimental", "proposed", "open", "planned"))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>The RAPP/1 organism, on one page</title>
<!-- Generated from organism/ by tools/build.py. Edit the part files and rebuild. -->
<style>
{css}</style>
</head>
<body>
<div class="page">
<header>
<div><h1>The RAPP/1 organism, on one page</h1>
<div class="sub">Read it bottom (0) to top (6). Left: what comes in. Right: what goes out or across. Bottom: how we dogfood it, what is still open, and what holds everywhere.</div></div>
<div class="legend"><div>{legend}</div><div><span class="gapline"></span>red dashed: a crossing no specification allows yet</div></div>
</header>
<section class="org">
{chr(10).join(org)}
</section>
<section class="bottom">
<div class="panel"><h2>{e(smart(d["name"]))} {chip(d["health"])}</h2>
<pre class="tree">{e(chr(10).join(smart(a).ljust(pad) + smart(b) for a, b in tree))}</pre>
<div class="loop">{loop}<span class="loopa">\u21bb</span></div>
<div>{inline(d["body"])}</div></div>
<div class="panel"><h2>Gap register (the way to fully healthy)</h2>
<table class="gaps">{gaps}</table></div>
<div class="panel"><h2>What holds everywhere</h2>
<ul class="inv">{rules}</ul></div>
</section>
<footer><span>Experimental map, generated from the organism/ tree \u00b7 details: ECOSYSTEM.md and CONSTITUTION.md in kody-w/rapp-work (branch experimental/rapp-work-constitution) \u00b7 model Hive: kody-w/rapp-model-hive (experimental/hive-md)</span>
<span>Specifications decide; this page only points at them.</span></footer>
</div>
</body>
</html>
"""


# ---- the genome and the long-form map ------------------------------------------------------------

def arrow(c):
    return "\u2194" if c["arrow"] == "both" else "\u2192"


def table(head, rows):
    return ["", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def genome(t, graph):
    def ref(x, folder):
        return f"[{x['name']}]({folder}/{x['stem']}.md)"

    inv, d, gaps = t["invariants"], t["dogfood"], sorted(t["gap"], key=lambda g: int(g["id"][1:]))
    L = ["<!-- GENERATED by tools/build.py from the part files in this folder. Do not edit by hand. -->", "",
         "# The RAPP/1 organism", "",
         "The whole organism on one page, generated from this folder's part files, one fact per file. "
         "Specifications decide; it only points at them. Experimental.", "",
         "**To change it,** edit a part file, then run `python3 tools/build.py` (`--check` proves nothing "
         "drifted).", "", "```text", graph.rstrip("\n"), "```", "", "## Layers, bottom to top"]
    L += table(["#", "Layer", "What it is", "Health"],
               [[str(x["n"]), ref(x, "layers"), x["role"], x["health"]] for x in t["layer"]])
    L += ["", "## Parts"] + table(["Part", "Where", "What it is", "Health"], [
        [ref(p, "parts"), f"{p['column']}, beside {p['level']}" if p["col"] else f"inside {p['level']}",
         p["role"], p["health"]] for p in [p for n in range(7) for p in t["inner"][n]] + t["sides"]])
    L += ["", "## Crossings"] + table(["From \u2192 to", "What crosses", "Authorized by", "Health"], [
        [f"[{t['ids'][c['from']]['name']} {arrow(c)} {t['ids'][c['to']]['name']}](crossings/{c['stem']}.md)",
         c["what"], c["authorized_by"], c["health"]] for c in t["crossing"]])
    L += ["", "## Gaps (fixes in each file)"] + table(
        ["ID", "Gap", "Status"], [[f"[{g['id']}](gaps/{g['stem']}.md)", g["gap"], g["status"]] for g in gaps])
    L += ["", "## Journeys"] + table(
        ["ID", "Journey"], [[f"[{j['id']}](journeys/{j['id']}.md)", j["title"]] for j in t["journey"]])
    L += ["", "## What holds everywhere", ""] + [f"- **{lead}** {rest}".rstrip() for lead, rest in inv["rules"]]
    L += ["", inv["healthy"], "", f"[{d['name']}](dogfood.md) ({d['health']}): where the organism is tried for real.",
          "", "## How to adapt it", "",
          "- **Change a fact:** edit the one file that holds it.",
          "- **Move a part:** change its `beside` or `layer`; every view follows.",
          "- **Add a crossing:** add a file to `crossings/`; the builder checks both ends.",
          "- **Close a gap:** change its `status` and the `health` that names it.",
          "- **Make your own:** copy the folder and change the facts.",
          f"- {inv['upstream']}", ""]
    return "\n".join(L)


def ecosystem(t):
    inv, gaps = t["invariants"], sorted(t["gap"], key=lambda g: int(g["id"][1:]))
    L = [MARK, "", "# The RAPP/1 organism, bottom to top", "",
         "> **Generated from [`organism/`](organism/).** Do not edit this file by hand: edit the part files there, "
         "then run `python3 organism/tools/build.py`. The same organism on one page is its genome, "
         "[`organism/ORGANISM.md`](organism/ORGANISM.md).", "",
         "**Status: experimental map.** It describes what exists and what is proposed, and changes nothing by "
         "itself. Specifications decide; this map only points at them. Where they disagree, the specification "
         "wins. It is a companion to the draft [`CONSTITUTION.md`](CONSTITUTION.md).", "",
         "![The RAPP/1 organism, bottom to top](organism/views/organism.svg)", "",
         "**How to read the graph:**",
         "- The **center column** stacks the layers from bytes (bottom) to you (top).",
         "- The **left column** is what flows in: outside knowledge and reviewed agents.",
         "- The **right column** is what goes out or across: public copies, other organizations and releases.",
         "- **Tags** show health: *in force*, *experimental* or *gap*. A red arrow is a crossing that no "
         "specification allows yet.", "",
         "The graph is drawn from the tree, like its other views: [Excalidraw](organism/views/organism.excalidraw), "
         "[text](organism/views/graph.txt) and [one printable page](organism/views/one-page.html).", "",
         "## 1. The layers, bottom to top"]
    L += table(["#", "Layer", "What it is", "Who decides", "Signed with", "Home", "Health"],
               [[str(x["n"]), f"**{x['name']}**", x["role"], x["decides"], x["signed_with"], x["home"], x["health"]]
                for x in t["layer"]])
    for x in (x for x in t["layer"] if t["inner"][x["n"]]):
        L += ["", f"Inside {lower1(x['name'])}:"] + table(["Part", "What it is", "Home", "Health"], [
            [f"**{p['name']}**", p["role"], p["home"], p["health"]] for p in t["inner"][x["n"]]])
    L += ["", "Beside the stack:"] + table(["Column", "Part", "What it is", "Home", "Health"], [
        [p["column"].capitalize(), f"**{p['name']}**", p["role"], p["home"], p["health"]] for p in t["sides"]])
    L += ["", "## 2. Crossings: how anything moves between layers", "",
          "Every arrow in the graph is one of these. Transport carries bytes; signatures decide "
          "(Constitution Article 7)."]
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
    L += ["", "## 6. Gap register"] + table(["ID", "Gap", "Home", "Proposed fix", "Status"], [
        [g["id"], g["gap"], g["home"], g["fix"], g["status"]] for g in gaps])
    L += ["", inv["upstream"], ""]
    return "\n".join(L).replace("](" + REPO, "](")  # links into the host repository become relative


# ---- build, check, print -------------------------------------------------------------------------

def build(t, root=ROOT):
    """Every generated file, as {path: bytes}. The host map is kept only where it already carries MARK."""
    graph, d = graph_txt(t), drawing(t)
    out = {root / "ORGANISM.md": genome(t, graph), root / "views/graph.txt": graph,
           root / "views/organism.svg": svg(d), root / "views/organism.excalidraw": excalidraw(d),
           root / "views/one-page.html": one_page(t)}
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
    extra = sorted(p for p in views.iterdir() if p not in outputs and p != root / PDF
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
    """Print the one-pager with headless Chrome and prove it is exactly one page."""
    exe, out = chrome(), root / PDF
    if exe is None:
        print("no Chrome or Chromium found: views/one-page.pdf was not printed")
        return 0
    out.unlink(missing_ok=True)
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={out}", (root / "views/one-page.html").as_uri()],
                       capture_output=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        pass
    if not out.is_file():
        refuse(show(out, root), "Chrome did not print it")
    pages = len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", out.read_bytes()))
    if pages != 1:
        refuse(show(out, root), f"has {pages} pages; the one-pager must fit one US Letter landscape page")
    print(f"printed {show(out, root)}: 1 page")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build every view of the organism from its part files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="rebuild in memory; exit 1 if anything drifted")
    mode.add_argument("--pdf", action="store_true", help="also print views/one-page.pdf with headless Chrome")
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
