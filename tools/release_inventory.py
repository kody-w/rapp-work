#!/usr/bin/env python3
"""Build or verify the deterministic repository release inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "RELEASE-INVENTORY.json"
EXCLUDED_PREFIXES = (
    ".git/",
    ".hive-test-work/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".test-work/",
    ".venv/",
    "build/",
    "dist/",
)


def release_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = []
    for value in result.stdout.splitlines():
        if (
            not value
            or value == "RELEASE-INVENTORY.json"
            or value.endswith((".pyc", ".pyo"))
            or "__pycache__/" in value
            or value.startswith(EXCLUDED_PREFIXES)
        ):
            continue
        path = ROOT / value
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"release inventory requires regular files: {value}")
        paths.append(value)
    return sorted(set(paths))


def is_source_checkout() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return (
        result.returncode == 0
        and Path(result.stdout.strip()).resolve() == ROOT.resolve()
    )


def build() -> dict:
    entries = []
    for relative in release_files():
        raw = (ROOT / relative).read_bytes()
        entries.append(
            {
                "bytes": len(raw),
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return {
        "distribution": "rapp-work",
        "files": entries,
        "profile": "rapp-work-sdk/1",
        "protocol": "rapp-work/1",
        "schema": "rapp-work-release-inventory/1",
        "version": "1.0.0",
    }


def canonical(value: object) -> bytes:
    sys.path.insert(0, str(ROOT / "src"))
    from rapp_work._json import canonical_bytes

    return canonical_bytes(value)


def verify_extracted() -> int:
    if not INVENTORY.is_file() or INVENTORY.is_symlink():
        raise SystemExit("release inventory is missing or unsafe")
    raw_inventory = INVENTORY.read_bytes()
    try:
        inventory = json.loads(raw_inventory)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit("release inventory is invalid JSON") from error
    if (
        not isinstance(inventory, dict)
        or set(inventory)
        != {"distribution", "files", "profile", "protocol", "schema", "version"}
        or inventory["distribution"] != "rapp-work"
        or inventory["profile"] != "rapp-work-sdk/1"
        or inventory["protocol"] != "rapp-work/1"
        or inventory["schema"] != "rapp-work-release-inventory/1"
        or inventory["version"] != "1.0.0"
        or not isinstance(inventory["files"], list)
        or canonical(inventory) != raw_inventory
    ):
        raise SystemExit("release inventory contract is invalid or noncanonical")
    paths: list[str] = []
    for entry in inventory["files"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"bytes", "path", "sha256"}
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 0
            or not isinstance(entry["path"], str)
            or not isinstance(entry["sha256"], str)
        ):
            raise SystemExit("release inventory entry is invalid")
        relative = PurePosixPath(entry["path"])
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.as_posix() == "RELEASE-INVENTORY.json"
        ):
            raise SystemExit("release inventory path is unsafe")
        paths.append(relative.as_posix())
        path = ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"inventoried release file is missing or unsafe: {relative}")
        raw = path.read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise SystemExit(f"inventoried release file differs: {relative}")
    if paths != sorted(set(paths)):
        raise SystemExit("release inventory paths are duplicated or unsorted")
    print(f"extracted release inventory verified: {len(paths)} files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not is_source_checkout():
        if args.write:
            raise SystemExit("release inventory can only be written from its source checkout")
        return verify_extracted()
    expected = canonical(build())
    if args.write:
        INVENTORY.write_bytes(expected)
        print(f"wrote {INVENTORY.name}: {len(json.loads(expected)['files'])} files")
        return 0
    if not INVENTORY.is_file() or INVENTORY.read_bytes() != expected:
        raise SystemExit("release inventory is missing or stale")
    print(f"release inventory verified: {len(json.loads(expected)['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
