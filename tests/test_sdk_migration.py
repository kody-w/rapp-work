from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import rapp_work.migration as migration_module
from rapp_work import migrate, scaffold
from rapp_work._json import canonical_bytes, canonical_sha256
from rapp_work.rapp1 import mint_rappid


def make_source(root: Path) -> None:
    request = {
        "kind": "workspace",
        "mode": "solo",
        "owner_label": "example",
        "root": str(root),
        "slug": "source",
        "world_id": "example-world",
    }
    planned = scaffold(request)
    applied = scaffold(
        {
            **request,
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
        }
    )
    assert applied["status"] == "applied"


def make_organization(root: Path) -> None:
    request = {
        "kind": "organization",
        "mode": "solo",
        "owner_label": "example",
        "root": str(root),
        "slug": "source-org",
        "world_id": "example-world",
    }
    planned = scaffold(request)
    assert (
        scaffold(
            {
                **request,
                "apply": True,
                "plan": planned["result"]["plan"],
                "plan_sha256": planned["result"]["plan_sha256"],
            }
        )["status"]
        == "applied"
    )


def stats(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.stat().st_ino,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file()
    }


def plan(source: Path, target: Path) -> dict:
    result = migrate({"source": str(source), "target": str(target)})
    assert result["status"] == "planned"
    return result


def apply(source: Path, target: Path, planned: dict) -> dict:
    return migrate(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
            "source": str(source),
            "target": str(target),
        }
    )


def test_migration_dry_run_and_wrong_hash_have_no_effects(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    assert not target.exists()
    refused = migrate(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": "0" * 64,
            "source": str(source),
            "target": str(target),
        }
    )
    assert refused["status"] == "refused"
    assert not target.exists()


def test_source_change_refuses_before_target_write(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    (source / "rappid.json").write_bytes((source / "rappid.json").read_bytes() + b"\n")
    refused = apply(source, target, planned)
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_MIGRATION_SOURCE_CHANGED"
    assert not target.exists()


def test_migration_activation_race_never_replaces_winner(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    activate = migration_module.activate_directory_noreplace

    def race(staging: Path, destination: Path) -> None:
        destination.mkdir(mode=0o700)
        (destination / "winner.txt").write_bytes(b"winner")
        activate(staging, destination)

    monkeypatch.setattr(migration_module, "activate_directory_noreplace", race)
    refused = apply(source, target, planned)
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_CREATE_COLLISION"
    assert (target / "winner.txt").read_bytes() == b"winner"
    assert not (target / ".rapp-work/migration-receipt.json").exists()


def test_completed_replay_is_full_and_read_only(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    first = apply(source, target, planned)
    assert first["status"] == "applied"
    before_source, before_target = stats(source), stats(target)
    replay = apply(source, target, planned)
    assert replay["status"] == "ok"
    assert replay["result"]["status"] == "unchanged"
    replanned = plan(source, target)
    assert replanned["result"]["plan_sha256"] == planned["result"]["plan_sha256"]
    assert stats(source) == before_source
    assert stats(target) == before_target


def test_completed_receipt_or_inventory_tamper_refuses_without_repair(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    assert apply(source, target, planned)["status"] == "applied"
    path = target / ".rapp-work/sdk.json"
    path.write_bytes(path.read_bytes() + b"\n")
    before = stats(target)
    replay = apply(source, target, planned)
    assert replay["status"] == "refused"
    assert replay["refusal"]["code"] == "REFUSE_MIGRATION_REPLAY"
    assert stats(target) == before


def test_source_bound_recovery_resumes_only_exact_plan(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    plan_value = planned["result"]["plan"]
    plan_hash = planned["result"]["plan_sha256"]
    staging = target.parent / f".{target.name}.rapp-work-migrate-{plan_hash[:24]}"
    (staging / ".rapp-work").mkdir(parents=True, mode=0o700)
    staging.chmod(0o700)
    binding_hash = canonical_sha256(plan_value["source_binding"])
    marker = {
        "plan_sha256": plan_hash,
        "schema": "rapp-work-migration-recovery/1",
        "source": str(source),
        "source_binding_sha256": binding_hash,
        "target": str(target),
    }
    (staging / ".rapp-work/migration-recovery.json").write_bytes(canonical_bytes(marker))
    first_action = plan_value["actions"][0]
    first_path = staging / first_action["path"]
    first_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    import base64

    first_path.write_bytes(base64.b64decode(first_action["content_base64"]))
    result = apply(source, target, planned)
    assert result["status"] == "applied"
    assert target.is_dir()
    assert not staging.exists()


def test_foreign_recovery_marker_refuses_without_deletion(sandbox: Path) -> None:
    source, target = sandbox / "source", sandbox / "target"
    make_source(source)
    planned = plan(source, target)
    plan_hash = planned["result"]["plan_sha256"]
    staging = target.parent / f".{target.name}.rapp-work-migrate-{plan_hash[:24]}"
    (staging / ".rapp-work").mkdir(parents=True, mode=0o700)
    staging.chmod(0o700)
    marker = {
        "plan_sha256": "0" * 64,
        "schema": "rapp-work-migration-recovery/1",
        "source": str(source),
        "source_binding_sha256": "0" * 64,
        "target": str(target),
    }
    marker_path = staging / ".rapp-work/migration-recovery.json"
    marker_path.write_bytes(canonical_bytes(marker))
    refused = apply(source, target, planned)
    assert refused["status"] == "refused"
    assert staging.exists()
    assert marker_path.read_bytes() == canonical_bytes(marker)


def test_pointer_only_organization_migrates_as_organization(sandbox: Path) -> None:
    source, target = sandbox / "organization", sandbox / "successor"
    make_organization(source)
    planned = plan(source, target)
    result = apply(source, target, planned)
    assert result["status"] == "applied"
    assert (target / "organization.json").is_file()
    assert (target / "workspaces.json").is_file()


def test_minimal_legacy_workspace_uses_hive_world_binding(sandbox: Path) -> None:
    source, target = sandbox / "legacy", sandbox / "successor"
    source.mkdir(mode=0o700)
    (source / "rappid.json").write_bytes(
        canonical_bytes(
            {
                "mode": "solo",
                "rappid": mint_rappid("example", "legacy"),
                "workspace_spec": "legacy-local/1",
            }
        )
    )
    (source / ".rapp-hive").mkdir(mode=0o700)
    (source / ".rapp-hive/declaration.json").write_bytes(
        canonical_bytes({"world_id": "legacy-world"})
    )
    planned = plan(source, target)
    assert apply(source, target, planned)["status"] == "applied"
    assert b"legacy-world" in (target / "rappid.json").read_bytes()
