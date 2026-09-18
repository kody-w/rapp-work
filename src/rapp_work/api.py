from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ._json import closed_object, strict_json_loads
from ._paths import absolute_path, assert_no_symlinks, read_regular
from .constants import (
    PROTOCOL_ID,
    PUBLIC_OPERATIONS,
    RESULT_SCHEMA,
    SDK_VERSION,
    WORKSPACE_PROFILE_ID,
)
from .discovery import api_metadata, discover_roots
from .errors import Refusal, require
from .migration import MigrationPlan, apply_migration, plan_migration
from .plans import ReleasePlan
from .profiles import ProfileRegistry, verify_source_estate
from .rapp1 import rappid_valid
from .workspace import (
    Organization,
    Workspace,
    apply_scaffold,
    apply_update,
    load_identity,
    plan_scaffold,
    plan_update,
)

Operation = Callable[[dict[str, Any]], dict[str, Any]]


def _envelope(
    operation: str,
    *,
    status: str,
    result: dict[str, Any] | None,
    refusal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "operation": operation,
        "profile": WORKSPACE_PROFILE_ID,
        "protocol": PROTOCOL_ID,
        "refusal": refusal,
        "result": result,
        "schema": RESULT_SCHEMA,
        "status": status,
    }


def _root_input(value: Any) -> Path:
    require(isinstance(value, str), "REFUSE_INPUT_SHAPE", "root must be a path string")
    return absolute_path(value)


def _legacy_identity(root: Path) -> dict[str, Any] | None:
    value = strict_json_loads(read_regular(root / "rappid.json"), where="legacy identity")
    if (
        not isinstance(value, dict)
        or value.get("schema") not in {None, "rapp/1"}
        or not rappid_valid(value.get("rappid"))
    ):
        return None
    return {
        "kind": value.get("kind", "workspace"),
        "profile": value.get("workspace_spec", "legacy-unversioned"),
        "rappid": value["rappid"],
        "world_id": value.get("world_id"),
    }


def _status(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(inputs, required=set(), optional={"root"}, where="status input")
    root = _root_input(item.get("root", str(Path.cwd())))
    root = assert_no_symlinks(root)
    classification = "directory"
    subject: dict[str, Any] | None = None
    if (root / "RAPP1_PIN.json").is_file() and (root / "registry.json").is_file():
        classification = "protocol-estate"
    elif (root / "rappid.json").is_file():
        try:
            identity = load_identity(root)
            classification = str(identity["kind"])
            subject = {
                "profile": identity.get("workspace_spec"),
                "rappid": identity["rappid"],
                "world_id": identity.get("world_id"),
            }
        except Refusal:
            legacy = _legacy_identity(root)
            require(
                legacy is not None,
                "REFUSE_IDENTITY",
                "unrecognized legacy workspace identity",
            )
            assert legacy is not None
            classification = "legacy-workspace"
            subject = legacy
    registry = ProfileRegistry.default()
    return {
        "api": api_metadata(),
        "classification": classification,
        "network": False,
        "profiles": list(registry.ids()),
        "root": str(root),
        "sdk_version": SDK_VERSION,
        "status": "available",
        "subject": subject,
    }


def _verify(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(inputs, required=set(), optional={"root"}, where="verify input")
    root = _root_input(item.get("root", str(Path.cwd())))
    root = assert_no_symlinks(root)
    profile_result = ProfileRegistry.default().verify()
    subject: dict[str, Any]
    if (root / "RAPP1_PIN.json").is_file() and (root / "registry.json").is_file():
        subject = verify_source_estate(root)
    elif (root / "rappid.json").is_file():
        try:
            identity = load_identity(root)
        except Refusal:
            legacy = _legacy_identity(root)
            require(
                legacy is not None,
                "REFUSE_IDENTITY",
                "unrecognized legacy workspace identity",
            )
            assert legacy is not None
            subject = {
                **legacy,
                "status": "verified-legacy-identity-only",
            }
            return {
                "network": False,
                "profiles": profile_result,
                "root": str(root),
                "status": "verified",
                "subject": subject,
            }
        if identity["kind"] == "workspace":
            require(
                (root / ".rapp-work/managed.json").is_file(),
                "REFUSE_SDK_PROFILE",
                "workspace has no qualified SDK integration; run update planning first",
            )
            subject = Workspace.load(root).verify()
        elif identity["kind"] == "organization":
            subject = Organization.load(root).verify()
        else:
            subject = {
                "kind": identity["kind"],
                "rappid": identity["rappid"],
                "status": "verified-identity-only",
            }
    else:
        raise Refusal(
            "REFUSE_VERIFY_TARGET",
            "verify target is not a source estate, Workspace, or Organization",
            {"root": str(root)},
        )
    return {
        "network": False,
        "profiles": profile_result,
        "root": str(root),
        "status": "verified",
        "subject": subject,
    }


def _discover(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(
        inputs,
        required={"roots"},
        optional={"max_entries"},
        where="discover input",
    )
    require(
        isinstance(item["roots"], list)
        and all(isinstance(value, str) for value in item["roots"]),
        "REFUSE_INPUT_SHAPE",
        "discover roots must be an array of path strings",
    )
    maximum = item.get("max_entries", 10_000)
    require(
        type(maximum) is int,
        "REFUSE_INPUT_SHAPE",
        "discover max_entries must be an integer",
    )
    return discover_roots([Path(value) for value in item["roots"]], maximum=maximum)


def _apply_fields(item: dict[str, Any], *, operation: str) -> tuple[bool, Any, Any]:
    apply = item.get("apply", False)
    require(type(apply) is bool, "REFUSE_INPUT_SHAPE", f"{operation} apply must be Boolean")
    plan_value = item.get("plan")
    plan_sha256 = item.get("plan_sha256")
    if apply:
        require(
            isinstance(plan_value, dict) and isinstance(plan_sha256, str),
            "REFUSE_APPLY_REQUIRED",
            f"{operation} apply requires the complete plan and exact plan_sha256",
        )
    else:
        require(
            plan_value is None and plan_sha256 is None,
            "REFUSE_APPLY_REQUIRED",
            f"{operation} plan evidence is accepted only with explicit apply",
        )
    return apply, plan_value, plan_sha256


def _scaffold(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(
        inputs,
        required={"kind", "mode", "owner_label", "root", "slug", "world_id"},
        optional={"apply", "plan", "plan_sha256"},
        where="scaffold input",
    )
    apply, plan_value, plan_sha256 = _apply_fields(item, operation="scaffold")
    root = _root_input(item["root"])
    if not apply:
        plan = plan_scaffold(
            root=root,
            kind=item["kind"],
            owner_label=item["owner_label"],
            slug=item["slug"],
            world_id=item["world_id"],
            mode=item["mode"],
        )
        return {
            "effects": False,
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "status": "planned",
        }
    plan = ReleasePlan.from_dict(plan_value)
    require(plan.operation == "scaffold", "REFUSE_PLAN", "scaffold requires a scaffold plan")
    require(
        all(
            plan.subject.get(key) == item[key]
            for key in ("kind", "mode", "owner_label", "slug", "world_id")
        ),
        "REFUSE_PLAN_TARGET",
        "scaffold plan subject differs from the apply request",
    )
    return apply_scaffold(plan, root=root, plan_sha256=plan_sha256)


def _update(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(
        inputs,
        required={"root"},
        optional={"apply", "plan", "plan_sha256"},
        where="update input",
    )
    apply, plan_value, plan_sha256 = _apply_fields(item, operation="update")
    root = _root_input(item["root"])
    if not apply:
        plan = plan_update(root)
        return {
            "effects": False,
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "status": "planned",
        }
    plan = ReleasePlan.from_dict(plan_value)
    require(plan.operation == "update", "REFUSE_PLAN", "update requires an update plan")
    return apply_update(plan, root=root, plan_sha256=plan_sha256)


def _migrate(inputs: dict[str, Any]) -> dict[str, Any]:
    item = closed_object(
        inputs,
        required={"source", "target"},
        optional={"apply", "plan", "plan_sha256"},
        where="migrate input",
    )
    apply, plan_value, plan_sha256 = _apply_fields(item, operation="migrate")
    source, target = _root_input(item["source"]), _root_input(item["target"])
    if not apply:
        plan = plan_migration(source, target)
        return {
            "effects": False,
            "plan": plan.to_dict(),
            "plan_sha256": plan.sha256,
            "status": "planned",
        }
    plan = MigrationPlan.from_dict(plan_value)
    return apply_migration(
        plan,
        source=source,
        target=target,
        plan_sha256=plan_sha256,
    )


_OPERATIONS: dict[str, Operation] = {
    "discover": _discover,
    "migrate": _migrate,
    "scaffold": _scaffold,
    "status": _status,
    "update": _update,
    "verify": _verify,
}


def execute(operation: str, inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if operation not in _OPERATIONS:
        refusal = Refusal(
            "REFUSE_OPERATION",
            "unknown public operation",
            {"allowed": list(PUBLIC_OPERATIONS), "operation": operation},
        )
        return _envelope(operation, status="refused", result=None, refusal=refusal.as_dict())
    try:
        result = _OPERATIONS[operation](dict(inputs or {}))
    except Refusal as error:
        return _envelope(operation, status="refused", result=None, refusal=error.as_dict())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        refusal = Refusal("REFUSE_RUNTIME", str(error))
        return _envelope(operation, status="refused", result=None, refusal=refusal.as_dict())
    status = "planned" if result.get("status") == "planned" else (
        "applied" if result.get("effects") is True else "ok"
    )
    return _envelope(operation, status=status, result=result)


def status(inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return execute("status", inputs)


def verify(inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return execute("verify", inputs)


def discover(inputs: Mapping[str, Any]) -> dict[str, Any]:
    return execute("discover", inputs)


def scaffold(inputs: Mapping[str, Any]) -> dict[str, Any]:
    return execute("scaffold", inputs)


def update(inputs: Mapping[str, Any]) -> dict[str, Any]:
    return execute("update", inputs)


def migrate(inputs: Mapping[str, Any]) -> dict[str, Any]:
    return execute("migrate", inputs)
