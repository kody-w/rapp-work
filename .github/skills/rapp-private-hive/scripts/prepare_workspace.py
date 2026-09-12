#!/usr/bin/env python3
"""Additive, no-data-loss preparation for a RAPP Private Hive workspace."""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
RAPP_PATH = ROOT / "vendor" / "rapp.py"
CONTROL = ".rapp-hive"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
EXCLUDED_ROOTS = {".git", CONTROL}
CONTROL_SCHEMAS = {
    "state.json": "rapp-private-hive-workspace/1",
    "declaration.json": "rapp-hive/1-declaration",
    "selection.json": "rapp-private-hive-selection/1",
    "baseline.json": "rapp-private-hive-baseline/1",
    "prepare-receipt.json": "rapp-private-hive-prepare-receipt/1",
    "trusted-scanners.json": "rapp-private-hive-trusted-scanners/1",
}
MANAGED_SKILL_FILES = {
    "SKILL.md",
    "DEPLOYMENT.md",
    "requirements.txt",
    "requirements-test.txt",
}
for _directory in ("scripts", "lib", "schemas", "tests", "vendor"):
    MANAGED_SKILL_FILES.update(
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / _directory).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix in {".py", ".json", ".md", ".txt"}
    )


def _load_rapp():
    spec = importlib.util.spec_from_file_location("rapp_private_hive_vendor", RAPP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import pinned RAPP/1 reference: {RAPP_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = _load_rapp()


def utc_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def canonical_bytes(value: object) -> bytes:
    return R.canonical(value).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
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
        if os.name == "nt":
            temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _owned_private_directory(path: Path, *, create: bool = False) -> Path:
    if create and not path.exists():
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.chmod(0o700)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"private directory is missing or unsafe: {path}")
    info = path.stat()
    if os.name != "nt" and (
        info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise ValueError(f"private directory must be owner-only mode 0700: {path}")
    return path


@contextmanager
def workspace_lock(root: Path):
    base = control_root(root)
    _owned_private_directory(base, create=True)
    path = base / "workspace.lock"
    if path.is_symlink():
        raise ValueError("workspace lock cannot be a symlink")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("workspace lock must be a regular file")
        if os.name == "nt":
            import msvcrt
            if info.st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextmanager
def prepare_lock(root: Path):
    path = root / ".rapp-hive-prepare.lock"
    if path.is_symlink():
        raise ValueError("prepare lock cannot be a symlink")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
        path.unlink(missing_ok=True)


def workspace_root(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_symlink():
        raise ValueError("workspace root cannot be a symlink")
    root = candidate.resolve()
    if not root.is_dir():
        raise ValueError(f"workspace is not a directory: {root}")
    return root


def safe_relative(raw: str) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or "\\" in raw
        or ":" in raw
        or any(ord(character) < 32 for character in raw)
    ):
        raise ValueError("path must be a non-empty relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe relative path: {raw}")
    if path.parts[0] in EXCLUDED_ROOTS:
        raise ValueError(f"control or Git paths cannot be selected: {raw}")
    return str(path)


def read_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ValueError(f"required file is missing: {path}") from error
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON member in {path}: {key}")
            value[key] = item
        return value
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def regular_file(root: Path, relative: str) -> Path:
    relative = safe_relative(relative)
    cursor = root
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"symlinked workspace path is forbidden: {relative}")
    resolved = cursor.resolve()
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"workspace path escapes root: {relative}")
    if not resolved.is_file():
        raise ValueError(f"workspace path must be a regular file: {relative}")
    return resolved


def read_regular_bytes(root: Path, relative: str) -> bytes:
    relative = safe_relative(relative)
    if os.name == "nt":
        return regular_file(root, relative).read_bytes()
    flags_directory = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root, flags_directory)
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            next_descriptor = os.open(part, flags_directory, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=descriptor,
        )
        try:
            info = os.fstat(file_descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(f"workspace path must be a regular file: {relative}")
            with os.fdopen(file_descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(file_descriptor)
    finally:
        os.close(descriptor)


def validate_pii_receipt_value(
    receipt: dict,
    file_hash: str,
    *,
    trusted_scanners: dict[str, str],
) -> tuple[dict, str]:
    raw = canonical_bytes(receipt)
    required = {
        "schema",
        "file_sha256",
        "result",
        "scanner_rappid",
        "scanner_version",
        "scanned_utc",
        "spki_der_b64",
        "sig",
    }
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("PII receipt has missing or unknown fields")
    if receipt["schema"] != "rapp-pii-scan/1" or receipt["result"] != "none":
        raise ValueError("PII receipt must report an explicit no-PII result")
    if receipt["file_sha256"] != file_hash:
        raise ValueError("PII receipt is not bound to the selected file")
    if not R.rappid_valid(receipt["scanner_rappid"]):
        raise ValueError("PII receipt scanner_rappid is invalid")
    if not isinstance(receipt["scanner_version"], str) or not receipt["scanner_version"]:
        raise ValueError("PII receipt scanner_version is invalid")
    if not R.utc_valid(receipt["scanned_utc"]):
        raise ValueError("PII receipt timestamp is invalid")
    try:
        spki = base64.b64decode(receipt["spki_der_b64"], validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError("PII receipt SPKI is invalid") from error
    if R.Hb("rapp/1:rappid", spki) != R.rappid_parts(receipt["scanner_rappid"])["hash"]:
        raise ValueError("PII receipt SPKI does not match scanner_rappid")
    spki_hash = sha256(spki)
    if trusted_scanners.get(receipt["scanner_rappid"]) != spki_hash:
        raise ValueError("PII receipt scanner is not trusted by this workspace")
    scanned = datetime.strptime(receipt["scanned_utc"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )
    age_seconds = (datetime.now(timezone.utc) - scanned).total_seconds()
    if age_seconds < -300 or age_seconds > 86400:
        raise ValueError("PII receipt is outside the accepted freshness window")
    unsigned = {key: value for key, value in receipt.items() if key != "sig"}
    ok, why = R.verify_detached_jws(
        unsigned,
        receipt["sig"],
        spki,
        expected_kid=receipt["scanner_rappid"],
    )
    if not ok:
        raise ValueError(f"PII receipt signature is invalid: {why}")
    return receipt, sha256(raw)


def validate_pii_receipt(
    path: str,
    file_hash: str,
    *,
    trusted_scanners: dict[str, str],
) -> tuple[dict, str]:
    receipt_path = Path(path).expanduser()
    if receipt_path.is_symlink():
        raise ValueError("PII receipt cannot be a symlink")
    raw = receipt_path.resolve().read_bytes()
    receipt = R._strict_json(raw)
    if raw != canonical_bytes(receipt):
        raise ValueError("PII receipt must be canonical RAPP JSON")
    return validate_pii_receipt_value(
        receipt,
        file_hash,
        trusted_scanners=trusted_scanners,
    )


def inventory(root: Path) -> list[dict]:
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts and (
            relative.parts[0] in EXCLUDED_ROOTS
            or relative.parts[0].startswith(".rapp-hive")
        ):
            continue
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8")
            entries.append(
                {
                    "path": relative.as_posix(),
                    "sha256": sha256(target),
                    "bytes": len(target),
                    "type": "symlink",
                }
            )
            continue
        if not path.is_file():
            continue
        data = read_regular_bytes(root, relative.as_posix())
        entries.append(
            {
                "path": relative.as_posix(),
                "sha256": sha256(data),
                "bytes": len(data),
                "type": "file",
            }
        )
    return entries


def inventory_hash(entries: list[dict]) -> str:
    return sha256(canonical_bytes(entries))


def verify_unchanged(root: Path, before: list[dict]) -> None:
    for entry in before:
        path = root / entry["path"]
        if entry.get("type", "file") == "symlink":
            if not path.is_symlink():
                raise RuntimeError(f"pre-existing workspace symlink changed: {entry['path']}")
            data = os.readlink(path).encode("utf-8")
        else:
            if not path.is_file():
                raise RuntimeError(f"pre-existing workspace file disappeared: {entry['path']}")
            data = read_regular_bytes(root, entry["path"])
        if len(data) != entry["bytes"] or sha256(data) != entry["sha256"]:
            raise RuntimeError(f"pre-existing workspace file changed: {entry['path']}")


def workspace_identity(root: Path) -> tuple[dict, str]:
    path = root / "rappid.json"
    if path.is_symlink():
        raise ValueError("workspace rappid.json cannot be a symlink")
    record = read_json(path)
    identity = record.get("rappid")
    if not R.rappid_valid(identity):
        raise ValueError("workspace rappid.json does not contain a valid RAPP/1 identity")
    return record, identity


def control_root(root: Path) -> Path:
    return root / CONTROL


def control_files(root: Path) -> tuple[dict, dict, dict]:
    base = control_root(root)
    _owned_private_directory(base)
    documents = {}
    for name, schema in CONTROL_SCHEMAS.items():
        path = base / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Private Hive control generation is incomplete: {name}")
        info = path.stat()
        if os.name != "nt" and (
            info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
        ):
            raise ValueError(f"Private Hive control file must be owner-only: {name}")
        value = read_json(path)
        if value.get("schema") != schema:
            raise ValueError(f"Private Hive control file has wrong schema: {name}")
        documents[name] = value
    state = documents["state.json"]
    declaration = documents["declaration.json"]
    selection = documents["selection.json"]
    baseline = documents["baseline.json"]
    receipt = documents["prepare-receipt.json"]
    scanners = documents["trusted-scanners.json"]
    _, workspace_rappid = workspace_identity(root)
    if (
        state.get("workspace_rappid") != workspace_rappid
        or selection.get("workspace_rappid") != workspace_rappid
        or receipt.get("workspace_rappid") != workspace_rappid
    ):
        raise ValueError("Private Hive control state belongs to a different workspace")
    if (
        state.get("hive_rappid") != declaration.get("hive_rappid")
        or receipt.get("hive_rappid") != declaration.get("hive_rappid")
    ):
        raise ValueError("Private Hive control state has inconsistent Hive identity")
    for where, identity in (
        ("state.hive_rappid", state.get("hive_rappid")),
        ("state.dimension_rappid", state.get("dimension_rappid")),
        ("state.member_rappid", state.get("member_rappid")),
        ("declaration.hive_rappid", declaration.get("hive_rappid")),
    ):
        if not R.rappid_valid(identity):
            raise ValueError(f"Private Hive {where} is invalid")
    if (
        not isinstance(state.get("hive_name"), str)
        or len(state["hive_name"]) > 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", state["hive_name"])
    ):
        raise ValueError("Private Hive stored hive_name is invalid")
    if declaration.get("schema") != "rapp-hive/1-declaration":
        raise ValueError("Private Hive declaration schema is invalid")
    world_id = declaration.get("world_id")
    if (
        not isinstance(world_id, str)
        or len(world_id) > 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", world_id)
    ):
        raise ValueError("Private Hive declaration world_id is invalid")
    rooms = declaration.get("rooms")
    if not isinstance(rooms, list) or not rooms:
        raise ValueError("Private Hive declaration rooms are invalid")
    room_access = {}
    for room in rooms:
        if (
            not isinstance(room, dict)
            or set(room) != {"id", "area", "members", "access"}
            or not isinstance(room["id"], str)
            or room["access"] not in {"repository", "sealed"}
        ):
            raise ValueError("Private Hive declaration room is invalid")
        safe_relative(room["area"])
        room_access[room["id"]] = room["access"]
    files = baseline.get("files")
    if not isinstance(files, list):
        raise ValueError("Private Hive baseline files are invalid")
    for index, entry in enumerate(files):
        if (
            not isinstance(entry, dict)
            or set(entry) not in (
                {"path", "sha256", "bytes"},
                {"path", "sha256", "bytes", "type"},
            )
            or safe_relative(entry["path"]) != entry["path"]
            or not isinstance(entry["sha256"], str)
            or not HEX64.fullmatch(entry["sha256"])
            or not isinstance(entry["bytes"], int)
            or isinstance(entry["bytes"], bool)
            or entry["bytes"] < 0
            or entry.get("type", "file") not in {"file", "symlink"}
        ):
            raise ValueError(f"Private Hive baseline entry is invalid: {index}")
    expected_hash = inventory_hash(files)
    expected_bytes = sum(entry.get("bytes", -1) for entry in files)
    if (
        expected_hash != state.get("baseline_inventory_sha256")
        or expected_hash != receipt.get("baseline_inventory_sha256")
        or len(files) != state.get("baseline_files")
        or expected_bytes != state.get("baseline_bytes")
    ):
        raise ValueError("Private Hive baseline commitment mismatch")
    selection_entries = selection.get("entries")
    if not isinstance(selection_entries, list):
        raise ValueError("Private Hive selection entries are invalid")
    selection_paths = []
    for entry in selection_entries:
        required_entry_keys = {
            "path",
            "sha256",
            "bytes",
            "data_class",
            "pii_status",
            "pii_evidence_hash",
            "pii_evidence",
            "room_id",
            "protection",
            "transfer",
            "status",
        }
        if not isinstance(entry, dict) or set(entry) != required_entry_keys:
            raise ValueError("Private Hive selection entry is invalid")
        safe_relative(entry["path"])
        selection_paths.append(entry["path"])
        if (
            not isinstance(entry["sha256"], str)
            or not HEX64.fullmatch(entry["sha256"])
            or not isinstance(entry["bytes"], int)
            or isinstance(entry["bytes"], bool)
            or entry["bytes"] < 0
            or entry["data_class"] not in {"dogg", "godd", "neutral"}
            or entry["pii_status"] not in {"none", "unknown"}
            or entry["room_id"] not in room_access
            or entry["protection"] not in {"member-visible", "sealed-room"}
            or entry["transfer"] != "copy"
            or entry["status"] not in {"selected", "pending-seal"}
        ):
            raise ValueError("Private Hive selection entry fields are invalid")
        if (entry["protection"] == "sealed-room") != (entry["status"] == "pending-seal"):
            raise ValueError("Private Hive selection sealing state is inconsistent")
        if entry["protection"] == "sealed-room" and room_access[entry["room_id"]] != "sealed":
            raise ValueError("Private Hive sealed selection names an unsealed room")
        if entry["protection"] == "member-visible" and room_access[entry["room_id"]] == "sealed":
            raise ValueError("Private Hive plaintext selection names a sealed room")
        if entry["data_class"] == "godd" and entry["protection"] != "sealed-room":
            raise ValueError("Private Hive GODD selection is not sealed")
        if entry["data_class"] in {"dogg", "neutral"} and (
            entry["pii_status"] != "none"
            or not isinstance(entry["pii_evidence_hash"], str)
            or not HEX64.fullmatch(entry["pii_evidence_hash"])
            or not isinstance(entry["pii_evidence"], dict)
        ):
            raise ValueError("Private Hive plaintext selection lacks PII evidence")
    if selection_paths != sorted(set(selection_paths)):
        raise ValueError("Private Hive selection paths must be unique and sorted")
    if (
        not isinstance(selection.get("generation"), int)
        or isinstance(selection.get("generation"), bool)
        or selection["generation"] < 0
    ):
        raise ValueError("Private Hive selection generation is invalid")
    entries = scanners.get("entries")
    if not isinstance(entries, list):
        raise ValueError("Private Hive trusted scanner list is invalid")
    scanner_ids = []
    for index, entry in enumerate(entries):
        if (
            not isinstance(entry, dict)
            or set(entry) != {"rappid", "spki_sha256"}
            or not R.rappid_valid(entry["rappid"])
            or not isinstance(entry["spki_sha256"], str)
            or not HEX64.fullmatch(entry["spki_sha256"])
        ):
            raise ValueError(f"Private Hive trusted scanner entry is invalid: {index}")
        scanner_ids.append(entry["rappid"])
    if scanner_ids != sorted(set(scanner_ids)):
        raise ValueError("Private Hive trusted scanners must be unique and sorted")
    return state, declaration, selection


def trusted_scanners(root: Path) -> dict[str, str]:
    value = read_json(control_root(root) / "trusted-scanners.json")
    return {entry["rappid"]: entry["spki_sha256"] for entry in value["entries"]}


def command_inspect(args) -> dict:
    root = workspace_root(args.workspace)
    record, identity = workspace_identity(root)
    entries = inventory(root)
    base = control_root(root)
    if base.exists():
        control_files(root)
    return {
        "status": "ready" if not base.exists() else "prepared",
        "workspace": str(root),
        "workspace_rappid": identity,
        "mode": record.get("mode", "solo"),
        "preexisting_files": len(entries),
        "preexisting_bytes": sum(entry["bytes"] for entry in entries),
        "inventory_sha256": inventory_hash(entries),
        "control_path": str(base),
    }


def command_prepare(args) -> dict:
    root = workspace_root(args.workspace)
    record, workspace_rappid = workspace_identity(root)
    if not R.rappid_valid(args.member_rappid):
        raise ValueError("--member-rappid must be a valid RAPP/1 identity")
    owner = R.rappid_parts(args.member_rappid)["owner"]
    world_id = args.world_id or record.get("world_id")
    if (
        not isinstance(world_id, str)
        or len(world_id) > 64
        or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", world_id)
    ):
        raise ValueError("--world-id must be a lowercase RAPP label")
    if len(args.hive_name) > 64 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.hive_name):
        raise ValueError("--hive-name must be a lowercase RAPP label")

    base = control_root(root)
    with prepare_lock(root):
        if base.exists():
            state, declaration, selection = control_files(root)
            if (
                state.get("member_rappid") != args.member_rappid
                or state.get("hive_name") != args.hive_name
                or declaration.get("world_id") != world_id
            ):
                raise ValueError("existing Private Hive preparation does not match requested configuration")
            return {
                "status": "already-prepared",
                "workspace": str(root),
                "hive_rappid": declaration["hive_rappid"],
                "dimension_rappid": state["dimension_rappid"],
                "selected": len(selection["entries"]),
            }

        before = inventory(root)
        created = utc_now()
        hive_rappid = R.mint_rappid(owner, args.hive_name)
        dimension_rappid = R.mint_rappid(owner, f"{args.hive_name}-local")
        declaration = {
        "schema": "rapp-hive/1-declaration",
        "hive_rappid": hive_rappid,
        "world_id": world_id,
        "created_utc": created,
        "authority_channel_id": "local-authority",
        "members": [
            {
                "rappid": args.member_rappid,
                "role": "owner",
                "area": f"members/{owner}",
            }
        ],
        "rooms": [
            {
                "id": "general",
                "area": "rooms/general",
                "members": [args.member_rappid],
                "access": "repository",
            },
            {
                "id": "private",
                "area": "rooms/private",
                "members": [args.member_rappid],
                "access": "sealed",
            },
        ],
        "channels": [
            {
                "id": "local-authority",
                "kind": "local",
                "role": "authority",
                "locator": f"{CONTROL}/outbox",
                "writeback": True,
            }
        ],
        "policy": {
            "godd_sharing": "explicit",
            "default_godd_scope": "local-only",
            "external_publication": "disabled",
            "conflict_mode": "explicit",
            "default_transfer": "copy",
        },
    }
        state = {
        "schema": "rapp-private-hive-workspace/1",
        "workspace_rappid": workspace_rappid,
        "hive_rappid": hive_rappid,
        "dimension_rappid": dimension_rappid,
        "member_rappid": args.member_rappid,
        "hive_name": args.hive_name,
        "created_utc": created,
        "baseline_inventory_sha256": inventory_hash(before),
        "baseline_files": len(before),
        "baseline_bytes": sum(entry["bytes"] for entry in before),
        "data_loss_guard": "preexisting-bytes-unchanged",
    }
        selection = {
        "schema": "rapp-private-hive-selection/1",
        "workspace_rappid": workspace_rappid,
        "default": "local-only",
        "generation": 0,
        "entries": [],
    }
        scanners = {
            "schema": "rapp-private-hive-trusted-scanners/1",
            "entries": [],
        }
        receipt = {
        "schema": "rapp-private-hive-prepare-receipt/1",
        "prepared_utc": created,
        "workspace_rappid": workspace_rappid,
        "hive_rappid": hive_rappid,
        "baseline_inventory_sha256": state["baseline_inventory_sha256"],
        "preexisting_bytes_unchanged": True,
        "selected_entries": 0,
    }
        temporary = root / f".{CONTROL}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
        try:
            temporary.mkdir(mode=0o700)
            atomic_write(
                temporary / "baseline.json",
                canonical_bytes({"schema": "rapp-private-hive-baseline/1", "files": before}),
            )
            atomic_write(temporary / "declaration.json", canonical_bytes(declaration))
            atomic_write(temporary / "selection.json", canonical_bytes(selection))
            atomic_write(temporary / "trusted-scanners.json", canonical_bytes(scanners))
            atomic_write(temporary / "state.json", canonical_bytes(state))
            atomic_write(temporary / "prepare-receipt.json", canonical_bytes(receipt))
            verify_unchanged(root, before)
            os.replace(temporary, base)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        control_files(root)
        return {"status": "prepared", "workspace": str(root), **receipt}


def embed_project_skill(workspace: Path) -> dict:
    destination = workspace / ".github" / "skills" / "rapp-private-hive"
    cursor = workspace
    for part in (".github", "skills", "rapp-private-hive"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("project skill path cannot contain a symlink")
    try:
        if destination.resolve() == ROOT.resolve():
            if not destination.is_dir():
                raise ValueError("repository-native project skill path is not a directory")
            return {
                "status": "repository-native",
                "path": ".github/skills/rapp-private-hive",
            }
    except FileNotFoundError:
        pass
    lock = read_json(ROOT / "rapp" / "agent.lock.json")
    expected = {
        entry["path"]: entry["sha256"]
        for entry in lock.get("files", [])
    }
    if len(expected) != len(lock.get("files", [])) or not expected:
        raise ValueError("source Private Hive skill lock is invalid")
    expected["rapp/agent.lock.json"] = sha256((ROOT / "rapp" / "agent.lock.json").read_bytes())

    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() or not destination.is_dir():
            raise ValueError("existing project skill path is unsafe")
        actual = {}
        for path in destination.rglob("*"):
            relative = path.relative_to(destination)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink() or (path.exists() and not path.is_file() and not path.is_dir()):
                raise ValueError("existing project skill contains an unsafe entry")
            if path.is_file():
                actual[relative.as_posix()] = sha256(path.read_bytes())
        if actual != expected:
            raise ValueError("existing project skill differs; explicit reviewed upgrade is required")
        return {
            "status": "already-embedded",
            "path": ".github/skills/rapp-private-hive",
            "version": lock.get("version"),
            "files": len(expected),
        }

    parent = destination.parent
    cursor = workspace
    for part in (".github", "skills"):
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("project skill parent cannot be a symlink")
        cursor.mkdir(exist_ok=True)
    temporary = parent / f".rapp-private-hive.tmp-{os.getpid()}-{os.urandom(4).hex()}"
    try:
        temporary.mkdir()
        for relative, expected_hash in sorted(expected.items()):
            source = ROOT / relative
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"source project skill file is unsafe: {relative}")
            data = source.read_bytes()
            if sha256(data) != expected_hash:
                raise ValueError(f"source project skill lock mismatch: {relative}")
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, data, 0o644)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "status": "embedded",
        "path": ".github/skills/rapp-private-hive",
        "version": lock.get("version"),
        "files": len(expected),
    }


def command_migrate(args) -> dict:
    root = workspace_root(args.workspace)
    workspace_record, workspace_rappid = workspace_identity(root)
    prepare_result = command_prepare(args)
    with workspace_lock(root):
        state, declaration, _ = control_files(root)
        baseline = read_json(control_root(root) / "baseline.json")["files"]
        verify_unchanged(root, baseline)
        embedded = embed_project_skill(root)
        source_spec = workspace_record.get("workspace_spec") or "legacy-unversioned"
        migration_identity = {
            "workspace_rappid": workspace_rappid,
            "source_workspace_spec": source_spec,
            "target_workspace_spec": "rapp-workspace/1.0",
            "target_hive_profile": "rapp-hive/1",
            "baseline_inventory_sha256": state["baseline_inventory_sha256"],
        }
        migration_id = sha256(canonical_bytes(migration_identity))
        path = control_root(root) / "migration-receipt.json"
        if path.exists():
            if path.is_symlink():
                raise ValueError("migration receipt cannot be a symlink")
            existing = read_json(path)
            if (
                existing.get("schema") != "rapp-private-hive-migration-receipt/1"
                or existing.get("migration_id") != migration_id
                or existing.get("workspace_rappid") != workspace_rappid
                or existing.get("hive_rappid") != declaration["hive_rappid"]
            ):
                raise ValueError("existing migration receipt conflicts with this workspace")
            return {
                "status": "already-migrated",
                "workspace": str(root),
                "migration_id": migration_id,
                "workspace_rappid": workspace_rappid,
                "hive_rappid": declaration["hive_rappid"],
                "identity_preserved": True,
                "original_bytes_unchanged": True,
                "project_skill": embedded,
            }
        receipt = {
            "schema": "rapp-private-hive-migration-receipt/1",
            "migration_id": migration_id,
            "migrated_utc": utc_now(),
            "workspace_rappid": workspace_rappid,
            "hive_rappid": declaration["hive_rappid"],
            "source_workspace_spec": source_spec,
            "target_workspace_spec": "rapp-workspace/1.0",
            "target_hive_profile": "rapp-hive/1",
            "baseline_inventory_sha256": state["baseline_inventory_sha256"],
            "original_files": state["baseline_files"],
            "original_bytes": state["baseline_bytes"],
            "identity_preserved": True,
            "original_bytes_unchanged": True,
            "migration_mode": "additive-sidecar",
            "project_skill": embedded,
        }
        atomic_write(path, canonical_bytes(receipt))
        verify_unchanged(root, baseline)
        return {
            "status": "migrated",
            "workspace": str(root),
            "prepare_status": prepare_result["status"],
            **receipt,
        }


def command_select(args) -> dict:
    root = workspace_root(args.workspace)
    with workspace_lock(root):
        _, declaration, selection = control_files(root)
        relative = safe_relative(args.path)
        source = regular_file(root, relative)
        rooms = {room["id"]: room for room in declaration["rooms"]}
        if args.room not in rooms:
            raise ValueError(f"unknown room: {args.room}")
        data = read_regular_bytes(root, relative)
        file_hash = sha256(data)
        scanners = trusted_scanners(root)
        pii_receipt = None
        pii_evidence_hash = None
        if args.data_class in {"dogg", "neutral"}:
            if not args.pii_evidence:
                raise ValueError("plaintext DOGG and neutral selection requires --pii-evidence <receipt.json>")
            pii_receipt, pii_evidence_hash = validate_pii_receipt(
                args.pii_evidence,
                file_hash,
                trusted_scanners=scanners,
            )
            pii_status = "none"
            protection = args.protection or "member-visible"
        else:
            if args.pii_evidence:
                raise ValueError("GODD selection does not use a public PII-clearance receipt")
            pii_status = "unknown"
            protection = args.protection or "sealed-room"
            if protection != "sealed-room" or rooms[args.room]["access"] != "sealed":
                raise ValueError("GODD selection requires a sealed room and sealed-room protection")
        if protection == "sealed-room" and rooms[args.room]["access"] != "sealed":
            raise ValueError("sealed-room protection requires a sealed room")
        if rooms[args.room]["access"] == "sealed" and protection != "sealed-room":
            raise ValueError("a sealed room requires sealed-room protection")
        entry = {
            "path": relative,
            "sha256": file_hash,
            "bytes": len(data),
            "data_class": args.data_class,
            "pii_status": pii_status,
            "pii_evidence_hash": pii_evidence_hash,
            "pii_evidence": pii_receipt,
            "room_id": args.room,
            "protection": protection,
            "transfer": "copy",
            "status": "pending-seal" if protection == "sealed-room" else "selected",
        }
        entries = [value for value in selection["entries"] if value["path"] != relative]
        entries.append(entry)
        entries.sort(key=lambda value: value["path"])
        selection["entries"] = entries
        selection["generation"] = selection.get("generation", 0) + 1
        atomic_write(control_root(root) / "selection.json", canonical_bytes(selection))
        return {
            "status": "selected",
            "selection_generation": selection["generation"],
            "entry": entry,
            "local_source_preserved": True,
        }


def command_unselect(args) -> dict:
    root = workspace_root(args.workspace)
    with workspace_lock(root):
        _, _, selection = control_files(root)
        relative = safe_relative(args.path)
        before = len(selection["entries"])
        selection["entries"] = [value for value in selection["entries"] if value["path"] != relative]
        if len(selection["entries"]) == before:
            raise ValueError(f"path is not selected: {relative}")
        selection["generation"] = selection.get("generation", 0) + 1
        atomic_write(control_root(root) / "selection.json", canonical_bytes(selection))
        return {
            "status": "unselected",
            "selection_generation": selection["generation"],
            "path": relative,
            "local_source_preserved": True,
        }


def command_trust_scanner(args) -> dict:
    root = workspace_root(args.workspace)
    if not R.rappid_valid(args.scanner_rappid):
        raise ValueError("--scanner-rappid must be a valid keyed RAPPID")
    if not HEX64.fullmatch(args.spki_sha256):
        raise ValueError("--spki-sha256 must be 64 lowercase hex")
    with workspace_lock(root):
        control_files(root)
        path = control_root(root) / "trusted-scanners.json"
        value = read_json(path)
        entries = [entry for entry in value["entries"] if entry["rappid"] != args.scanner_rappid]
        entries.append({"rappid": args.scanner_rappid, "spki_sha256": args.spki_sha256})
        entries.sort(key=lambda entry: entry["rappid"])
        value["entries"] = entries
        atomic_write(path, canonical_bytes(value))
        return {"status": "trusted", "scanner_rappid": args.scanner_rappid}


def command_stage(args) -> dict:
    root = workspace_root(args.workspace)
    with workspace_lock(root):
        state, declaration, selection = control_files(root)
        scanners = trusted_scanners(root)
        outbox_input = Path(args.outbox).expanduser()
        if outbox_input.is_symlink():
            raise ValueError("outbox cannot be a symlink")
        outbox = outbox_input.resolve()
        if outbox == root or root in outbox.parents:
            raise ValueError("outbox must be outside the local workspace")
        _owned_private_directory(outbox, create=True)
        hive_key = sha256(declaration["hive_rappid"].encode("utf-8"))[:24]
        stage_path = outbox / f"hive-{hive_key}"
        if stage_path == root or root in stage_path.parents or stage_path in root.parents:
            raise ValueError("derived staging directory overlaps the local workspace")
        stage_root = _owned_private_directory(stage_path, create=True)
        unexpected = {
            path.name for path in stage_root.iterdir()
            if path.name not in {"generations", "current.json"}
            and not path.name.startswith(".generation-")
        }
        if unexpected:
            raise RuntimeError(f"outbox contains unmanaged entries: {sorted(unexpected)}")
        generations = _owned_private_directory(stage_root / "generations", create=True)
        temporary = stage_root / f".generation-{os.getpid()}-{os.urandom(4).hex()}"
        temporary.mkdir(mode=0o700)
        staged = []
        pending_sealed = []
        try:
            for entry in selection["entries"]:
                source = regular_file(root, entry["path"])
                data = read_regular_bytes(root, entry["path"])
                if sha256(data) != entry["sha256"] or len(data) != entry["bytes"]:
                    raise RuntimeError(f"selected source changed; reselect before staging: {entry['path']}")
                if entry["protection"] == "sealed-room":
                    pending_sealed.append(
                        {
                            "source_path_sha256": sha256(entry["path"].encode("utf-8")),
                            "source_sha256": entry["sha256"],
                            "room_id": entry["room_id"],
                            "status": "pending-seal",
                        }
                    )
                    continue
                receipt, evidence_hash = validate_pii_receipt_value(
                    entry.get("pii_evidence"),
                    entry["sha256"],
                    trusted_scanners=scanners,
                )
                if evidence_hash != entry.get("pii_evidence_hash"):
                    raise RuntimeError(f"PII evidence commitment changed: {entry['path']}")
                destination = temporary / "objects" / entry["path"]
                cursor = temporary
                for part in destination.relative_to(temporary).parts[:-1]:
                    cursor = cursor / part
                    if cursor.exists() and (cursor.is_symlink() or not cursor.is_dir()):
                        raise RuntimeError(f"unsafe staging path: {entry['path']}")
                    cursor.mkdir(exist_ok=True, mode=0o700)
                    cursor.chmod(0o700)
                atomic_write(destination, data, 0o600)
                staged.append(
                    {
                        key: entry[key]
                        for key in (
                            "path",
                            "sha256",
                            "bytes",
                            "data_class",
                            "pii_status",
                            "pii_evidence_hash",
                            "room_id",
                        )
                    }
                )
                if receipt["result"] != "none":
                    raise RuntimeError(f"PII receipt no longer clears source: {entry['path']}")
            manifest = {
                "schema": "rapp-private-hive-stage/2",
                "hive_rappid": declaration["hive_rappid"],
                "dimension_rappid": state["dimension_rappid"],
                "selection_generation": selection.get("generation", 0),
                "objects": staged,
                "pending_sealed": pending_sealed,
                "local_sources_preserved": True,
            }
            manifest_bytes = canonical_bytes(manifest)
            generation_hash = sha256(manifest_bytes)
            atomic_write(temporary / "manifest.json", manifest_bytes, 0o600)
            generation = generations / generation_hash
            if generation.exists():
                if generation.is_symlink() or not generation.is_dir():
                    raise RuntimeError("existing stage generation is unsafe")
                expected_files = {"manifest.json"}
                valid_generation = (generation / "manifest.json").is_file()
                if valid_generation:
                    valid_generation = (generation / "manifest.json").read_bytes() == manifest_bytes
                for item in staged:
                    relative = "objects/" + item["path"]
                    expected_files.add(relative)
                    try:
                        data = read_regular_bytes(generation, relative)
                    except (OSError, ValueError):
                        valid_generation = False
                        continue
                    if sha256(data) != item["sha256"] or len(data) != item["bytes"]:
                        valid_generation = False
                actual_files = set()
                for path in generation.rglob("*"):
                    if path.is_symlink():
                        valid_generation = False
                        continue
                    if path.is_file():
                        actual_files.add(path.relative_to(generation).as_posix())
                valid_generation = valid_generation and actual_files == expected_files
                if valid_generation:
                    shutil.rmtree(temporary)
                else:
                    shutil.rmtree(generation)
                    os.replace(temporary, generation)
            else:
                os.replace(temporary, generation)
            pointer = {
                "schema": "rapp-private-hive-current-stage/1",
                "generation": generation_hash,
                "manifest_sha256": generation_hash,
            }
            atomic_write(stage_root / "current.json", canonical_bytes(pointer), 0o600)
            for prior in generations.iterdir():
                if prior.name == generation_hash:
                    continue
                if prior.is_symlink() or not prior.is_dir():
                    raise RuntimeError(f"unsafe prior stage generation: {prior.name}")
                shutil.rmtree(prior)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        return {
            "status": "staged" if not pending_sealed else "staged-with-pending-sealed",
            "outbox": str(stage_root),
            "generation": generation_hash,
            "staged": len(staged),
            "pending_sealed": [
                entry["path"] for entry in selection["entries"]
                if entry["protection"] == "sealed-room"
            ],
            "local_sources_preserved": True,
        }


def command_verify(args) -> dict:
    root = workspace_root(args.workspace)
    with workspace_lock(root):
        state, declaration, selection = control_files(root)
        scanners = trusted_scanners(root)
        baseline = read_json(control_root(root) / "baseline.json")["files"]
        baseline_changes = []
        for entry in baseline:
            try:
                if entry.get("type", "file") == "symlink":
                    path = root / entry["path"]
                    if not path.is_symlink():
                        raise ValueError("symlink changed")
                    data = os.readlink(path).encode("utf-8")
                else:
                    regular_file(root, entry["path"])
                    data = read_regular_bytes(root, entry["path"])
                matches = sha256(data) == entry["sha256"] and len(data) == entry["bytes"]
            except ValueError:
                matches = False
            if not matches:
                baseline_changes.append(entry["path"])
        checked = []
        stale_selection = []
        for entry in selection["entries"]:
            try:
                source = regular_file(root, entry["path"])
                current = read_regular_bytes(root, entry["path"])
                matches = sha256(current) == entry["sha256"] and len(current) == entry["bytes"]
                if matches and entry["data_class"] in {"dogg", "neutral"}:
                    _, evidence_hash = validate_pii_receipt_value(
                        entry.get("pii_evidence"),
                        entry["sha256"],
                        trusted_scanners=scanners,
                    )
                    matches = evidence_hash == entry.get("pii_evidence_hash")
            except (ValueError, RuntimeError):
                matches = False
            checked.append({"path": entry["path"], "matches_selection": matches})
            if not matches:
                stale_selection.append(entry["path"])
        status = "verified"
        if stale_selection:
            status = "selection-stale"
        elif baseline_changes:
            status = "workspace-evolved"
        return {
            "status": status,
            "workspace_rappid": state["workspace_rappid"],
            "hive_rappid": declaration["hive_rappid"],
            "baseline_changes": baseline_changes,
            "selection_generation": selection["generation"],
            "stale_selection": stale_selection,
            "selection": checked,
            "local_only_default": selection["default"] == "local-only",
        }


COMMANDS = {
    "inspect": command_inspect,
    "prepare": command_prepare,
    "migrate": command_migrate,
    "select": command_select,
    "unselect": command_unselect,
    "trust-scanner": command_trust_scanner,
    "stage": command_stage,
    "verify": command_verify,
}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        if name in {"prepare", "migrate"}:
            command.add_argument("--member-rappid", required=True)
            command.add_argument("--hive-name", required=True)
            command.add_argument("--world-id")
        elif name == "select":
            command.add_argument("--path", required=True)
            command.add_argument("--data-class", choices=("dogg", "godd", "neutral"), required=True)
            command.add_argument("--room", required=True)
            command.add_argument("--protection", choices=("member-visible", "sealed-room"))
            command.add_argument("--pii-evidence")
        elif name == "unselect":
            command.add_argument("--path", required=True)
        elif name == "trust-scanner":
            command.add_argument("--scanner-rappid", required=True)
            command.add_argument("--spki-sha256", required=True)
        elif name == "stage":
            command.add_argument("--outbox", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = COMMANDS[args.command](args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"status": "refused", "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
