from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

import rapp_work.workspace as workspace_module
from rapp_work import (
    FileAction,
    Organization,
    ReleasePlan,
    Workspace,
    scaffold,
    status,
    update,
    verify,
)
from rapp_work._json import canonical_bytes
from rapp_work.errors import Refusal
from rapp_work.rapp1 import mint_rappid


def request(root: Path, *, kind: str = "workspace") -> dict[str, object]:
    return {
        "kind": kind,
        "mode": "solo",
        "owner_label": "example",
        "root": str(root),
        "slug": "finance" if kind == "workspace" else "company",
        "world_id": "example-world",
    }


def apply_scaffold(root: Path, *, kind: str = "workspace") -> dict:
    planned = scaffold(request(root, kind=kind))
    assert planned["status"] == "planned"
    result = scaffold(
        {
            **request(root, kind=kind),
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
        }
    )
    assert result["status"] == "applied"
    return result


def snapshot(root: Path) -> dict[str, tuple[int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def test_scaffold_is_plan_only_by_default(sandbox: Path) -> None:
    root = sandbox / "workspace"
    result = scaffold(request(root))
    assert result["status"] == "planned"
    assert result["result"]["effects"] is False
    assert not root.exists()


def test_scaffold_apply_requires_exact_plan_hash(sandbox: Path) -> None:
    root = sandbox / "workspace"
    planned = scaffold(request(root))
    refused = scaffold(
        {
            **request(root),
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": "0" * 64,
        }
    )
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_PLAN_HASH"
    assert not root.exists()


def test_scaffold_activation_race_never_replaces_winner(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = sandbox / "workspace"
    planned = scaffold(request(root))
    activate = workspace_module.activate_directory_noreplace

    def race(staging: Path, target: Path) -> None:
        target.mkdir(mode=0o700)
        (target / "winner.txt").write_bytes(b"winner")
        activate(staging, target)

    monkeypatch.setattr(workspace_module, "activate_directory_noreplace", race)
    refused = scaffold(
        {
            **request(root),
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
        }
    )
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_CREATE_COLLISION"
    assert (root / "winner.txt").read_bytes() == b"winner"
    assert not (root / "rappid.json").exists()


def test_scaffold_apply_is_bound_to_requested_subject(sandbox: Path) -> None:
    root = sandbox / "workspace"
    planned = scaffold(request(root))
    refused = scaffold(
        {
            **request(root),
            "slug": "different",
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
        }
    )
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_PLAN_TARGET"
    assert not root.exists()


def test_scaffold_verify_and_read_only_operations(sandbox: Path) -> None:
    root = sandbox / "workspace"
    apply_scaffold(root)
    before = snapshot(root)
    assert Workspace.load(root).verify()["status"] == "verified"
    assert status({"root": str(root)})["status"] == "ok"
    assert verify({"root": str(root)})["status"] == "ok"
    assert snapshot(root) == before


def test_closed_operation_input_refuses_without_effects(sandbox: Path) -> None:
    root = sandbox / "workspace"
    result = scaffold({**request(root), "surprise": True})
    assert result["status"] == "refused"
    assert result["refusal"]["code"] == "REFUSE_INPUT_KEYS"
    assert not root.exists()


def test_status_on_plain_directory_is_read_only(sandbox: Path) -> None:
    before = (sandbox.stat().st_ino, sandbox.stat().st_mtime_ns, list(sandbox.iterdir()))
    result = status({"root": str(sandbox)})
    after = (sandbox.stat().st_ino, sandbox.stat().st_mtime_ns, list(sandbox.iterdir()))
    assert result["status"] == "ok"
    assert result["result"]["classification"] == "directory"
    assert after == before


def test_symlink_target_refuses(sandbox: Path) -> None:
    external = sandbox / "external"
    external.mkdir(mode=0o700)
    target = sandbox / "workspace"
    target.symlink_to(external, target_is_directory=True)
    result = scaffold(request(target))
    assert result["status"] == "refused"
    assert not (external / "rappid.json").exists()


def test_hardlinked_identity_refuses(sandbox: Path) -> None:
    root = sandbox / "workspace"
    root.mkdir(mode=0o700)
    identity = sandbox / "identity.json"
    identity.write_bytes(
        canonical_bytes(
            {
                "kind": "workspace",
                "mode": "solo",
                "name": "hardlink",
                "rappid": mint_rappid("example", "hardlink"),
                "schema": "rapp/1",
                "workspace_spec": "rapp-work-sdk/1",
                "world_id": "example-world",
            }
        )
    )
    os.link(identity, root / "rappid.json")
    result = status({"root": str(root)})
    assert result["status"] == "refused"
    assert result["refusal"]["code"] == "REFUSE_PATH_TYPE"


def test_update_is_additive_for_legacy_workspace(sandbox: Path) -> None:
    root = sandbox / "legacy"
    root.mkdir(mode=0o700)
    identity = {
        "kind": "workspace",
        "mode": "solo",
        "name": "legacy",
        "rappid": mint_rappid("example", "legacy"),
        "schema": "rapp/1",
        "workspace_spec": "rapp-workspace/2.0",
        "world_id": "example-world",
    }
    original = canonical_bytes(identity)
    (root / "rappid.json").write_bytes(original)
    planned = update({"root": str(root)})
    assert planned["status"] == "planned"
    assert not (root / ".rapp-work").exists()
    applied = update(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
            "root": str(root),
        }
    )
    assert applied["status"] == "applied"
    assert (root / "rappid.json").read_bytes() == original
    assert Workspace.load(root).verify()["profile"] == "rapp-workspace/2.0"


def test_status_and_verify_recognize_minimal_legacy_identity(sandbox: Path) -> None:
    root = sandbox / "older"
    root.mkdir(mode=0o700)
    identity = {
        "mode": "solo",
        "rappid": mint_rappid("example", "older"),
        "workspace_spec": "legacy-local/1",
    }
    (root / "rappid.json").write_bytes(canonical_bytes(identity))
    observed = status({"root": str(root)})
    checked = verify({"root": str(root)})
    assert observed["result"]["classification"] == "legacy-workspace"
    assert checked["result"]["subject"]["status"] == "verified-legacy-identity-only"


def test_update_refuses_unmanaged_collision(sandbox: Path) -> None:
    root = sandbox / "legacy"
    root.mkdir(mode=0o700)
    identity = {
        "kind": "workspace",
        "mode": "solo",
        "name": "legacy",
        "rappid": mint_rappid("example", "legacy"),
        "schema": "rapp/1",
        "workspace_spec": "rapp-workspace/2.0",
        "world_id": "example-world",
    }
    (root / "rappid.json").write_bytes(canonical_bytes(identity))
    (root / ".rapp-work").mkdir(mode=0o700)
    (root / ".rapp-work/sdk.json").write_text("owner data", encoding="utf-8")
    result = update({"root": str(root)})
    assert result["status"] == "refused"
    assert result["refusal"]["code"] == "REFUSE_MANAGED_COLLISION"
    assert (root / ".rapp-work/sdk.json").read_text() == "owner data"


def test_zero_action_update_apply_is_read_only(sandbox: Path) -> None:
    root = sandbox / "workspace"
    apply_scaffold(root)
    planned = update({"root": str(root)})
    assert planned["result"]["plan"]["actions"] == []
    before = snapshot(root)
    applied = update(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
            "root": str(root),
        }
    )
    assert applied["status"] == "ok"
    assert applied["result"]["status"] == "unchanged"
    assert snapshot(root) == before


def test_forged_update_recovery_cannot_write_unmanaged_paths(sandbox: Path) -> None:
    root = sandbox / "workspace"
    apply_scaffold(root)
    valid = Workspace.load(root).plan_update()
    forged = ReleasePlan(
        operation="update",
        target=valid.target,
        subject=valid.subject,
        actions=(FileAction("create", "unmanaged.txt", b"forged"),),
        preconditions=valid.preconditions,
    )
    marker = root / ".rapp-work/update-recovery.json"
    marker.write_bytes(
        canonical_bytes(
            {
                "plan": forged.to_dict(),
                "plan_sha256": forged.sha256,
                "schema": "rapp-work-update-recovery/1",
            }
        )
    )
    refused = update(
        {
            "apply": True,
            "plan": forged.to_dict(),
            "plan_sha256": forged.sha256,
            "root": str(root),
        }
    )
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_PLAN"
    assert not (root / "unmanaged.txt").exists()


def test_pointer_only_organization_registration(sandbox: Path) -> None:
    organization_root = sandbox / "organization"
    workspace_root = sandbox / "workspace"
    apply_scaffold(organization_root, kind="organization")
    apply_scaffold(workspace_root)
    organization = Organization.load(organization_root)
    workspace = Workspace.load(workspace_root)
    plan = organization.plan_register(workspace)
    result = organization.apply_register(workspace, plan, plan_sha256=plan.sha256)
    assert result["status"] == "registered"
    pointers = organization.pointers()
    assert len(pointers) == 1
    assert set(pointers[0]) == {"active", "mode", "name", "path", "rappid", "world_id"}
    registry_text = (organization_root / "workspaces.json").read_text()
    assert "content" not in registry_text
    assert "credential" not in registry_text


def test_organization_registration_preserves_world_boundary(sandbox: Path) -> None:
    organization_root = sandbox / "organization"
    workspace_root = sandbox / "workspace"
    apply_scaffold(organization_root, kind="organization")
    request_value = request(workspace_root)
    request_value["world_id"] = "another-world"
    planned = scaffold(request_value)
    assert (
        scaffold(
            {
                **request_value,
                "apply": True,
                "plan": planned["result"]["plan"],
                "plan_sha256": planned["result"]["plan_sha256"],
            }
        )["status"]
        == "applied"
    )
    organization = Organization.load(organization_root)
    with pytest.raises(Refusal, match="REFUSE_WORLD_BOUNDARY"):
        organization.plan_register(Workspace.load(workspace_root))
    assert organization.pointers() == ()
