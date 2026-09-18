from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from .errors import require
from .plans import FileAction
from .rapp1 import rappid_valid
from .workspace import Organization, _managed_record, _organization_files, _workspace_files

HEX64 = re.compile(r"^[0-9a-f]{64}$")
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


def _source_identity(root: Path) -> dict[str, Any]:
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


def _inventory(entries: dict[str, bytes]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "bytes": len(content),
            "path": path,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        for path, content in sorted(entries.items())
    )


def _recovery(plan: MigrationPlan) -> dict[str, Any]:
    return {
        "plan_sha256": plan.sha256,
        "schema": "rapp-work-migration-recovery/1",
        "source": plan.source,
        "source_binding_sha256": canonical_sha256(plan.source_binding),
        "target": plan.target,
    }


def _receipt(plan: MigrationPlan) -> MigrationReceipt:
    entries = {action.path: action.content for action in plan.actions}
    entries[".rapp-work/migration-recovery.json"] = canonical_bytes(_recovery(plan))
    return MigrationReceipt(
        plan_sha256=plan.sha256,
        source=plan.source,
        source_binding_sha256=canonical_sha256(plan.source_binding),
        target=plan.target,
        target_files=_inventory(entries),
    )


def _verify_completed(plan: MigrationPlan, target: Path) -> dict[str, Any]:
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
        source_binding(source) == plan.source_binding,
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
