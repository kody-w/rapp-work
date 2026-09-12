#!/usr/bin/env python3
"""Append a rapp/1 frame to a rapp-projects stream — lease-aware, multi-operator safe.

The frame files under projects/<slug>/frames/ are the authority; everything
else (index.json, BOARD.md, docs) is a derived projection. This writer uses
the rapp-1 reference implementation for canonical hashing — never hand-roll.

Concurrency model (rapp-projects/PROTOCOL.md + DISTRIBUTED.md):
  work.punchin opens a lease (actor + lease_expires_utc); work.heartbeat
  extends it; work.handoff / work.punchout release it; work.takeover claims a
  stream ONLY after the prior lease expired or was handed off. While another
  actor holds an unexpired lease, every mutating append is refused. With
  RAPP_REQUIRE_LEASE=1 (mandatory in distributed mode; auto-forced when the
  workspace rappid.json declares mode "hive") even solo appends require
  holding the lease.

HONESTY NOTE: among CONFORMING writers the lease arbitrates and the chain's
duplicate-seq check deterministically DETECTS any fork (including the offline
double-punchin race). Actor ids are unauthenticated free text and local frames
are unsigned (rapp/1 requires signatures only on net:/swarm streams), so
against a spoofing or non-conforming writer the guarantee is detection plus
git review — not prevention. Frame-signing for hive mode is future work.

Usage:
  append_frame.py --project <slug> --event <kind> [--payload '<json>'] [--actor ID]
  append_frame.py --genesis --project <slug> --title T --goal G [--owner O]
  append_frame.py --punchin --project <slug> --actor ID [--intent TEXT] [--lease-minutes N]
  append_frame.py --heartbeat|--handoff|--punchout --project <slug> --actor ID
  append_frame.py --takeover --project <slug> --actor ID [--reason TEXT]
  append_frame.py --verify  --project <slug> | --verify --all
  append_frame.py --lease   --project <slug>          # show lease state

Env: RAPP_ACTOR (default actor id), RAPP_REQUIRE_LEASE=1 (strict mode),
     RAPP_PROJECTS_ROOT (override root; testing only).
"""
import argparse, glob, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAPP1 = os.path.expanduser(os.environ.get("RAPP1_PATH", "~/rapp-1"))
sys.path.insert(0, RAPP1)
import rapp  # noqa: E402

SCRIPT_PATH = Path(__file__).resolve()


def find_workspace_root():
    for candidate in (SCRIPT_PATH.parent, *SCRIPT_PATH.parents):
        if (candidate / "rappid.json").is_file():
            return candidate
    return None


WORKSPACE_ROOT = find_workspace_root()
if os.environ.get("RAPP_PROJECTS_ROOT"):
    ROOT = os.environ["RAPP_PROJECTS_ROOT"]
elif WORKSPACE_ROOT is not None and (WORKSPACE_ROOT / "rapp-projects").is_dir():
    ROOT = str(WORKSPACE_ROOT / "rapp-projects")
else:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LEASE_EVENTS = {"work.punchin", "work.heartbeat", "work.handoff",
                "work.takeover", "work.punchout"}
DEFAULT_LEASE_MIN = 60


def now_dt():
    return datetime.now(timezone.utc)


def fmt_utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}" + "Z"


def project_dir(slug):
    return os.path.join(ROOT, "projects", slug)


def read_chain(slug):
    frames = []
    for f in sorted(glob.glob(os.path.join(project_dir(slug), "frames", "*.json"))):
        try:
            with open(f) as fh:
                frames.append((f, json.load(fh)))
        except (json.JSONDecodeError, OSError) as e:
            raise SystemExit(f"CHAIN UNREADABLE at {os.path.basename(f)}: {e} — "
                             f"a partial/corrupt frame; restore it from git or quarantine "
                             f"it per DISTRIBUTED.md before continuing.")
    return frames


def verify_chain(slug):
    """Verify the full chain; detect forks (duplicate seq) explicitly."""
    entries = read_chain(slug)
    seen_seq = {}
    for path, fr in entries:
        if fr["seq"] in seen_seq:
            raise SystemExit(
                f"CHAIN FORKED at seq {fr['seq']}: {os.path.basename(seen_seq[fr['seq']])} "
                f"vs {os.path.basename(path)} — two writers appended without the lease. "
                f"Recover per rapp-projects/DISTRIBUTED.md §Fork recovery.")
        seen_seq[fr["seq"]] = path
    rid = json.load(open(os.path.join(project_dir(slug), "rappid.json")))["rappid"]
    head = None
    for path, fr in entries:
        ok, step, reason = rapp.verify_frame(fr, head=head, stream_id_of_record=rid)
        if not ok:
            raise SystemExit(f"CHAIN BROKEN at seq {fr['seq']} ({os.path.basename(path)}): "
                             f"step {step}: {reason}")
        head = fr
    return [fr for _, fr in entries]


def lease_state(chain):
    """Derive (holder_actor_id, expires_utc_str, open) from the chain."""
    holder, expires, is_open = None, None, False
    for fr in chain:
        p = fr.get("payload", {})
        ev = p.get("event")
        if ev in ("work.punchin", "work.takeover"):
            holder = (p.get("actor") or {}).get("id")
            expires = p.get("lease_expires_utc")
            is_open = True
        elif ev == "work.heartbeat" and is_open:
            expires = p.get("lease_expires_utc", expires)
        elif ev in ("work.handoff", "work.punchout"):
            is_open = False
    return holder, expires, is_open


_UTC_FORM = None
def _utc_valid(s):
    global _UTC_FORM
    if _UTC_FORM is None:
        import re
        _UTC_FORM = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    return isinstance(s, str) and bool(_UTC_FORM.match(s))


def lease_active(chain):
    holder, expires, is_open = lease_state(chain)
    if not is_open or holder is None:
        return None, None
    # A missing or malformed expiry must NEVER create an immortal lease:
    # treat it as already expired so the stream stays takeover-able.
    if not _utc_valid(expires):
        return None, (holder, expires or "<missing>")
    if fmt_utc(now_dt()) > expires:
        return None, (holder, expires)          # expired — takeover allowed
    return (holder, expires), None


def strict_mode():
    """Strict when env-set OR when the enclosing workspace declares mode:hive."""
    if os.environ.get("RAPP_REQUIRE_LEASE") == "1":
        return True
    try:
        root = WORKSPACE_ROOT
        if root is None:
            candidate = Path(ROOT).resolve()
            root = candidate.parent if candidate.name == "rapp-projects" else candidate
        with open(root / "rappid.json") as fh:
            return json.load(fh).get("mode") == "hive"
    except (OSError, json.JSONDecodeError):
        return False


def check_lease(chain, event, actor):
    """Enforce the concurrency rules. Raises SystemExit on refusal."""
    active, expired = lease_active(chain)
    strict = strict_mode()
    if event == "work.punchin":
        if active:
            raise SystemExit(f"REFUSED: {active[0]} holds an active lease until {active[1]}. "
                             f"Wait, request a handoff, or take over after expiry.")
        return
    if event == "work.takeover":
        if active:
            raise SystemExit(f"REFUSED: cannot take over an ACTIVE lease "
                             f"({active[0]} until {active[1]}). Takeover requires expiry or handoff.")
        return
    # heartbeat / handoff / punchout / plain mutating events:
    if active:
        if actor != active[0]:
            raise SystemExit(f"REFUSED: {active[0]} holds the lease until {active[1]}; "
                             f"you are '{actor}'. No toe-stepping.")
        return
    if event in ("work.heartbeat", "work.handoff", "work.punchout"):
        raise SystemExit(f"REFUSED: no active lease to {event.split('.')[1]} "
                         f"(expired lease: {expired[0] if expired else 'none'}). Punch in first.")
    if strict:
        raise SystemExit("REFUSED: strict lease mode (RAPP_REQUIRE_LEASE=1 or hive "
                         "workspace) — punch in before appending.")


def write_frame(slug, frame):
    fdir = os.path.join(project_dir(slug), "frames")
    os.makedirs(fdir, exist_ok=True)
    name = f"{frame['seq']:020d}-{frame['frame_hash']}.json"
    fd, tmp = tempfile.mkstemp(dir=fdir, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps(frame, sort_keys=True, separators=(",", ":")))
        f.flush()
        os.fsync(f.fileno())                    # durability before the rename
    os.rename(tmp, os.path.join(fdir, name))    # atomic naming
    try:
        dfd = os.open(fdir, os.O_RDONLY)
        os.fsync(dfd); os.close(dfd)            # persist the directory entry
    except OSError:
        pass
    return name


def append(slug, event, payload, actor):
    chain = verify_chain(slug)
    if not chain:
        raise SystemExit(f"{slug}: no genesis — run --genesis first")
    check_lease(chain, event, actor)
    head = chain[-1]
    body = dict(payload or {})
    body.setdefault("event", event)
    body.setdefault("project", slug)
    if actor and "actor" not in body:
        body["actor"] = {"id": actor}
    # Monotonic stamp: a fast-clock peer's head must not lock slower clocks out
    # (rapp/1 step 4 refuses utc < head.utc). Bump to head.utc + 1ms if needed.
    utc = fmt_utc(now_dt())
    if utc <= head["utc"]:
        base = datetime.strptime(head["utc"], "%Y-%m-%dT%H:%M:%S.%fZ")
        utc = fmt_utc(base.replace(tzinfo=timezone.utc) + timedelta(milliseconds=1))
    frame = rapp.build_frame("body.pulse", head["stream_id"], head["seq"] + 1,
                             utc, body, prev=head["payload_hash"])
    ok, step, reason = rapp.verify_frame(frame, head=head,
                                         stream_id_of_record=head["stream_id"])
    if not ok:
        raise SystemExit(f"refusing to write invalid frame: step {step}: {reason}")
    return write_frame(slug, frame)


def genesis(slug, title, goal, owner):
    pdir = project_dir(slug)
    if os.path.exists(os.path.join(pdir, "rappid.json")):
        raise SystemExit(f"{slug} already exists (mint-once: reuse the stored rappid)")
    os.makedirs(os.path.join(pdir, "frames"), exist_ok=True)
    rid = rapp.mint_rappid("rapp-projects", slug)
    if not rapp.rappid_valid(rid):
        raise SystemExit(f"minted rappid failed validation: {rid}")
    with open(os.path.join(pdir, "rappid.json"), "w") as f:
        json.dump({"schema": "rapp/1", "rappid": rid, "kind": "project",
                   "name": title, "frames": "frames/"}, f, indent=2)
        f.write("\n")
    payload = {"event": "project.genesis", "project": slug, "title": title,
               "goal": goal, "owner": owner, "visibility": "local",
               "origin": f"{now_dt().date()} genesis"}
    frame = rapp.build_frame("body.pulse", rid, 0, fmt_utc(now_dt()), payload, prev=None)
    ok, step, reason = rapp.verify_frame(frame, head=None, stream_id_of_record=rid)
    if not ok:
        raise SystemExit(f"refusing to write invalid genesis: step {step}: {reason}")
    return write_frame(slug, frame)


def all_slugs():
    return sorted(os.path.basename(d) for d in glob.glob(os.path.join(ROOT, "projects", "*"))
                  if os.path.isdir(os.path.join(d, "frames")))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project")
    ap.add_argument("--event")
    ap.add_argument("--payload", default="{}")
    ap.add_argument("--actor", default=os.environ.get("RAPP_ACTOR"))
    ap.add_argument("--genesis", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--lease", action="store_true")
    ap.add_argument("--punchin", action="store_true")
    ap.add_argument("--heartbeat", action="store_true")
    ap.add_argument("--handoff", action="store_true")
    ap.add_argument("--takeover", action="store_true")
    ap.add_argument("--punchout", action="store_true")
    ap.add_argument("--intent", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--lease-minutes", type=int, default=DEFAULT_LEASE_MIN)
    ap.add_argument("--title")
    ap.add_argument("--goal")
    ap.add_argument("--owner", default="the workspace owner")
    a = ap.parse_args()

    if a.verify and a.all:
        bad = 0
        for slug in all_slugs():
            try:
                n = len(verify_chain(slug))
                print(f"OK   {slug}: {n} frames")
            except SystemExit as e:
                bad += 1
                print(f"FAIL {slug}: {e}")
        sys.exit(1 if bad else 0)
    if not a.project:
        ap.error("--project required")
    if a.verify:
        print(f"OK {a.project}: {len(verify_chain(a.project))} frames verify")
        sys.exit(0)
    if a.lease:
        chain = verify_chain(a.project)
        active, expired = lease_active(chain)
        if active:
            print(f"LEASED {a.project}: {active[0]} until {active[1]}")
        elif expired:
            print(f"EXPIRED {a.project}: {expired[0]} lapsed at {expired[1]} — takeover allowed")
        else:
            print(f"FREE {a.project}: no active lease")
        sys.exit(0)
    if a.genesis:
        print(f"GENESIS {genesis(a.project, a.title, a.goal, a.owner)}")
        sys.exit(0)

    lease_flags = [a.punchin, a.heartbeat, a.handoff, a.takeover, a.punchout]
    if sum(lease_flags) > 1:
        ap.error("pick one of --punchin/--heartbeat/--handoff/--takeover/--punchout")
    if any(lease_flags):
        if not a.actor:
            ap.error("--actor (or RAPP_ACTOR) required for lease operations")
        ev = ("work.punchin" if a.punchin else "work.heartbeat" if a.heartbeat
              else "work.handoff" if a.handoff else "work.takeover" if a.takeover
              else "work.punchout")
        payload = json.loads(a.payload)
        payload["event"] = ev
        payload.setdefault("actor", {"id": a.actor})
        if ev in ("work.punchin", "work.takeover", "work.heartbeat"):
            payload["lease_expires_utc"] = fmt_utc(now_dt() + timedelta(minutes=a.lease_minutes))
        if a.intent:
            payload.setdefault("intent", a.intent)
        if a.reason:
            payload.setdefault("reason", a.reason)
        print(f"APPEND {append(a.project, ev, payload, a.actor)}")
        sys.exit(0)

    if not a.event:
        ap.error("--event required")
    if a.event in LEASE_EVENTS:
        ap.error(f"use the dedicated flag for {a.event} (e.g. --punchin)")
    print(f"APPEND {append(a.project, a.event, json.loads(a.payload), a.actor)}")
