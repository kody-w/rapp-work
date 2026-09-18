#!/usr/bin/env python3
"""Verify wheel/sdist identity, safety, and required packaged compatibility data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_COMMIT = "591e014ad39e223b00ab343ae26e5d9a867ebeee"
CANONICAL_REPOSITORY = "https://github.com/kody-w/rapp-1"
HISTORICAL_WORK_SPEC_SHA256 = "861920ed31dd31412cc67064532ca855e3d9f842f1f63fa7f3daeab605fddf7e"
RAPP1_PIN_KEYS = {
    "commit",
    "protocol",
    "reference_path",
    "reference_sha256",
    "repository",
    "schema",
    "spec_path",
    "spec_sha256",
}
RAPP_WORK_PIN_KEYS = {
    "commit",
    "protocol",
    "repository",
    "schema",
    "schema_path",
    "schema_sha256",
    "spec_path",
    "spec_sha256",
}
SDIST_METADATA = {
    "PKG-INFO",
    "setup.cfg",
    "src/rapp_work.egg-info/PKG-INFO",
    "src/rapp_work.egg-info/SOURCES.txt",
    "src/rapp_work.egg-info/dependency_links.txt",
    "src/rapp_work.egg-info/entry_points.txt",
    "src/rapp_work.egg-info/requires.txt",
    "src/rapp_work.egg-info/top_level.txt",
}


def closed_json(raw: bytes, keys: set[str], where: str) -> dict:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{where} is invalid JSON") from error
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{where} is not a closed object")
    return value


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe archive path: {name}")
    return path.as_posix()


def verify_wheel(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        names = [safe_name(info.filename.rstrip("/")) for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("wheel contains duplicate paths")
        for info in archive.infolist():
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise ValueError("wheel contains a symlink")
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise ValueError("wheel must contain one METADATA file")
        metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
        if metadata["Name"] != "rapp-work" or metadata["Version"] != "1.0.0":
            raise ValueError("wheel distribution identity mismatch")
        if metadata["Requires-Python"] != ">=3.10":
            raise ValueError("wheel Python compatibility metadata mismatch")
        if not any(
            value.startswith("cryptography") for value in metadata.get_all("Requires-Dist", [])
        ):
            raise ValueError("wheel is missing its signature-verification dependency")
        required_suffixes = {
            "rapp_work/__init__.py",
            "rapp_work/__main__.py",
            "rapp_work/py.typed",
            "rapp_work/data/RAPP1_PIN.json",
            "rapp_work/data/RAPP_WORK_PIN.json",
            "rapp_work/data/api.json",
            "rapp_work/data/profiles.json",
            "rapp_work/data/rapp-work-1-SPEC.md",
            "rapp_work/data/rapp-work-1-schema.json",
            "rapp_work/_vendor_rapp1/rapp.py",
            "rapp_work/_protocols/rapp-hive/1/SPEC.md",
            "rapp_work/_protocols/rapp-federation/1/fixtures/ed25519-bilateral.json",
            "rapp_work/_legacy_skills/rapp-private-hive/scripts/deploy_hive.py",
            "rapp_work/_legacy_skills/rapp-workspace-manager/scripts/manage.py",
        }
        missing = sorted(required_suffixes - set(names))
        if missing:
            raise ValueError(f"wheel is missing required package data: {missing}")
        entry_points = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        if len(entry_points) != 1 or b"rapp-work = rapp_work.cli:main" not in archive.read(entry_points[0]):
            raise ValueError("wheel console entrypoint mismatch")
        pin = closed_json(
            archive.read("rapp_work/data/RAPP1_PIN.json"),
            RAPP1_PIN_KEYS,
            "wheel RAPP/1 pin",
        )
        if (
            pin["schema"] != "rapp-work-parent-pin/1"
            or pin["protocol"] != "rapp/1"
            or pin["repository"] != CANONICAL_REPOSITORY
            or pin["commit"] != CANONICAL_COMMIT
            or pin["spec_path"] != "SPEC.md"
            or pin["reference_path"] != "rapp.py"
        ):
            raise ValueError("wheel RAPP/1 parent pin contract mismatch")
        if (
            hashlib.sha256(archive.read("rapp_work/_vendor_rapp1/rapp.py")).hexdigest()
            != pin["reference_sha256"]
            or hashlib.sha256(archive.read("rapp_work/_vendor_rapp1/SPEC.md")).hexdigest()
            != pin["spec_sha256"]
        ):
            raise ValueError("wheel RAPP/1 parent pin mismatch")
        work_pin = closed_json(
            archive.read("rapp_work/data/RAPP_WORK_PIN.json"),
            RAPP_WORK_PIN_KEYS,
            "wheel RAPP Work SDK parent pin",
        )
        if (
            work_pin["schema"] != "rapp-work-sdk-parent-pin/1"
            or work_pin["protocol"] != "rapp-work/1"
            or work_pin["repository"] != CANONICAL_REPOSITORY
            or work_pin["commit"] != CANONICAL_COMMIT
            or work_pin["spec_path"] != "protocols/rapp-work/1/SPEC.md"
            or work_pin["schema_path"] != "protocols/rapp-work/1/schema.json"
            or work_pin["repository"] != pin["repository"]
            or work_pin["commit"] != pin["commit"]
        ):
            raise ValueError("wheel RAPP Work SDK parent pin contract mismatch")
        if (
            hashlib.sha256(archive.read("rapp_work/data/rapp-work-1-SPEC.md")).hexdigest()
            != work_pin["spec_sha256"]
            or hashlib.sha256(
                archive.read("rapp_work/data/rapp-work-1-schema.json")
            ).hexdigest()
            != work_pin["schema_sha256"]
        ):
            raise ValueError("wheel RAPP Work SDK parent pin mismatch")
        profiles = closed_json(
            archive.read("rapp_work/data/profiles.json"),
            {"profiles", "schema"},
            "wheel profile registry",
        )
        if (
            profiles["schema"] != "rapp-work-profile-registry/1"
            or not isinstance(profiles["profiles"], list)
        ):
            raise ValueError("wheel profile registry contract mismatch")
        descriptors = {
            descriptor.get("id"): descriptor
            for descriptor in profiles["profiles"]
            if isinstance(descriptor, dict)
        }
        canonical_work = descriptors.get("rapp-work/1")
        if (
            not isinstance(canonical_work, dict)
            or canonical_work.get("authority") != "accepted-canonical-protocol"
            or canonical_work.get("activation")
            != "sdk-parent-pin-not-estate-activation"
            or canonical_work.get("spec_path") != "data:rapp-work-1-SPEC.md"
            or canonical_work.get("spec_sha256") != work_pin["spec_sha256"]
            or canonical_work.get("schema_path") != "data:rapp-work-1-schema.json"
            or canonical_work.get("schema_sha256") != work_pin["schema_sha256"]
        ):
            raise ValueError("wheel canonical RAPP Work profile descriptor mismatch")
        skill_prefix = "rapp_work/_legacy_skills/rapp-private-hive/"
        lock = json.loads(archive.read(skill_prefix + "rapp/agent.lock.json"))
        for entry in lock["files"]:
            packaged = skill_prefix + entry["path"]
            if packaged not in names:
                raise ValueError(f"wheel compatibility lock file missing: {entry['path']}")
            if hashlib.sha256(archive.read(packaged)).hexdigest() != entry["sha256"]:
                raise ValueError(f"wheel compatibility lock mismatch: {entry['path']}")
        forbidden = ("owner.pk8.pem", "state.sqlite3", ".env", "id_rsa")
        if any(any(part == value for part in PurePosixPath(name).parts) for name in names for value in forbidden):
            raise ValueError("wheel contains a forbidden custody or credential file")
    return {"artifact": path.name, "files": len(names), "type": "wheel"}


def inventory_entries(raw: bytes) -> dict[str, dict[str, object]]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("sdist release inventory is invalid JSON") from error
    if (
        not isinstance(value, dict)
        or set(value) != {"distribution", "files", "profile", "protocol", "schema", "version"}
        or value["distribution"] != "rapp-work"
        or value["profile"] != "rapp-work-sdk/1"
        or value["protocol"] != "rapp-work/1"
        or value["schema"] != "rapp-work-release-inventory/1"
        or value["version"] != "1.0.0"
        or not isinstance(value["files"], list)
    ):
        raise ValueError("sdist release inventory contract mismatch")
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if raw != canonical:
        raise ValueError("sdist release inventory is not canonical JSON")
    entries: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for entry in value["files"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"bytes", "path", "sha256"}
            or type(entry["bytes"]) is not int
            or entry["bytes"] < 0
            or not isinstance(entry["path"], str)
            or not isinstance(entry["sha256"], str)
            or HEX64.fullmatch(entry["sha256"]) is None
        ):
            raise ValueError("sdist release inventory entry is invalid")
        relative = safe_name(entry["path"])
        if relative == "RELEASE-INVENTORY.json" or relative in entries:
            raise ValueError("sdist release inventory contains a duplicate or self-entry")
        entries[relative] = entry
        order.append(relative)
    if order != sorted(order):
        raise ValueError("sdist release inventory is not path sorted")
    return entries


def verify_inventory_files(files: dict[str, bytes]) -> None:
    inventory_raw = files.get("RELEASE-INVENTORY.json")
    if inventory_raw is None:
        raise ValueError("sdist is missing RELEASE-INVENTORY.json")
    entries = inventory_entries(inventory_raw)
    expected = set(entries) | {"RELEASE-INVENTORY.json"}
    missing = sorted(expected - set(files))
    if missing:
        raise ValueError(f"sdist is missing inventoried release files: {missing}")
    extras = sorted(set(files) - expected)
    unsupported = sorted(set(extras) - SDIST_METADATA)
    if unsupported:
        raise ValueError(f"sdist contains non-inventoried files: {unsupported}")
    missing_metadata = sorted(SDIST_METADATA - set(files))
    if missing_metadata:
        raise ValueError(f"sdist is missing deterministic packaging metadata: {missing_metadata}")
    for relative, entry in entries.items():
        raw = files[relative]
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"sdist inventoried file hash mismatch: {relative}")

    root_parent_pin = closed_json(files["RAPP1_PIN.json"], RAPP1_PIN_KEYS, "sdist RAPP/1 pin")
    packaged_parent_pin = closed_json(
        files["src/rapp_work/data/RAPP1_PIN.json"],
        RAPP1_PIN_KEYS,
        "sdist packaged RAPP/1 pin",
    )
    root_work_pin = closed_json(
        files["RAPP_WORK_PIN.json"],
        RAPP_WORK_PIN_KEYS,
        "sdist RAPP Work SDK parent pin",
    )
    packaged_work_pin = closed_json(
        files["src/rapp_work/data/RAPP_WORK_PIN.json"],
        RAPP_WORK_PIN_KEYS,
        "sdist packaged RAPP Work SDK parent pin",
    )
    if (
        root_parent_pin != packaged_parent_pin
        or root_parent_pin["schema"] != "rapp-work-parent-pin/1"
        or root_parent_pin["repository"] != CANONICAL_REPOSITORY
        or root_parent_pin["commit"] != CANONICAL_COMMIT
        or root_work_pin != packaged_work_pin
        or root_work_pin["schema"] != "rapp-work-sdk-parent-pin/1"
        or root_work_pin["repository"] != CANONICAL_REPOSITORY
        or root_work_pin["commit"] != CANONICAL_COMMIT
        or root_parent_pin["repository"] != root_work_pin["repository"]
        or root_parent_pin["commit"] != root_work_pin["commit"]
    ):
        raise ValueError("sdist canonical protocol pin mismatch")
    if (
        hashlib.sha256(files["vendor/rapp-1/SPEC.md"]).hexdigest()
        != root_parent_pin["spec_sha256"]
        or hashlib.sha256(files["vendor/rapp-1/rapp.py"]).hexdigest()
        != root_parent_pin["reference_sha256"]
        or hashlib.sha256(files["src/rapp_work/data/rapp-work-1-SPEC.md"]).hexdigest()
        != root_work_pin["spec_sha256"]
        or hashlib.sha256(
            files["src/rapp_work/data/rapp-work-1-schema.json"]
        ).hexdigest()
        != root_work_pin["schema_sha256"]
        or hashlib.sha256(files["SPEC.md"]).hexdigest() != HISTORICAL_WORK_SPEC_SHA256
    ):
        raise ValueError("sdist protocol pin bytes mismatch")

    root_metadata = files["PKG-INFO"]
    egg_metadata = files["src/rapp_work.egg-info/PKG-INFO"]
    if root_metadata != egg_metadata:
        raise ValueError("sdist PKG-INFO copies differ")
    metadata = BytesParser().parsebytes(root_metadata)
    if (
        metadata["Name"] != "rapp-work"
        or metadata["Version"] != "1.0.0"
        or metadata["Requires-Python"] != ">=3.10"
        or not any(
            value.startswith("cryptography")
            for value in metadata.get_all("Requires-Dist", [])
        )
    ):
        raise ValueError("sdist deterministic package metadata mismatch")
    exact_metadata = {
        "setup.cfg": b"[egg_info]\ntag_build = \ntag_date = 0\n\n",
        "src/rapp_work.egg-info/dependency_links.txt": b"\n",
        "src/rapp_work.egg-info/entry_points.txt": (
            b"[console_scripts]\nrapp-work = rapp_work.cli:main\n"
        ),
        "src/rapp_work.egg-info/requires.txt": (
            b"cryptography<47,>=42\n\n"
            b"[dev]\n"
            b"build<2,>=1.2\n"
            b"jsonschema<5,>=4.21\n"
            b"mypy<2,>=1.15\n"
            b"pytest<10,>=8\n"
            b"ruff<1,>=0.11\n"
            b"wheel<1,>=0.45\n"
        ),
        "src/rapp_work.egg-info/top_level.txt": b"rapp_work\n",
    }
    for relative, expected_raw in exact_metadata.items():
        if files[relative] != expected_raw:
            raise ValueError(f"sdist generated metadata differs: {relative}")
    sources = files["src/rapp_work.egg-info/SOURCES.txt"].decode("utf-8").splitlines()
    expected_sources = expected | {
        relative
        for relative in SDIST_METADATA
        if relative.startswith("src/rapp_work.egg-info/")
    }
    if len(sources) != len(set(sources)) or set(sources) != expected_sources:
        raise ValueError("sdist SOURCES.txt does not exactly enumerate release inputs")


def verify_sdist(path: Path) -> dict:
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [safe_name(member.name.rstrip("/")) for member in members if member.name.rstrip("/")]
        if len(names) != len(set(names)):
            raise ValueError("sdist contains duplicate paths")
        if any(not (member.isfile() or member.isdir()) for member in members):
            raise ValueError("sdist contains a link, device, or unsupported member")
        roots = {PurePosixPath(name).parts[0] for name in names}
        if len(roots) != 1:
            raise ValueError("sdist must have one archive root")
        root = next(iter(roots))
        files: dict[str, bytes] = {}
        for member in members:
            if not member.isfile():
                continue
            relative = PurePosixPath(safe_name(member.name)).relative_to(root).as_posix()
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"sdist regular file could not be read: {relative}")
            files[relative] = extracted.read()
        verify_inventory_files(files)
    return {"artifact": path.name, "files": len(files), "type": "sdist"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args(argv)
    results = []
    for path in args.artifacts:
        if path.suffix == ".whl":
            results.append(verify_wheel(path))
        elif path.name.endswith(".tar.gz"):
            results.append(verify_sdist(path))
        else:
            raise ValueError(f"unsupported package artifact: {path}")
    for result in results:
        print(f"{result['type']}: {result['artifact']} ({result['files']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
