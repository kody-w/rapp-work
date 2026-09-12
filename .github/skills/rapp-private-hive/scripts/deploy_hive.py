#!/usr/bin/env python3
"""Deploy approved single-owner RAPP Private Hive artifacts; never execute them."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def verify_lock():
    lock = json.loads((ROOT / "rapp" / "agent.lock.json").read_text(encoding="utf-8"))
    required = {"SKILL.md", "DEPLOYMENT.md", "requirements.txt", "requirements-test.txt"}
    for directory in ("scripts", "lib", "schemas", "tests", "vendor"):
        required.update(path.relative_to(ROOT).as_posix() for path in (ROOT / directory).rglob("*")
                        if path.is_file() and "__pycache__" not in path.parts
                        and path.suffix in {".py", ".json", ".md", ".txt"})
    entries = lock.get("files", [])
    if lock.get("schema") != "rapp-skill-lock/1" or [item.get("path") for item in entries] != sorted(required):
        raise ValueError("skill checksum lock file set is incomplete or noncanonical")
    for item in entries:
        if set(item) != {"path", "sha256"}:
            raise ValueError("invalid checksum lock entry")
        path = ROOT / item["path"]
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != ROOT.parent):
            raise ValueError("symlinked skill code refused")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("skill checksum lock mismatch: " + item["path"])
    expected = hashlib.sha256((ROOT / "vendor" / "hive" / "SPEC.md").read_bytes()).hexdigest()
    if lock["protocol"]["spec_sha256"] != expected:
        raise ValueError("pinned Hive specification checksum mismatch")
    return {"status": "verified-skill-lock", "version": lock["version"], "files": len(entries)}


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--preflight", action="store_true", help="verify every locked skill and vendored protocol byte")
    groups = root.add_subparsers(dest="group")

    key = groups.add_parser("key", aliases=["keys"]).add_subparsers(dest="operation", required=True)
    create = key.add_parser("create")
    create.add_argument("--key-dir", type=Path, required=True)
    create.add_argument("--owner-label", required=True)
    create.add_argument("--slug", default="owner")
    load = key.add_parser("load")
    load.add_argument("--key-dir", type=Path, required=True)
    load.add_argument("--expected-rappid", required=True)

    auth = groups.add_parser("authority").add_subparsers(dest="operation", required=True)
    for name in ("init", "import"):
        command = auth.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--publisher-dir", type=Path, required=True)
        command.add_argument("--key-dir", type=Path, required=True)
        command.add_argument("--channels", type=Path, required=True)
        command.add_argument("--adopt-prepared-owner")
        command.add_argument("--created-utc")
        if name == "import":
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument("--source", type=Path, help="existing filesystem publication, read only")
            source.add_argument("--source-channel-id", help="existing private GitHub channel in --channels")
            command.add_argument("--read-state-dir", type=Path, help="explicit isolated Git read cache, outside workspace/custody/state")
            command.add_argument("--github-evidence", type=Path)
            command.add_argument("--anchor", type=Path, required=True, help="separately supplied existing anchor")
            command.add_argument("--expected-spki-sha256", required=True)
    export = auth.add_parser("anchor")
    export.add_argument("--publisher-dir", type=Path, required=True)
    export.add_argument("--out", type=Path)

    releases = groups.add_parser("release").add_subparsers(dest="operation", required=True)
    for name in ("build", "show", "approve", "publish", "status", "discard"):
        command = releases.add_parser(name)
        command.add_argument("--publisher-dir", type=Path, required=True)
        if name in {"build", "approve", "publish"}:
            command.add_argument("--key-dir", type=Path, required=True)
        if name in {"show", "approve", "publish", "discard"}:
            command.add_argument("--plan-hash", required=True, help="exact reviewed immutable plan SHA-256")
        if name == "build":
            command.add_argument("--stage-root", type=Path, required=True)
            command.add_argument("--expected-ref", action="append", default=[], metavar="CHANNEL=OID|absent")
            command.add_argument("--created-utc")
        if name == "publish":
            command.add_argument("--github-evidence", type=Path,
                                 help="explicit operator-supplied API evidence; gh still provides credentials")

    clients = groups.add_parser("client").add_subparsers(dest="operation", required=True)
    for name in ("init", "pull", "verify", "materialize"):
        command = clients.add_parser(name)
        command.add_argument("--client-dir", type=Path, required=True)
        if name == "init":
            command.add_argument("--anchor", type=Path, required=True)
            command.add_argument("--expected-spki-sha256", required=True)
        if name == "pull":
            command.add_argument("--channels", type=Path, required=True)
            command.add_argument("--channel-id", required=True)
            command.add_argument("--github-evidence", type=Path)
        if name in {"materialize", "verify"}:
            command.add_argument("--destination", type=Path, required=name == "materialize")
    for name in ("sharepoint", "public-git", "federation", "seal", "key-release", "rotate-owner", "topology"):
        command = groups.add_parser(name)
        command.add_argument("arguments", nargs=argparse.REMAINDER)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    unsupported = {"sharepoint", "public-git", "federation", "seal", "key-release", "rotate-owner", "topology"}
    if args.group in unsupported:
        raise ValueError("unsupported operation refused before effects: " + args.group)
    preflight = verify_lock()
    if args.preflight:
        print(json.dumps(preflight, sort_keys=True))
        return 0
    if args.group is None:
        raise ValueError("choose an explicit deployment workflow or --preflight")
    sys.path.insert(0, str(ROOT / "lib"))
    from private_hive import client, keys, release
    from private_hive.authority import validate_channels
    from private_hive.bundle import verify_bundle
    from private_hive.common import R, canonical, digest, exact_keys, paths_disjoint, read_file, require
    from private_hive.state import State
    from private_hive.adapters.filesystem import Filesystem
    from private_hive.adapters.github_git import GitHubCLI, GitHubGit

    def channels(path):
        document = R._strict_json(read_file(path))
        exact_keys(document, {"schema", "channels"}, "channel configuration")
        require(document["schema"] == "rapp-private-hive-channels/1", "wrong channels schema")
        return validate_channels(document["channels"])

    def provider(path):
        if path is None:
            return None
        class SnapshotEvidence(GitHubCLI):
            def __call__(self, config):
                return R._strict_json(read_file(path))
        return SnapshotEvidence()

    if args.group in {"key", "keys"}:
        key = (keys.create(args.key_dir, args.owner_label, args.slug) if args.operation == "create"
               else keys.load(args.key_dir, expected_rappid=args.expected_rappid))
        result = {"status": "created" if args.operation == "create" else "loaded",
                  "owner_rappid": key.rappid, "spki_sha256": digest(key.spki)}
    elif args.group == "authority":
        if args.operation == "anchor":
            result = release.export_anchor(args.publisher_dir, args.out)
        else:
            configuration = channels(args.channels)
            key = keys.load(args.key_dir)
            imported = None
            if args.operation == "import":
                anchor_raw = read_file(args.anchor)
                anchor = keys.verify_anchor(anchor_raw)
                require(anchor["spki_sha256"] == args.expected_spki_sha256, "existing owner fingerprint mismatch")
                if args.source is not None:
                    source = Filesystem(args.source)
                    pointer = source.current()
                    require(pointer is not None, "source has no existing authority")
                    imported = verify_bundle(anchor_raw, pointer, source.read)
                else:
                    selected = [item for item in configuration if item["id"] == args.source_channel_id and item["kind"] == "github"]
                    require(len(selected) == 1 and args.read_state_dir is not None,
                            "GitHub import requires an exact GitHub channel and an explicit --read-state-dir")
                    paths_disjoint(args.workspace, args.publisher_dir, args.key_dir, args.read_state_dir)
                    source = GitHubGit(selected[0], args.read_state_dir, evidence_provider=provider(args.github_evidence))
                    with source.snapshot() as (read, ref):
                        imported = verify_bundle(anchor_raw, read("refs/current.json"), read)
            result = release.initialize(args.workspace, args.publisher_dir, key, configuration,
                                        adopt_prepared_owner=args.adopt_prepared_owner, created_utc=args.created_utc,
                                        imported=imported)
    elif args.group == "release":
        if args.operation == "status":
            result = release.status(args.publisher_dir)
        elif args.operation == "show":
            snapshot = State.readonly_snapshot(args.publisher_dir)
            state = State(args.publisher_dir, "publisher")
            with state.transaction() as db:
                frozen = State.release(db, args.plan_hash)
                release.frozen(snapshot, args.plan_hash, frozen)
                result = {"plan_hash": args.plan_hash, "plan": frozen["plan"], "approval": frozen["approval"]}
        elif args.operation == "discard":
            result = release.discard(args.publisher_dir, args.plan_hash)
        else:
            snapshot = State.readonly_snapshot(args.publisher_dir)
            key = keys.load(args.key_dir, expected_rappid=snapshot["config"]["owner_rappid"])
            if args.operation == "build":
                pairs = [value.split("=", 1) for value in args.expected_ref]
                require(all(len(pair) == 2 for pair in pairs) and len({pair[0] for pair in pairs}) == len(pairs),
                        "expected refs must be unique CHANNEL=OID entries")
                result = release.build(args.publisher_dir, key, args.stage_root, expected_refs=dict(pairs),
                                       created_utc=args.created_utc)
            elif args.operation == "approve":
                result = release.approve(args.publisher_dir, key, args.plan_hash)
            else:
                result = release.publish(args.publisher_dir, key, args.plan_hash,
                                         evidence_provider=provider(args.github_evidence))
    else:
        if args.operation == "init":
            result = client.initialize(args.client_dir, read_file(args.anchor),
                                       expected_spki_sha256=args.expected_spki_sha256)
        elif args.operation == "pull":
            configuration = channels(args.channels)
            selected = [item for item in configuration if item["id"] == args.channel_id]
            require(len(selected) == 1, "explicit channel not in configuration")
            result = client.pull(args.client_dir, selected[0], evidence_provider=provider(args.github_evidence))
        elif args.operation == "materialize":
            result = client.materialize(args.client_dir, args.destination)
        else:
            result = client.verify(args.client_dir, args.destination)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, RuntimeError, KeyError, TypeError, IndexError, RecursionError, ImportError) as error:
        print(json.dumps({"status": "refused", "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
