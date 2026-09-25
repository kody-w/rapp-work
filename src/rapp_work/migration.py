from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, TypeAlias

from ._json import canonical_bytes, canonical_sha256, closed_object, strict_json_loads
from ._paths import (
    absolute_path,
    activate_directory_noreplace,
    assert_no_symlinks,
    create_directories,
    directory_fd,
    path_identity,
    private_directory,
    read_regular,
    safe_relative,
    write_new,
)
from .errors import Refusal, require
from .plans import FileAction
from .rapp1 import FRAME_KEYS, rappid_valid
from .workspace import Organization, _managed_record, _organization_files, _workspace_files

HEX64 = re.compile(r"^[0-9a-f]{64}$")
POINTER_SUCCESSOR = "pointer-only"
POINTER_PATH = ".rapp-work/pointer-successor.json"
POINTER_SCHEMA = "rapp-work-pointer-successor/1"
POINTER_SOURCE_SCHEMA = "rapp-work-pointer-successor-source/1"
POINTER_PLAN_SCHEMA = "rapp-work-pointer-successor-plan/1"
POINTER_WORLD_MAX = 128
POINTER_MAX_NAMED_PATHS = 256
POINTER_MAX_AUTHORITY_BYTES = 64 * 1024 * 1024
# Code points refused in a legacy world id: C0, DEL, C1, UTF-16 surrogates, and the
# explicit bidirectional controls, so a reviewed plan cannot display a spoofed world.
POINTER_WORLD_FORBIDDEN = (
    (0x0000, 0x001F),
    (0x007F, 0x009F),
    (0x061C, 0x061C),
    (0x200E, 0x200F),
    (0x202A, 0x202E),
    (0x2066, 0x2069),
    (0xD800, 0xDFFF),
)
HIVE_AUTHORITY_PATHS = (
    ".rapp-hive/authority.json",
    ".rapp-hive/baseline.json",
    ".rapp-hive/declaration.json",
    ".rapp-hive/migration-receipt.json",
    ".rapp-hive/owner-anchor.json",
    ".rapp-hive/registry.json",
    ".rapp-hive/selection.json",
    ".rapp-hive/state.json",
    ".rapp/registry.json",
    "owner-anchor.json",
    "rapp/registry.json",
    "refs/current.json",
    "registry.json",
)
HIVE_CHANNEL_KINDS = ("custom", "github", "lan", "local", "nas", "sharepoint")
HIVE_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
LOCATOR_SEGMENT = r"[A-Za-z0-9._~%!$&()*+,;=:-]+"
GITHUB_LOCATOR = re.compile(
    r"https://github\.com/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}"
)
HTTPS_LOCATOR = re.compile(
    r"https://[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(?::[0-9]{1,5})?"
    rf"(?:/(?:{LOCATOR_SEGMENT})?)*"
)
OPAQUE_LOCATOR = re.compile(rf"[a-z][a-z0-9+.-]{{0,31}}:{LOCATOR_SEGMENT}(?:/{LOCATOR_SEGMENT})*")
RELATIVE_LOCATOR = re.compile(rf"{LOCATOR_SEGMENT}(?:/{LOCATOR_SEGMENT})*")
LOCATOR_FORBIDDEN = frozenset("@?#\\\"'<>`{}|^[]")
SOURCE_AUTHORITY_PATHS = (
    ".rapp-hive/baseline.json",
    ".rapp-hive/declaration.json",
    ".rapp-hive/migration-receipt.json",
    ".rapp-hive/selection.json",
    ".rapp-hive/state.json",
    ".rapp-work/managed.json",
    ".rapp-work/sdk.json",
    "organization.json",
    "rappid.json",
    "workspaces.json",
)


def pointer_world_id(value: Any, where: str) -> str:
    """Validate a legacy source world id recorded verbatim by a pointer-only successor.

    The grammar is a strict subset of the RAPP Workspace/1 world id (1 to 128
    characters, no control characters) inside the RAPP I-JSON domain (NFC, Unicode
    scalar values), additionally refusing C1 and bidirectional controls. It is never a
    label, path, name, instruction-file value, or hash input.
    """

    require(
        isinstance(value, str)
        and 1 <= len(value) <= POINTER_WORLD_MAX
        and not any(
            low <= ord(character) <= high
            for character in value
            for low, high in POINTER_WORLD_FORBIDDEN
        )
        and unicodedata.normalize("NFC", value) == value,
        "REFUSE_POINTER_WORLD",
        f"{where} must be 1 to {POINTER_WORLD_MAX} NFC characters without control characters",
        length=len(value) if isinstance(value, str) else None,
    )
    return str(value)


def _source_identity(root: Path, *, pointer: bool = False) -> dict[str, Any]:
    value = strict_json_loads(read_regular(root / "rappid.json"), where="migration source identity")
    require(
        isinstance(value, dict)
        and value.get("schema", "rapp/1") == "rapp/1"
        and rappid_valid(value.get("rappid")),
        "REFUSE_MIGRATION_SOURCE",
        "migration source lacks a valid RAPP/1 identity",
    )
    kind = value.get("kind", "workspace")
    require(
        kind in {"workspace", "organization"},
        "REFUSE_MIGRATION_SOURCE",
        "migration supports only workspace or Organization sources",
    )
    world_id = value.get("world_id")
    if world_id is None:
        declaration = root / ".rapp-hive/declaration.json"
        if declaration.exists() and not declaration.is_symlink():
            document = strict_json_loads(read_regular(declaration), where="Hive declaration")
            world_id = document.get("world_id") if isinstance(document, dict) else None
    if pointer:
        pointer_world_id(world_id, "migration source world_id")
    else:
        require(
            isinstance(world_id, str)
            and bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", world_id))
            and len(world_id) <= 64,
            "REFUSE_MIGRATION_SOURCE",
            "migration source must declare one valid world_id",
        )
    name = value.get("name") or root.name
    require(
        isinstance(name, str) and bool(name),
        "REFUSE_MIGRATION_SOURCE",
        "migration source name is unavailable",
    )
    mode = value.get("mode", "solo")
    require(
        mode in {"solo", "hive"},
        "REFUSE_MIGRATION_SOURCE",
        "migration source mode is invalid",
    )
    return {
        "kind": kind,
        "mode": mode,
        "name": name,
        "rappid": value["rappid"],
        "schema": "rapp/1",
        "workspace_spec": "rapp-work-sdk/1",
        "world_id": world_id,
    }


def source_binding(root: Path) -> dict[str, Any]:
    root = assert_no_symlinks(absolute_path(root))
    identity = _source_identity(root)
    authority: list[dict[str, Any]] = []
    for relative in SOURCE_AUTHORITY_PATHS:
        path = root / relative
        if not path.exists() and not path.is_symlink():
            continue
        raw = read_regular(path)
        authority.append(
            {
                "bytes": len(raw),
                "path": relative,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    require(
        any(item["path"] == "rappid.json" for item in authority),
        "REFUSE_MIGRATION_SOURCE",
        "migration source identity could not be bound",
    )
    raw_identity = strict_json_loads(read_regular(root / "rappid.json"), where="source identity")
    require(
        isinstance(raw_identity, dict),
        "REFUSE_MIGRATION_SOURCE",
        "migration source identity must be an object",
    )
    return {
        "authority_files": authority,
        "kind": identity["kind"],
        "path": str(root),
        "profile": raw_identity.get("workspace_spec", "legacy-unversioned"),
        "rappid": identity["rappid"],
        "root_identity": path_identity(root),
        "schema": "rapp-work-migration-source/1",
        "world_id": identity["world_id"],
    }


@dataclass(frozen=True)
class MigrationPlan:
    source: str
    target: str
    source_binding: dict[str, Any]
    actions: tuple[FileAction, ...]

    SCHEMA = "rapp-work-migration-plan/1"

    def __post_init__(self) -> None:
        require(
            str(absolute_path(self.source)) == self.source
            and str(absolute_path(self.target)) == self.target,
            "REFUSE_MIGRATION_PLAN",
            "migration source and target must be absolute lexical paths",
        )
        require(
            self.source != self.target
            and absolute_path(self.source) not in absolute_path(self.target).parents
            and absolute_path(self.target) not in absolute_path(self.source).parents,
            "REFUSE_MIGRATION_OVERLAP",
            "migration source and target must be disjoint",
        )
        require(
            [action.path for action in self.actions]
            == sorted({action.path for action in self.actions})
            and len(self.actions) <= 512
            and sum(len(action.content) for action in self.actions) <= 64 * 1024 * 1024,
            "REFUSE_MIGRATION_PLAN",
            "migration actions must be unique, sorted, and bounded",
        )
        canonical_bytes(self.source_binding)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "network": False,
            "operation": "migrate",
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "schema": self.SCHEMA,
            "source": self.source,
            "source_binding": self.source_binding,
            "target": self.target,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> MigrationPlan:
        item = closed_object(
            value,
            required={
                "actions",
                "network",
                "operation",
                "profile",
                "protocol",
                "schema",
                "source",
                "source_binding",
                "target",
            },
            where="migration plan",
        )
        require(
            item["schema"] == cls.SCHEMA
            and item["operation"] == "migrate"
            and item["network"] is False
            and item["profile"] == "rapp-work-sdk/1"
            and item["protocol"] == "rapp-work/1"
            and isinstance(item["source_binding"], dict)
            and isinstance(item["actions"], list),
            "REFUSE_MIGRATION_PLAN",
            "migration plan contract mismatch",
        )
        return cls(
            source=item["source"],
            target=item["target"],
            source_binding=dict(item["source_binding"]),
            actions=tuple(FileAction.from_dict(action) for action in item["actions"]),
        )


@dataclass(frozen=True)
class MigrationReceipt:
    plan_sha256: str
    source: str
    source_binding_sha256: str
    target: str
    target_files: tuple[dict[str, Any], ...]

    SCHEMA = "rapp-work-migration-receipt/1"

    def __post_init__(self) -> None:
        require(
            bool(HEX64.fullmatch(self.plan_sha256))
            and bool(HEX64.fullmatch(self.source_binding_sha256)),
            "REFUSE_MIGRATION_RECEIPT",
            "migration receipt hash is invalid",
        )
        require(
            str(absolute_path(self.source)) == self.source
            and str(absolute_path(self.target)) == self.target,
            "REFUSE_MIGRATION_RECEIPT",
            "migration receipt source or target is not an absolute lexical path",
        )
        paths: list[str] = []
        for raw in self.target_files:
            item = closed_object(
                raw,
                required={"bytes", "path", "sha256"},
                where="migration receipt file",
            )
            paths.append(safe_relative(item["path"]))
            require(
                type(item["bytes"]) is int
                and 0 <= item["bytes"] <= 16 * 1024 * 1024
                and isinstance(item["sha256"], str)
                and bool(HEX64.fullmatch(item["sha256"])),
                "REFUSE_MIGRATION_RECEIPT",
                "migration receipt file commitment is invalid",
            )
        require(
            paths == sorted(set(paths)),
            "REFUSE_MIGRATION_RECEIPT",
            "migration receipt inventory must be unique and path sorted",
        )

    @property
    def target_inventory_sha256(self) -> str:
        return canonical_sha256(list(self.target_files))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_sha256": self.plan_sha256,
            "schema": self.SCHEMA,
            "source": self.source,
            "source_binding_sha256": self.source_binding_sha256,
            "source_preserved": True,
            "status": "completed",
            "target": self.target,
            "target_files": list(self.target_files),
            "target_inventory_sha256": self.target_inventory_sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> MigrationReceipt:
        item = closed_object(
            value,
            required={
                "plan_sha256",
                "schema",
                "source",
                "source_binding_sha256",
                "source_preserved",
                "status",
                "target",
                "target_files",
                "target_inventory_sha256",
            },
            where="migration receipt",
        )
        require(
            item["schema"] == cls.SCHEMA
            and item["status"] == "completed"
            and item["source_preserved"] is True
            and isinstance(item["target_files"], list),
            "REFUSE_MIGRATION_RECEIPT",
            "migration receipt contract mismatch",
        )
        receipt = cls(
            plan_sha256=item["plan_sha256"],
            source=item["source"],
            source_binding_sha256=item["source_binding_sha256"],
            target=item["target"],
            target_files=tuple(dict(entry) for entry in item["target_files"]),
        )
        require(
            item["target_inventory_sha256"] == receipt.target_inventory_sha256,
            "REFUSE_MIGRATION_RECEIPT",
            "migration receipt inventory commitment mismatch",
        )
        return receipt


def _migration_files(source: Path, binding: dict[str, Any]) -> dict[str, bytes]:
    identity = _source_identity(source)
    files = (
        _organization_files(identity)
        if identity["kind"] == "organization"
        else _workspace_files(identity)
    )
    if identity["kind"] == "organization":
        pointers = Organization.load(source).pointers()
        files["workspaces.json"] = canonical_bytes(
            {
                "organization_rappid": identity["rappid"],
                "schema": "rapp-work-organization-pointers/1",
                "workspaces": list(pointers),
            }
        )
    pointer = {
        "execution": "never",
        "source": str(source),
        "source_binding_sha256": canonical_sha256(binding),
        "source_profile": binding["profile"],
        "source_rappid": binding["rappid"],
        "source_world_id": binding["world_id"],
        "schema": "rapp-work-migration-source-pointer/1",
    }
    files[".rapp-work/migration-source.json"] = canonical_bytes(pointer)
    managed_paths = {
        path: content
        for path, content in files.items()
        if path.startswith(".rapp-work/") or path.startswith(".github/skills/rapp-work-sdk/")
    }
    managed_paths.pop(".rapp-work/managed.json", None)
    files[".rapp-work/managed.json"] = canonical_bytes(_managed_record(managed_paths))
    return files


def plan_migration(source: Path, target: Path) -> MigrationPlan:
    source = assert_no_symlinks(absolute_path(source))
    target = absolute_path(target)
    if target.exists() or target.is_symlink():
        assert_no_symlinks(target)
    else:
        assert_no_symlinks(target.parent)
    binding = source_binding(source)
    files = _migration_files(source, binding)
    actions = tuple(
        FileAction("create", path, content)
        for path, content in sorted(files.items())
    )
    return MigrationPlan(
        source=str(source),
        target=str(target),
        source_binding=binding,
        actions=actions,
    )


def _hive_label(value: Any, where: str) -> str:
    require(
        isinstance(value, str) and bool(HIVE_LABEL.fullmatch(value)),
        "REFUSE_POINTER_CHANNEL",
        f"{where} must be a lowercase rapp-hive/1 label",
    )
    return str(value)


def _profile_text(value: Any, where: str, code: str) -> str:
    require(
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(0x20 <= ord(character) != 0x7F for character in value),
        code,
        f"{where} must be 1 to 128 characters without control characters",
    )
    return str(value)


def _locator_components_safe(value: str) -> bool:
    return all(part not in {".", ".."} for part in value.split("/") if part)


def authority_locator(value: Any, kind: str) -> str:
    """Validate a credential-free authority channel locator (transport metadata only)."""

    require(
        isinstance(value, str)
        and 1 <= len(value) <= 2048
        and all(0x21 <= ord(character) <= 0x7E for character in value),
        "REFUSE_POINTER_CHANNEL",
        "authority channel locator must be 1 to 2048 printable ASCII characters",
    )
    require(
        not any(character in LOCATOR_FORBIDDEN for character in value),
        "REFUSE_POINTER_CHANNEL",
        "authority channel locator must not carry user information, queries, or fragments",
    )
    if kind == "github":
        valid = bool(GITHUB_LOCATOR.fullmatch(value)) and not value.endswith(".git")
        where = value[len("https://github.com/") :]
    elif "://" in value:
        valid = bool(HTTPS_LOCATOR.fullmatch(value))
        where = value.split("://", 1)[1].partition("/")[2]
    else:
        valid = bool(OPAQUE_LOCATOR.fullmatch(value) or RELATIVE_LOCATOR.fullmatch(value))
        where = value.split(":", 1)[1] if OPAQUE_LOCATOR.fullmatch(value) else value
    require(
        valid and _locator_components_safe(where),
        "REFUSE_POINTER_CHANNEL",
        "authority channel locator must be a credential-free https URL, opaque locator, "
        "or relative locator; GitHub channels use https://github.com/<owner>/<repository>",
    )
    return str(value)


def authority_channel(value: Any) -> dict[str, str]:
    item = closed_object(value, required={"id", "kind", "locator"}, where="authority channel")
    channel_id = _hive_label(item["id"], "authority channel id")
    require(
        item["kind"] in HIVE_CHANNEL_KINDS,
        "REFUSE_POINTER_CHANNEL",
        "authority channel kind is not a rapp-hive/1 channel kind",
        allowed=list(HIVE_CHANNEL_KINDS),
    )
    kind = str(item["kind"])
    return {"id": channel_id, "kind": kind, "locator": authority_locator(item["locator"], kind)}


def _authority_path(value: Any) -> str:
    require(isinstance(value, str), "REFUSE_POINTER_AUTHORITY", "authority path must be text")
    relative = safe_relative(value)
    require(
        all(part.casefold() != ".git" for part in PurePosixPath(relative).parts),
        "REFUSE_POINTER_AUTHORITY",
        "Git internals are never source authority and are never read",
        path=relative,
    )
    return relative


def hive_description(value: Any) -> dict[str, Any]:
    """Validate the operator's closed description of a source without a workspace identity."""

    item = closed_object(
        value,
        required={"authority_channel", "authority_paths", "hive_rappid", "world_id"},
        where="Hive description",
    )
    require(
        isinstance(item["hive_rappid"], str) and rappid_valid(item["hive_rappid"]),
        "REFUSE_POINTER_SOURCE",
        "Hive description hive_rappid must be an existing valid RAPP/1 RAPPID",
    )
    paths = item["authority_paths"]
    require(
        isinstance(paths, list) and 1 <= len(paths) <= POINTER_MAX_NAMED_PATHS,
        "REFUSE_POINTER_AUTHORITY",
        f"Hive description names 1 to {POINTER_MAX_NAMED_PATHS} authority paths",
    )
    checked = [_authority_path(path) for path in paths]
    require(
        checked == sorted(set(checked)),
        "REFUSE_POINTER_AUTHORITY",
        "Hive description authority paths must be unique and sorted",
    )
    return {
        "authority_channel": authority_channel(item["authority_channel"]),
        "authority_paths": checked,
        "hive_rappid": str(item["hive_rappid"]),
        "world_id": pointer_world_id(item["world_id"], "Hive description world_id"),
    }


def _read_authority(
    root: Path,
    fixed: tuple[str, ...],
    named: list[str],
) -> dict[str, bytes]:
    selected = set(named)
    for relative in named:
        path = root / relative
        require(
            path.exists() or path.is_symlink(),
            "REFUSE_POINTER_AUTHORITY",
            "named source authority file is missing",
            path=relative,
        )
    for relative in fixed:
        path = root / relative
        if path.exists() or path.is_symlink():
            selected.add(relative)
    contents: dict[str, bytes] = {}
    total = 0
    for relative in sorted(selected):
        raw = read_regular(root / relative)
        total += len(raw)
        require(
            total <= POINTER_MAX_AUTHORITY_BYTES,
            "REFUSE_POINTER_AUTHORITY",
            "bound source authority exceeds the byte limit",
            limit=POINTER_MAX_AUTHORITY_BYTES,
        )
        contents[relative] = raw
    require(
        bool(contents),
        "REFUSE_POINTER_AUTHORITY",
        "pointer-only successor must bind at least one source authority file",
    )
    return contents


def _declared_channel(declaration: dict[str, Any]) -> dict[str, Any] | None:
    channels = declaration.get("channels")
    if not isinstance(channels, list):
        return None
    wanted = declaration.get("authority_channel_id")
    for channel in channels:
        if isinstance(channel, dict) and channel.get("id") == wanted:
            return {key: channel.get(key) for key in ("id", "kind", "locator")}
    return None


def _corroborate(contents: dict[str, bytes], description: dict[str, Any]) -> None:
    """Refuse a description contradicted by a recognized Hive record in the bound bytes."""

    for relative, raw in sorted(contents.items()):
        if not relative.endswith(".json"):
            continue
        try:
            value = strict_json_loads(raw, where="source authority record")
        except Refusal:
            continue
        if not isinstance(value, dict):
            continue
        payload = value.get("payload")
        if value.get("schema") == "rapp-hive/1-declaration":
            declaration: dict[str, Any] | None = value
        elif (
            set(value) == FRAME_KEYS
            and value.get("spec") == "rapp/1"
            and value.get("kind") == "hive.declaration"
            and isinstance(payload, dict)
            and payload.get("schema") == "rapp-hive/1-declaration"
        ):
            declaration = payload
        else:
            declaration = None
        if declaration is not None:
            require(
                declaration.get("hive_rappid") == description["hive_rappid"]
                and declaration.get("world_id") == description["world_id"]
                and _declared_channel(declaration) == description["authority_channel"],
                "REFUSE_POINTER_CLAIM",
                "Hive description differs from the source's rapp-hive/1 declaration",
                path=relative,
            )
        elif value.get("schema") == "rapp-private-hive-owner-anchor/1":
            require(
                value.get("hive_rappid") == description["hive_rappid"]
                and value.get("world_id") == description["world_id"],
                "REFUSE_POINTER_CLAIM",
                "Hive description differs from the source's Private Hive owner anchor",
                path=relative,
            )


def _commitments(contents: dict[str, bytes]) -> list[dict[str, Any]]:
    return [
        {"bytes": len(raw), "path": relative, "sha256": hashlib.sha256(raw).hexdigest()}
        for relative, raw in sorted(contents.items())
    ]


def pointer_source_binding(root: Path, hive: Any = None) -> dict[str, Any]:
    """Bind a pointer-only successor source without copying or interpreting its state."""

    root = assert_no_symlinks(absolute_path(root))
    identity_path = root / "rappid.json"
    if identity_path.exists() or identity_path.is_symlink():
        require(
            hive is None,
            "REFUSE_POINTER_SOURCE",
            "a source with rappid.json is described by its own identity; omit the Hive description",
        )
        identity = _source_identity(root, pointer=True)
        contents = _read_authority(root, SOURCE_AUTHORITY_PATHS, [])
        raw_identity = strict_json_loads(contents["rappid.json"], where="source identity")
        require(
            isinstance(raw_identity, dict),
            "REFUSE_MIGRATION_SOURCE",
            "migration source identity must be an object",
        )
        profile = _profile_text(
            raw_identity.get("workspace_spec", "legacy-unversioned"),
            "migration source workspace_spec",
            "REFUSE_MIGRATION_SOURCE",
        )
        return {
            "authority_channel": None,
            "authority_files": _commitments(contents),
            "described_paths": [],
            "identity_source": "source-identity-file",
            "kind": identity["kind"],
            "path": str(root),
            "profile": profile,
            "rappid": identity["rappid"],
            "root_identity": path_identity(root),
            "schema": POINTER_SOURCE_SCHEMA,
            "world_id": identity["world_id"],
        }
    require(
        hive is not None,
        "REFUSE_POINTER_SOURCE",
        "a source without rappid.json needs an explicit, reviewed Hive description",
    )
    description = hive_description(hive)
    contents = _read_authority(root, HIVE_AUTHORITY_PATHS, description["authority_paths"])
    _corroborate(contents, description)
    return {
        "authority_channel": description["authority_channel"],
        "authority_files": _commitments(contents),
        "described_paths": description["authority_paths"],
        "identity_source": "operator-description",
        "kind": "hive",
        "path": str(root),
        "profile": None,
        "rappid": description["hive_rappid"],
        "root_identity": path_identity(root),
        "schema": POINTER_SOURCE_SCHEMA,
        "world_id": description["world_id"],
    }


def _description_from_binding(binding: dict[str, Any]) -> dict[str, Any] | None:
    if binding["identity_source"] != "operator-description":
        return None
    return {
        "authority_channel": binding["authority_channel"],
        "authority_paths": list(binding["described_paths"]),
        "hive_rappid": binding["rappid"],
        "world_id": binding["world_id"],
    }


def _check_pointer_binding(binding: Any) -> dict[str, Any]:
    item = closed_object(
        binding,
        required={
            "authority_channel",
            "authority_files",
            "described_paths",
            "identity_source",
            "kind",
            "path",
            "profile",
            "rappid",
            "root_identity",
            "schema",
            "world_id",
        },
        where="pointer-only source binding",
    )
    operator = item["identity_source"] == "operator-description"
    root_identity = item["root_identity"]
    require(
        item["schema"] == POINTER_SOURCE_SCHEMA
        and isinstance(item["identity_source"], str)
        and item["identity_source"] in {"operator-description", "source-identity-file"}
        and isinstance(item["kind"], str)
        and item["kind"] in ({"hive"} if operator else {"workspace", "organization"})
        and isinstance(root_identity, dict)
        and set(root_identity) == {"device", "inode", "mode"}
        and all(type(root_identity[key]) is int for key in root_identity)
        and isinstance(item["rappid"], str)
        and rappid_valid(item["rappid"])
        and isinstance(item["path"], str)
        and isinstance(item["authority_files"], list)
        and bool(item["authority_files"])
        and isinstance(item["described_paths"], list)
        and (bool(item["described_paths"]) if operator else not item["described_paths"])
        and (item["authority_channel"] is not None) == operator
        and (item["profile"] is None) == operator,
        "REFUSE_MIGRATION_PLAN",
        "pointer-only source binding contract mismatch",
    )
    pointer_world_id(item["world_id"], "pointer-only source world_id")
    if operator:
        authority_channel(item["authority_channel"])
        for relative in item["described_paths"]:
            _authority_path(relative)
    else:
        _profile_text(item["profile"], "pointer-only source profile", "REFUSE_MIGRATION_PLAN")
    _check_commitments(
        item["authority_files"],
        "pointer-only source binding",
        "REFUSE_MIGRATION_PLAN",
    )
    return item


def _check_commitments(entries: Any, where: str, code: str) -> None:
    require(
        isinstance(entries, list) and bool(entries),
        code,
        f"{where} authority files are missing",
    )
    paths: list[str] = []
    for raw in entries:
        entry = closed_object(raw, required={"bytes", "path", "sha256"}, where=f"{where} file")
        paths.append(safe_relative(entry["path"]))
        require(
            type(entry["bytes"]) is int
            and 0 <= entry["bytes"] <= POINTER_MAX_AUTHORITY_BYTES
            and isinstance(entry["sha256"], str)
            and bool(HEX64.fullmatch(entry["sha256"])),
            code,
            f"{where} authority commitment is invalid",
        )
    require(
        paths == sorted(set(paths)),
        code,
        f"{where} authority files must be unique and path sorted",
    )


def pointer_record(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "authority_channel": binding["authority_channel"],
        "authority_files": list(binding["authority_files"]),
        "content_copied": False,
        "execution": "never",
        "grants_authority": False,
        "identity_source": binding["identity_source"],
        "schema": POINTER_SCHEMA,
        "source": binding["path"],
        "source_binding_sha256": canonical_sha256(binding),
        "source_kind": binding["kind"],
        "source_profile": binding["profile"],
        "source_rappid": binding["rappid"],
        "source_world_id": binding["world_id"],
    }


def validate_pointer_record(value: Any) -> dict[str, Any]:
    """Validate a closed rapp-work-pointer-successor/1 record."""

    item = closed_object(
        value,
        required={
            "authority_channel",
            "authority_files",
            "content_copied",
            "execution",
            "grants_authority",
            "identity_source",
            "schema",
            "source",
            "source_binding_sha256",
            "source_kind",
            "source_profile",
            "source_rappid",
            "source_world_id",
        },
        where="pointer-only successor record",
    )
    operator = item["identity_source"] == "operator-description"
    require(
        item["schema"] == POINTER_SCHEMA
        and item["content_copied"] is False
        and item["execution"] == "never"
        and item["grants_authority"] is False
        and isinstance(item["identity_source"], str)
        and item["identity_source"] in {"operator-description", "source-identity-file"}
        and isinstance(item["source_kind"], str)
        and item["source_kind"] in ({"hive"} if operator else {"workspace", "organization"})
        and isinstance(item["source"], str)
        and str(absolute_path(item["source"])) == item["source"]
        and isinstance(item["source_binding_sha256"], str)
        and bool(HEX64.fullmatch(item["source_binding_sha256"]))
        and isinstance(item["source_rappid"], str)
        and rappid_valid(item["source_rappid"])
        and (item["authority_channel"] is not None) == operator
        and (item["source_profile"] is None) == operator,
        "REFUSE_POINTER_RECORD",
        "pointer-only successor record contract mismatch",
    )
    pointer_world_id(item["source_world_id"], "pointer-only successor source_world_id")
    if operator:
        authority_channel(item["authority_channel"])
    else:
        _profile_text(
            item["source_profile"],
            "pointer-only successor source_profile",
            "REFUSE_POINTER_RECORD",
        )
    _check_commitments(
        item["authority_files"],
        "pointer-only successor record",
        "REFUSE_POINTER_RECORD",
    )
    return item


@dataclass(frozen=True)
class PointerSuccessorPlan:
    """Create-only plan for a successor that records only a source pointer."""

    source: str
    target: str
    source_binding: dict[str, Any]
    actions: tuple[FileAction, ...]

    SCHEMA = POINTER_PLAN_SCHEMA

    def __post_init__(self) -> None:
        require(
            str(absolute_path(self.source)) == self.source
            and str(absolute_path(self.target)) == self.target,
            "REFUSE_MIGRATION_PLAN",
            "migration source and target must be absolute lexical paths",
        )
        require(
            self.source != self.target
            and absolute_path(self.source) not in absolute_path(self.target).parents
            and absolute_path(self.target) not in absolute_path(self.source).parents,
            "REFUSE_MIGRATION_OVERLAP",
            "migration source and target must be disjoint",
        )
        _check_pointer_binding(self.source_binding)
        require(
            self.source_binding["path"] == self.source,
            "REFUSE_MIGRATION_PLAN",
            "pointer-only source binding names another source",
        )
        require(
            len(self.actions) == 1
            and self.actions[0].operation == "create"
            and self.actions[0].path == POINTER_PATH
            and self.actions[0].mode == 0o600,
            "REFUSE_MIGRATION_PLAN",
            "pointer-only successor plan creates exactly its pointer record",
        )
        require(
            self.actions[0].content == canonical_bytes(pointer_record(self.source_binding)),
            "REFUSE_MIGRATION_PLAN",
            "pointer-only successor record differs from its source binding",
        )
        validate_pointer_record(strict_json_loads(self.actions[0].content, where="pointer record"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "network": False,
            "operation": "migrate",
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "schema": self.SCHEMA,
            "source": self.source,
            "source_binding": self.source_binding,
            "successor": POINTER_SUCCESSOR,
            "target": self.target,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> PointerSuccessorPlan:
        item = closed_object(
            value,
            required={
                "actions",
                "network",
                "operation",
                "profile",
                "protocol",
                "schema",
                "source",
                "source_binding",
                "successor",
                "target",
            },
            where="pointer-only successor plan",
        )
        require(
            item["schema"] == cls.SCHEMA
            and item["operation"] == "migrate"
            and item["network"] is False
            and item["profile"] == "rapp-work-sdk/1"
            and item["protocol"] == "rapp-work/1"
            and item["successor"] == POINTER_SUCCESSOR
            and isinstance(item["source"], str)
            and isinstance(item["target"], str)
            and isinstance(item["source_binding"], dict)
            and isinstance(item["actions"], list),
            "REFUSE_MIGRATION_PLAN",
            "pointer-only successor plan contract mismatch",
        )
        return cls(
            source=item["source"],
            target=item["target"],
            source_binding=dict(item["source_binding"]),
            actions=tuple(FileAction.from_dict(action) for action in item["actions"]),
        )


MigrationLike: TypeAlias = MigrationPlan | PointerSuccessorPlan


def plan_pointer_successor(source: Path, target: Path, *, hive: Any = None) -> PointerSuccessorPlan:
    source = assert_no_symlinks(absolute_path(source))
    target = absolute_path(target)
    if target.exists() or target.is_symlink():
        assert_no_symlinks(target)
    else:
        assert_no_symlinks(target.parent)
    binding = pointer_source_binding(source, hive)
    record = validate_pointer_record(pointer_record(binding))
    return PointerSuccessorPlan(
        source=str(source),
        target=str(target),
        source_binding=binding,
        actions=(FileAction("create", POINTER_PATH, canonical_bytes(record)),),
    )


def _inventory(entries: dict[str, bytes]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "bytes": len(content),
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(entries.items())
    )


def _recovery(plan: MigrationLike) -> dict[str, Any]:
    return {
        "plan_sha256": plan.sha256,
        "schema": "rapp-work-migration-recovery/1",
        "source": plan.source,
        "source_binding_sha256": canonical_sha256(plan.source_binding),
        "target": plan.target,
    }


def _receipt(plan: MigrationLike) -> MigrationReceipt:
    entries = {action.path: action.content for action in plan.actions}
    entries[".rapp-work/migration-recovery.json"] = canonical_bytes(_recovery(plan))
    return MigrationReceipt(
        plan_sha256=plan.sha256,
        source=plan.source,
        source_binding_sha256=canonical_sha256(plan.source_binding),
        target=plan.target,
        target_files=_inventory(entries),
    )


def _verify_completed(plan: MigrationLike, target: Path) -> dict[str, Any]:
    receipt_path = target / ".rapp-work/migration-receipt.json"
    receipt = MigrationReceipt.from_dict(
        strict_json_loads(read_regular(receipt_path), where="migration receipt")
    )
    expected = _receipt(plan)
    require(
        receipt.to_dict() == expected.to_dict(),
        "REFUSE_MIGRATION_REPLAY",
        "completed migration receipt differs from the exact source-bound plan",
    )
    for entry in receipt.target_files:
        relative = safe_relative(entry["path"])
        raw = read_regular(target / relative)
        require(
            type(entry["bytes"]) is int
            and len(raw) == entry["bytes"]
            and hashlib.sha256(raw).hexdigest() == entry["sha256"],
            "REFUSE_MIGRATION_REPLAY",
            "completed migration target inventory differs",
            path=relative,
        )
    return {
        "effects": False,
        "plan_sha256": plan.sha256,
        "receipt_sha256": hashlib.sha256(read_regular(receipt_path)).hexdigest(),
        "source_preserved": True,
        "status": "unchanged",
        "target": str(target),
    }


def _write_staged(staging: Path, relative: str, content: bytes) -> None:
    parent = Path(relative).parent.as_posix()
    if parent != ".":
        create_directories(staging, parent)
    destination = staging / relative
    if destination.exists() or destination.is_symlink():
        require(
            read_regular(destination) == content,
            "REFUSE_RECOVERY_COLLISION",
            "migration recovery file differs from the source-bound plan",
            path=relative,
        )
    else:
        write_new(destination, content)


def _complete(
    plan: MigrationLike,
    *,
    target: Path,
    rebind: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    if target.exists() or target.is_symlink():
        assert_no_symlinks(target)
        return _verify_completed(plan, target)

    staging = target.parent / f".{target.name}.rapp-work-migrate-{plan.sha256[:24]}"
    recovery_bytes = canonical_bytes(_recovery(plan))
    if staging.exists() or staging.is_symlink():
        assert_no_symlinks(staging)
        private_directory(staging)
        require(
            read_regular(staging / ".rapp-work/migration-recovery.json") == recovery_bytes,
            "REFUSE_RECOVERY_BINDING",
            "migration staging belongs to another source or plan",
        )
    else:
        with directory_fd(target.parent) as parent:
            os.mkdir(staging.name, 0o700, dir_fd=parent)
            os.fsync(parent)
        private_directory(staging)
        _write_staged(staging, ".rapp-work/migration-recovery.json", recovery_bytes)

    for action in plan.actions:
        _write_staged(staging, action.path, action.content)
    receipt = _receipt(plan)
    receipt_bytes = canonical_bytes(receipt.to_dict())
    _write_staged(staging, ".rapp-work/migration-receipt.json", receipt_bytes)
    require(
        rebind() == plan.source_binding,
        "REFUSE_MIGRATION_SOURCE_CHANGED",
        "migration source authority changed during staging",
    )
    _verify_completed(plan, staging)
    activate_directory_noreplace(staging, target)
    completed = _verify_completed(plan, target)
    return {
        **completed,
        "effects": True,
        "status": "migrated",
    }


def apply_migration(
    plan: MigrationPlan,
    *,
    source: Path,
    target: Path,
    plan_sha256: str,
) -> dict[str, Any]:
    require(
        plan.sha256 == plan_sha256,
        "REFUSE_PLAN_HASH",
        "exact canonical migration plan SHA-256 is required",
        actual=plan.sha256,
        supplied=plan_sha256,
    )
    source = assert_no_symlinks(absolute_path(source))
    target = absolute_path(target)
    require(
        plan.source == str(source) and plan.target == str(target),
        "REFUSE_PLAN_TARGET",
        "migration plan source or target differs from the request",
    )
    current_binding = source_binding(source)
    require(
        current_binding == plan.source_binding,
        "REFUSE_MIGRATION_SOURCE_CHANGED",
        "migration source authority changed after planning",
    )
    expected = plan_migration(source, target)
    require(
        expected.to_dict() == plan.to_dict(),
        "REFUSE_MIGRATION_PLAN",
        "migration plan contains unqualified output bytes",
    )
    return _complete(plan, target=target, rebind=lambda: source_binding(source))


def apply_pointer_successor(
    plan: PointerSuccessorPlan,
    *,
    source: Path,
    target: Path,
    plan_sha256: str,
) -> dict[str, Any]:
    require(
        plan.sha256 == plan_sha256,
        "REFUSE_PLAN_HASH",
        "exact canonical migration plan SHA-256 is required",
        actual=plan.sha256,
        supplied=plan_sha256,
    )
    source = assert_no_symlinks(absolute_path(source))
    target = absolute_path(target)
    require(
        plan.source == str(source) and plan.target == str(target),
        "REFUSE_PLAN_TARGET",
        "migration plan source or target differs from the request",
    )
    description = _description_from_binding(plan.source_binding)
    current_binding = pointer_source_binding(source, description)
    require(
        current_binding == plan.source_binding,
        "REFUSE_MIGRATION_SOURCE_CHANGED",
        "migration source authority changed after planning",
    )
    expected = plan_pointer_successor(source, target, hive=description)
    require(
        expected.to_dict() == plan.to_dict(),
        "REFUSE_MIGRATION_PLAN",
        "migration plan contains unqualified output bytes",
    )
    return _complete(
        plan,
        target=target,
        rebind=lambda: pointer_source_binding(source, description),
    )
