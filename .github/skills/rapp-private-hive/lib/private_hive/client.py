from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import uuid

from .authority import channel_declaration, validate_channels
from .bundle import verify_bundle
from .common import canonical, digest, exact_keys, locked, no_symlinks, parse, paths_disjoint, private_directory, read_file, require, sync_directory, write_file
from .keys import verify_anchor
from .state import State
from .adapters.filesystem import Filesystem
from .adapters.github_git import GitHubGit


def initialize(directory: Path, anchor_raw: bytes, *, expected_spki_sha256: str):
    anchor = verify_anchor(anchor_raw)
    require(anchor["spki_sha256"] == expected_spki_sha256, "out-of-band owner fingerprint mismatch")
    directory = no_symlinks(Path(directory))
    if (directory / "state.sqlite3").exists():
        snapshot = State.readonly_snapshot(directory)
        require(snapshot.get("role") == {"role": "client"} and snapshot.get("anchor") == anchor,
                "existing client trust anchor differs; owner rotation is unsupported")
        return {"status": "already-initialized", "hive_rappid": anchor["hive_rappid"]}
    state = State(directory, "client", create=True)
    with state.transaction() as db:
        require(State.get(db, "anchor") is None, "concurrent client initialization refused")
        State.set(db, "anchor", anchor)
        State.set(db, "client", {"id": uuid.uuid4().hex})
    return {"status": "initialized-from-out-of-band-anchor", "hive_rappid": anchor["hive_rappid"]}


@contextmanager
def source(channel, state_directory: Path, *, adapter=None, evidence_provider=None):
    validate_channels([{**channel, "role": "authority"}])
    if adapter is None:
        adapter = (Filesystem(Path(channel["path"])) if channel["kind"] == "filesystem"
                   else GitHubGit(channel, state_directory / ("git-" + channel["id"]), evidence_provider=evidence_provider))
    if channel["kind"] == "filesystem":
        paths_disjoint(state_directory, Path(channel["path"]))
        pointer = adapter.current()
        require(pointer is not None, "channel has no current publication")
        yield pointer, adapter.read, None
    else:
        with adapter.snapshot() as (read, ref):
            yield read("refs/current.json"), read, ref


def pull(directory: Path, channel: dict, *, adapter=None, evidence_provider=None, fault=None):
    snapshot = State.readonly_snapshot(directory)
    require(snapshot.get("role") == {"role": "client"} and "anchor" in snapshot, "initialize a client with an independent anchor first")
    with source(channel, Path(directory), adapter=adapter, evidence_provider=evidence_provider) as (pointer, read, ref):
        verified = verify_bundle(canonical(snapshot["anchor"]), pointer, read, checkpoint=snapshot.get("checkpoint"))
    require(channel_declaration(channel) in verified.gate._declaration["channels"],
            "transport does not match the signed channel declaration")
    pointer_hash = digest(pointer)
    state = State(directory, "client")
    with state.transaction() as db:
        require(State.get(db, "checkpoint") == snapshot.get("checkpoint"), "concurrent pull advanced client state; retry")
        existing = db.execute("SELECT pointer FROM releases WHERE plan_hash=?", (pointer_hash,)).fetchone()
        if existing is not None:
            local = State.release(db, pointer_hash)
            require(local["pointer"] == pointer and local["files"] == verified.files, "cached authenticated bytes changed")
            return {"status": "unchanged", "pointer_sha256": pointer_hash, "files": len(verified.materialized), "ref": ref}
        plan = {"schema": "rapp-private-hive-client-cache/1", "pointer_sha256": pointer_hash}
        db.execute("INSERT INTO releases(plan_hash,input_hash,plan,pointer,complete) VALUES(?,?,?,?,1)",
                   (pointer_hash, pointer_hash, canonical(plan), pointer))
        db.executemany("INSERT INTO release_files(plan_hash,path,content) VALUES(?,?,?)",
                       [(pointer_hash, path, raw) for path, raw in sorted(verified.files.items())])
        State.set(db, "accepted", {"pointer_sha256": pointer_hash})
        State.set(db, "checkpoint", verified.checkpoint())
        if fault:
            fault("before-client-commit")
    return {"status": "pulled-and-verified", "pointer_sha256": pointer_hash, "files": len(verified.materialized), "ref": ref}


def cached(directory: Path):
    snapshot = State.readonly_snapshot(directory)
    require(snapshot.get("accepted") is not None, "client has no authenticated publication")
    state = State(directory, "client")
    with state.transaction() as db:
        local = State.release(db, snapshot["accepted"]["pointer_sha256"])
    verified = verify_bundle(canonical(snapshot["anchor"]), local["pointer"], local["files"].__getitem__,
                             checkpoint=snapshot["checkpoint"])
    return snapshot, verified


def _manifest(verified):
    return {"schema": "rapp-private-hive-materialized-generation/1", "pointer_sha256": digest(verified.pointer_bytes),
            "release_seq": verified.pointer["release_seq"],
            "files": [{"path": path, "bytes": len(raw), "sha256": digest(raw)}
                      for path, raw in sorted(verified.materialized.items())]}


def _check_generation(root, manifest, materialized):
    private_directory(root)
    expected = set(materialized) | {".generation.json", ".building.json"}
    actual = set()
    for path in root.rglob("*"):
        no_symlinks(path)
        if path.is_dir():
            private_directory(path)
        else:
            name = path.relative_to(root).as_posix()
            require(name in expected, "unmanaged materialized file")
            actual.add(name)
            wanted = (canonical(manifest) if name == ".generation.json" else
                      canonical({"pointer_sha256": manifest["pointer_sha256"]}) if name == ".building.json"
                      else materialized[name])
            require(read_file(path, private=True) == wanted, "materialized file modified or corrupt")
    require(actual == expected, "materialized generation is incomplete")


def materialize(directory: Path, destination: Path, *, fault=None):
    snapshot, verified = cached(directory)
    state = State(directory, "client")
    destination = no_symlinks(Path(destination))
    require(destination != Path(directory).absolute() and destination not in Path(directory).absolute().parents,
            "materialization cannot overwrite client state or its parent")
    owner = {"schema": "rapp-private-hive-managed-output/1", "client_id": snapshot["client"]["id"],
             "anchor_sha256": digest(canonical(snapshot["anchor"]))}
    if destination.exists():
        private_directory(destination)
        require((destination / ".hive-managed.json").exists()
                and read_file(destination / ".hive-managed.json", private=True) == canonical(owner),
                "unmanaged destination or different client; never overwrite it")
    else:
        private_directory(destination, create=True)
        write_file(destination / ".hive-managed.json", canonical(owner), immutable=True)
    with locked(destination / ".materialize.lock"):
        require(all(path.name in {".hive-managed.json", ".materialize.lock", "generations", "current.json"}
                    for path in destination.iterdir()), "unmanaged materialization root content")
        generations = private_directory(destination / "generations", create=True)
        pointer_hash = digest(verified.pointer_bytes)
        manifest = _manifest(verified)
        generation = generations / pointer_hash
        if generation.exists():
            _check_generation(generation, manifest, verified.materialized)
        else:
            building = private_directory(generations / (".building-" + pointer_hash), create=True)
            marker = canonical({"pointer_sha256": pointer_hash})
            existing = {path.relative_to(building).as_posix() for path in building.rglob("*") if not path.is_dir()}
            require(existing <= set(verified.materialized) | {".generation.json", ".building.json"},
                    "unmanaged content in incomplete materialization")
            write_file(building / ".building.json", marker, immutable=True)
            for name, raw in sorted(verified.materialized.items()):
                target = building / name
                for parent in reversed(target.parents):
                    if building in parent.parents:
                        private_directory(parent, create=True)
                write_file(target, raw, immutable=True)
                if fault:
                    fault("after-materialized-file")
            write_file(building / ".generation.json", canonical(manifest), immutable=True)
            _check_generation(building, manifest, verified.materialized)
            sync_directory(building)
            os.rename(building, generation)
            sync_directory(generations)
        current_path = destination / "current.json"
        if current_path.exists() or current_path.is_symlink():
            current = parse(read_file(current_path, private=True))
            exact_keys(current, {"schema", "pointer_sha256", "release_seq", "generation"}, "materialized current")
            require(current["schema"] == "rapp-private-hive-materialized-current/1"
                    and type(current["release_seq"]) is int and current["release_seq"] <= verified.pointer["release_seq"],
                    "materialized current rollback")
            if current["release_seq"] == verified.pointer["release_seq"]:
                require(current["pointer_sha256"] == pointer_hash, "same-sequence materialization fork")
        desired = {"schema": "rapp-private-hive-materialized-current/1", "pointer_sha256": pointer_hash,
                   "release_seq": verified.pointer["release_seq"], "generation": pointer_hash}
        with state.transaction() as db:
            require(State.get(db, "accepted") == {"pointer_sha256": pointer_hash},
                    "client accepted a newer publication during materialization; retry")
            if fault:
                fault("before-materialized-cas")
            write_file(current_path, canonical(desired))
            if fault:
                fault("after-materialized-cas")
            _check_generation(generation, manifest, verified.materialized)
            require(read_file(current_path, private=True) == canonical(desired), "materialization read-back mismatch")
            State.set(db, "materialized", {"destination": str(destination), "pointer_sha256": pointer_hash})
    return {"status": "materialized-as-data", "generation": str(generation), "files": len(verified.materialized),
            "executed": False, "original_files_preserved": True}


def verify(directory: Path, destination: Path | None = None):
    snapshot, verified = cached(directory)
    if destination is not None:
        destination = no_symlinks(Path(destination))
        expected = canonical({"schema": "rapp-private-hive-managed-output/1", "client_id": snapshot["client"]["id"],
                              "anchor_sha256": digest(canonical(snapshot["anchor"]))})
        require(read_file(destination / ".hive-managed.json", private=True) == expected, "unmanaged destination")
        current = parse(read_file(destination / "current.json", private=True))
        pointer_hash = digest(verified.pointer_bytes)
        require(current == {"schema": "rapp-private-hive-materialized-current/1", "pointer_sha256": pointer_hash,
                            "release_seq": verified.pointer["release_seq"], "generation": pointer_hash},
                "materialized current differs from authenticated cache")
        _check_generation(destination / "generations" / pointer_hash, _manifest(verified), verified.materialized)
    return {"status": "verified", "files": len(verified.materialized), "executed": False,
            "checkpoint": verified.checkpoint()}
