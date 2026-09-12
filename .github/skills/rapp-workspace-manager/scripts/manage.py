#!/usr/bin/env python3
"""Pointer-only RAPP Workspace manager and deterministic workspace scaffold."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
RAPP_PATH = ROOT / "vendor" / "rapp.py"
DEFAULT_REGISTRY = Path("~/.config/rapp-work/workspaces.json").expanduser()
LABEL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_rapp():
    spec = importlib.util.spec_from_file_location("rapp_work_manager_rapp", RAPP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load vendored RAPP/1 reference")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load_rapp()


def canonical(value) -> bytes:
    return R.canonical(value).encode("utf-8")


def atomic_write(path: Path, data: bytes, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if os.name != "nt":
                os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_label(value: str, name: str):
    if not isinstance(value, str) or len(value) > 64 or not LABEL.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase RAPP label")


def workspace_record(path: Path) -> dict:
    path = path.expanduser().resolve()
    record_path = path / "rappid.json"
    if record_path.is_symlink() or not record_path.is_file():
        raise ValueError("workspace requires a regular rappid.json")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != "rapp/1" or not R.rappid_valid(record.get("rappid")):
        raise ValueError("workspace identity is not RAPP/1 conformant")
    world = record.get("world_id")
    validate_label(world, "workspace world_id")
    if record.get("mode", "solo") not in {"solo", "hive"}:
        raise ValueError("workspace mode must be solo or hive")
    return record


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema": "rapp-workspace-manager/1", "workspaces": []}
    if path.is_symlink():
        raise ValueError("workspace registry cannot be a symlink")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "rapp-workspace-manager/1" or not isinstance(value.get("workspaces"), list):
        raise ValueError("workspace registry has the wrong shape")
    return value


def register(path: Path, registry_path: Path) -> dict:
    path = path.expanduser().resolve()
    record = workspace_record(path)
    registry = load_registry(registry_path)
    entry = {
        "rappid": record["rappid"],
        "name": record.get("name") or path.name,
        "path": str(path),
        "world_id": record["world_id"],
        "mode": record.get("mode", "solo"),
        "active": True,
    }
    entries = [
        value for value in registry["workspaces"]
        if value.get("rappid") != entry["rappid"] and value.get("path") != entry["path"]
    ]
    entries.append(entry)
    entries.sort(key=lambda value: (value["world_id"], value["name"], value["rappid"]))
    registry["workspaces"] = entries
    registry_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        registry_path.parent.chmod(0o700)
    atomic_write(registry_path, canonical(registry))
    return entry


def copy_skill(name: str, destination: Path):
    source = SKILLS / name
    if not (source / "SKILL.md").is_file():
        raise ValueError(f"manager distribution is missing project skill: {name}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def create(args) -> dict:
    target = Path(args.path).expanduser()
    if target.is_symlink() or target.exists():
        raise ValueError("workspace target must not already exist")
    validate_label(args.owner_label, "owner label")
    validate_label(args.slug, "workspace slug")
    validate_label(args.world_id, "world_id")
    parent = target.parent.resolve()
    if not parent.is_dir():
        raise ValueError("workspace parent directory does not exist")
    target = parent / target.name
    temporary = parent / f".{target.name}.rapp-work-{os.getpid()}"
    if temporary.exists():
        raise ValueError("temporary workspace path already exists")
    identity = R.mint_rappid(args.owner_label, args.slug)
    try:
        temporary.mkdir(mode=0o700)
        record = {
            "schema": "rapp/1",
            "rappid": identity,
            "kind": "workspace",
            "name": args.slug,
            "workspace_spec": "rapp-workspace/2.0",
            "mode": args.mode,
            "world_id": args.world_id,
        }
        atomic_write(temporary / "rappid.json", json.dumps(record, indent=2).encode() + b"\n", 0o600)
        atomic_write(
            temporary / "README.md",
            (
                "# " + args.slug + "\n\n"
                "**PRIVATE / LOCAL-ONLY BY DEFAULT.** Nothing leaves this workspace "
                "without explicit classification, selection, approval, and a private channel.\n"
            ).encode(),
            0o600,
        )
        atomic_write(temporary / "HOME.md", b"# Home\n\nWorkspace command center.\n", 0o600)
        atomic_write(
            temporary / "CLAUDE.md",
            (
                "# Workspace instructions\n\n"
                f"World: `{args.world_id}`. Never read or write across another world_id. "
                "Preserve local data and require owner approval for outward actions.\n"
            ).encode(),
            0o600,
        )
        atomic_write(
            temporary / "where-everything-lives.md",
            b"# Where everything lives\n\nRecord workspace-local systems and pointers here.\n",
            0o600,
        )
        atomic_write(temporary / "SPEC.md", (ROOT / "templates" / "workspace-SPEC.md").read_bytes(), 0o600)
        tools = temporary / "tools"
        tools.mkdir()
        atomic_write(tools / "append_frame.py", (ROOT / "templates" / "append_frame.py").read_bytes(), 0o700)
        project_skills = temporary / ".github" / "skills"
        project_skills.mkdir(parents=True)
        for name in ("rapp-workspace", "rapp-private-hive", "rapp-workspace-manager"):
            copy_skill(name, project_skills / name)
        for name in ("strategy", "projects", "reference", "people", "meetings", "rapp-projects"):
            (temporary / name).mkdir()
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    entry = register(target, Path(args.registry).expanduser())
    return {"status": "created", "workspace": entry}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--path", required=True)
    create_parser.add_argument("--owner-label", required=True)
    create_parser.add_argument("--slug", required=True)
    create_parser.add_argument("--world-id", required=True)
    create_parser.add_argument("--mode", choices=("solo", "hive"), default="solo")
    register_parser = commands.add_parser("register")
    register_parser.add_argument("--path", required=True)
    commands.add_parser("list")
    args = parser.parse_args()
    registry_path = Path(args.registry).expanduser()
    if args.command == "create":
        result = create(args)
    elif args.command == "register":
        result = {"status": "registered", "workspace": register(Path(args.path), registry_path)}
    else:
        result = load_registry(registry_path)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "refused", "error": str(error)}, sort_keys=True))
        raise SystemExit(1)
