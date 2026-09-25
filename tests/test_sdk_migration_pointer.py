"""Pointer-only successors (proposal 0004, gap G4): repository-seeded Hives and long world ids."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import warnings
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import rapp_work.migration as migration_module
from rapp_work import Organization, Workspace, migrate, scaffold, status, update, verify
from rapp_work._json import canonical_bytes, canonical_sha256
from rapp_work.compat import private_hive, private_hive_prepare
from rapp_work.discovery import api_metadata
from rapp_work.errors import Refusal
from rapp_work.rapp1 import build_frame, canonical, mint_rappid

ROOT = Path(__file__).resolve().parents[1]
POINTER_PATH = ".rapp-work/pointer-successor.json"
PROPOSAL = ROOT / "docs/proposals/0004-sdk-migration-successors.md"
WORLD80 = "example-" + "w" * 72
SUCCESSOR_FILES = [
    ".rapp-work",
    ".rapp-work/migration-receipt.json",
    ".rapp-work/migration-recovery.json",
    ".rapp-work/pointer-successor.json",
]
PRIVATE_SENTINEL = b"SYNTHETIC GODD SENTINEL: never copy this into a successor.\n"
POLICY = b"# Admission\n\nNew members need approval from two peers (was: the owner).\n"


def git_seed(root: Path) -> None:
    """Make ``root`` a Git working tree whose index holds every file (no identity needed)."""

    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root.parent),
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
    }
    for arguments in (
        ["git", "-c", "init.defaultBranch=main", "init", "--quiet", "--template=", str(root)],
        ["git", "-C", str(root), "add", "--all"],
    ):
        subprocess.run(arguments, check=True, capture_output=True, env=environment)


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def member_card(key: Ed25519PrivateKey, owner: str) -> dict[str, str]:
    der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return {
        "owner_rappid": mint_rappid(owner, "hive-member", der),
        "schema": "rapp-work-anchor/1",
        "spki_der_b64": base64.b64encode(der).decode("ascii"),
        "spki_sha256": hashlib.sha256(der).hexdigest(),
    }


def signed_join_request(key: Ed25519PrivateKey, card: dict[str, str], hive: str) -> dict[str, Any]:
    payload = {
        "hive": hive,
        "note": "Synthetic newcomer asks to join.",
        "operation": "join-request",
        "spki_der_b64": card["spki_der_b64"],
    }
    frame = build_frame(
        kind="onboarding.join",
        stream_id=card["owner_rappid"],
        seq=0,
        utc="2026-08-02T10:00:00.000Z",
        payload=payload,
        prev=None,
    ).to_dict()
    header = b64url(
        canonical(
            {"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": card["owner_rappid"]}
        ).encode()
    )
    unsigned = {name: value for name, value in frame.items() if name != "sig"}
    signature = key.sign(header.encode("ascii") + b"." + canonical(unsigned).encode())
    frame["sig"] = header + ".." + b64url(signature)
    return frame


def seeded_hive(root: Path, *, world: str = WORLD80) -> dict[str, Any]:
    """Synthetic repository-seeded Hive: owner card, policy, join requests, content, Git."""

    root.mkdir(mode=0o700)
    hive = mint_rappid("example-owner", "example-seeded-hive")
    owner = member_card(Ed25519PrivateKey.generate(), "example-owner")
    (root / "owner-anchor.json").write_text(json.dumps(owner, indent=2) + "\n", encoding="utf-8")
    (root / "POLICY.md").write_bytes(POLICY)
    (root / "seed.json").write_bytes(
        canonical_bytes(
            {
                "hive": hive,
                "owner": owner["owner_rappid"],
                "schema": "example-hive-seed/1",
                "world_id": world,
            }
        )
    )
    (root / "requests").mkdir(mode=0o700)
    for handle in ("example-member-a", "example-member-b"):
        key = Ed25519PrivateKey.generate()
        request = signed_join_request(key, member_card(key, handle), hive)
        (root / "requests" / f"{handle}.json").write_text(
            json.dumps(request, indent=2) + "\n",
            encoding="utf-8",
        )
    (root / "shared").mkdir(mode=0o700)
    (root / "shared" / "notes.md").write_bytes(b"# Shared notes\n\nSynthetic team content.\n")
    (root / "private").mkdir(mode=0o700)
    (root / "private" / "secret.txt").write_bytes(PRIVATE_SENTINEL)
    git_seed(root)
    return {
        "authority_channel": {
            "id": "origin",
            "kind": "github",
            "locator": "https://github.com/example-owner/example-seeded-hive",
        },
        "authority_paths": [
            "POLICY.md",
            "requests/example-member-a.json",
            "requests/example-member-b.json",
            "seed.json",
        ],
        "hive_rappid": hive,
        "world_id": world,
    }


def identity_workspace(root: Path, world: str) -> Path:
    root.mkdir(mode=0o700)
    (root / "rappid.json").write_bytes(
        canonical_bytes(
            {
                "kind": "workspace",
                "mode": "solo",
                "name": root.name,
                "rappid": mint_rappid("example", "legacy-world"),
                "schema": "rapp/1",
                "workspace_spec": "rapp-workspace/1",
                "world_id": world,
            }
        )
    )
    (root / "notes.md").write_bytes(b"# Legacy notes\n")
    return root


def plan(source: Path, target: Path, hive: dict[str, Any] | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "source": str(source),
        "successor": "pointer-only",
        "target": str(target),
    }
    if hive is not None:
        request["hive"] = hive
    return migrate(request)


def apply(source: Path, target: Path, planned: dict[str, Any], **extra: Any) -> dict[str, Any]:
    request = {
        "apply": True,
        "plan": planned["result"]["plan"],
        "plan_sha256": planned["result"]["plan_sha256"],
        "source": str(source),
        "successor": "pointer-only",
        "target": str(target),
        **extra,
    }
    return migrate(request)


def planned_ok(source: Path, target: Path, hive: dict[str, Any] | None = None) -> dict[str, Any]:
    result = plan(source, target, hive)
    assert result["status"] == "planned", result["refusal"]
    return result


def snapshot(root: Path) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        relative = path.relative_to(root).as_posix()
        if stat.S_ISDIR(info.st_mode):
            entries[relative] = ("dir", info.st_ino, stat.S_IMODE(info.st_mode))
        else:
            entries[relative] = (
                "file",
                info.st_ino,
                info.st_mtime_ns,
                stat.S_IMODE(info.st_mode),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
    return entries


def listing(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def pointer(target: Path) -> dict[str, Any]:
    value = json.loads((target / POINTER_PATH).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def refused(result: dict[str, Any], code: str) -> None:
    assert result["status"] == "refused", result
    assert result["refusal"]["code"] == code, result["refusal"]


def test_seeded_hive_default_migration_refusal_is_unchanged(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    before = snapshot(source)
    default = migrate({"source": str(source), "target": str(target)})
    refused(default, "REFUSE_PATH_UNSAFE")
    assert default["refusal"]["details"] == {"path": str(source)}
    assert hive["world_id"] == WORLD80
    long_world = identity_workspace(sandbox / "long-world", "w" * 80)
    text_world = identity_workspace(sandbox / "text-world", "Example World")
    hyphens = identity_workspace(sandbox / "double-hyphen", "example--world")
    declared = sandbox / "declared-world"
    declared.mkdir(mode=0o700)
    (declared / "rappid.json").write_bytes(
        canonical_bytes(
            {"rappid": mint_rappid("example", "declared"), "workspace_spec": "legacy/1"}
        )
    )
    (declared / ".rapp-hive").mkdir(mode=0o700)
    (declared / ".rapp-hive/declaration.json").write_bytes(canonical_bytes({"world_id": "w" * 80}))
    for legacy in (long_world, text_world, hyphens, declared):
        refused(
            migrate({"source": str(legacy), "target": str(sandbox / "other")}),
            "REFUSE_MIGRATION_SOURCE",
        )
    assert not target.exists()
    assert snapshot(source) == before


def test_seeded_hive_pointer_only_successor_plans_and_applies_exactly(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    result = planned["result"]
    assert result["effects"] is False
    assert not target.exists()
    value = result["plan"]
    assert value["schema"] == "rapp-work-pointer-successor-plan/1"
    assert value["successor"] == "pointer-only"
    assert value["network"] is False
    assert [action["path"] for action in value["actions"]] == [POINTER_PATH]
    assert result["plan_sha256"] == canonical_sha256(value)
    binding = value["source_binding"]
    bound = ["owner-anchor.json", *hive["authority_paths"]]
    assert [entry["path"] for entry in binding["authority_files"]] == sorted(bound)
    for entry in binding["authority_files"]:
        raw = (source / entry["path"]).read_bytes()
        assert entry == {
            "bytes": len(raw),
            "path": entry["path"],
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    assert binding["kind"] == "hive"
    assert binding["identity_source"] == "operator-description"
    assert binding["described_paths"] == hive["authority_paths"]
    assert binding["world_id"] == WORLD80 and len(WORLD80) == 80

    applied = apply(source, target, planned)
    assert applied["status"] == "applied", applied["refusal"]
    assert applied["result"]["status"] == "migrated"
    assert applied["result"]["plan_sha256"] == result["plan_sha256"]
    assert listing(target) == SUCCESSOR_FILES
    record = pointer(target)
    assert record == {
        "authority_channel": hive["authority_channel"],
        "authority_files": binding["authority_files"],
        "content_copied": False,
        "execution": "never",
        "grants_authority": False,
        "identity_source": "operator-description",
        "schema": "rapp-work-pointer-successor/1",
        "source": str(source),
        "source_binding_sha256": canonical_sha256(binding),
        "source_kind": "hive",
        "source_profile": None,
        "source_rappid": hive["hive_rappid"],
        "source_world_id": WORLD80,
    }
    assert migration_module.validate_pointer_record(record) == record
    assert (target / POINTER_PATH).read_bytes() == canonical_bytes(record)
    receipt = json.loads((target / ".rapp-work/migration-receipt.json").read_text(encoding="utf-8"))
    assert receipt["schema"] == "rapp-work-migration-receipt/1"
    assert receipt["plan_sha256"] == result["plan_sha256"]
    assert [entry["path"] for entry in receipt["target_files"]] == [
        ".rapp-work/migration-recovery.json",
        POINTER_PATH,
    ]
    if os.name == "posix":
        for path in target.rglob("*"):
            expected = 0o700 if path.is_dir() else 0o600
            assert stat.S_IMODE(path.stat().st_mode) == expected, path


def test_pointer_successor_copies_no_hive_state(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    assert apply(source, target, planned)["status"] == "applied"
    assert listing(target) == SUCCESSOR_FILES
    written = b"\n".join(path.read_bytes() for path in target.rglob("*") if path.is_file())
    plan_bytes = canonical_bytes(planned["result"]["plan"])
    owner = json.loads((source / "owner-anchor.json").read_text(encoding="utf-8"))
    forbidden = [
        PRIVATE_SENTINEL,
        POLICY,
        b"Synthetic team content",
        b"Synthetic newcomer",
        owner["spki_der_b64"].encode(),
        b"private/secret.txt",
        b"shared/notes.md",
    ]
    for name in ("example-member-a", "example-member-b"):
        request = json.loads((source / "requests" / f"{name}.json").read_text(encoding="utf-8"))
        forbidden += [request["sig"].encode(), request["payload"]["spki_der_b64"].encode()]
    for git_file in (source / ".git").rglob("*"):
        if git_file.is_file() and git_file.stat().st_size >= 16:
            forbidden.append(git_file.read_bytes())
    for value in forbidden:
        assert value not in written
        assert value not in plan_bytes


def test_pointer_successor_preserves_source_byte_for_byte(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    before = snapshot(source)
    assert (source / ".git").is_dir() and any(key.startswith(".git/") for key in before)
    planned = planned_ok(source, target, hive)
    assert snapshot(source) == before
    assert apply(source, target, planned)["status"] == "applied"
    assert snapshot(source) == before
    assert apply(source, target, planned)["status"] == "ok"
    assert snapshot(source) == before


def test_pointer_completed_replay_is_full_and_read_only(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    assert apply(source, target, planned)["status"] == "applied"
    before_source, before_target = snapshot(source), snapshot(target)
    replay = apply(source, target, planned)
    assert replay["status"] == "ok"
    assert replay["result"]["status"] == "unchanged"
    assert replay["result"]["effects"] is False
    assert (
        planned_ok(source, target, hive)["result"]["plan_sha256"]
        == planned["result"]["plan_sha256"]
    )
    assert snapshot(source) == before_source
    assert snapshot(target) == before_target

    record_path = target / POINTER_PATH
    original = record_path.read_bytes()
    record_path.write_bytes(original.replace(b'"execution":"never"', b'"execution":"always"'))
    tampered = snapshot(target)
    refused(apply(source, target, planned), "REFUSE_MIGRATION_REPLAY")
    assert snapshot(target) == tampered
    record_path.write_bytes(original)
    receipt_path = target / ".rapp-work/migration-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["plan_sha256"] = "1" * 64
    receipt_path.write_bytes(canonical_bytes(receipt))
    refused(apply(source, target, planned), "REFUSE_MIGRATION_REPLAY")


def test_pointer_changed_source_refuses_before_any_write(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    staging_prefix = f".{target.name}.rapp-work-migrate-"

    policy = source / "POLICY.md"
    policy.write_bytes(POLICY + b"Changed after review.\n")
    refused(apply(source, target, planned), "REFUSE_MIGRATION_SOURCE_CHANGED")
    policy.write_bytes(POLICY)

    registry = source / "registry.json"
    registry.write_bytes(b"{}")
    refused(apply(source, target, planned), "REFUSE_MIGRATION_SOURCE_CHANGED")
    registry.unlink()

    request = source / "requests" / "example-member-b.json"
    saved = request.read_bytes()
    request.unlink()
    refused(apply(source, target, planned), "REFUSE_POINTER_AUTHORITY")
    request.write_bytes(saved)
    assert not target.exists()
    assert not any(path.name.startswith(staging_prefix) for path in sandbox.iterdir())

    assert apply(source, target, planned)["status"] == "applied"
    completed = snapshot(target)
    (source / "seed.json").write_bytes(b"{}")
    refused(apply(source, target, planned), "REFUSE_MIGRATION_SOURCE_CHANGED")
    assert snapshot(target) == completed


def test_pointer_plan_hash_and_tamper_gates(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    wrong = migrate(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": "0" * 64,
            "source": str(source),
            "successor": "pointer-only",
            "target": str(target),
        }
    )
    refused(wrong, "REFUSE_PLAN_HASH")

    def forged(change: Any) -> dict[str, Any]:
        value = json.loads(json.dumps(planned["result"]["plan"]))
        change(value)
        return {"result": {"plan": value, "plan_sha256": canonical_sha256(value)}}

    def swap_pointer(value: dict[str, Any]) -> None:
        record = json.loads(base64.b64decode(value["actions"][0]["content_base64"]))
        record["content_copied"] = True
        raw = canonical_bytes(record)
        value["actions"][0].update(
            bytes=len(raw),
            content_base64=base64.b64encode(raw).decode("ascii"),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def forge_commitment(value: dict[str, Any]) -> None:
        value["source_binding"]["authority_files"][0]["sha256"] = "1" * 64
        record = json.loads(base64.b64decode(value["actions"][0]["content_base64"]))
        record["authority_files"] = value["source_binding"]["authority_files"]
        record["source_binding_sha256"] = canonical_sha256(value["source_binding"])
        raw = canonical_bytes(record)
        value["actions"][0].update(
            bytes=len(raw),
            content_base64=base64.b64encode(raw).decode("ascii"),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def extra_action(value: dict[str, Any]) -> None:
        raw = (source / "POLICY.md").read_bytes()
        value["actions"].append(
            {
                "bytes": len(raw),
                "content_base64": base64.b64encode(raw).decode("ascii"),
                "expected_sha256": None,
                "mode": 384,
                "operation": "create",
                "path": "POLICY.md",
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    refused(apply(source, target, forged(swap_pointer)), "REFUSE_MIGRATION_PLAN")
    refused(apply(source, target, forged(forge_commitment)), "REFUSE_MIGRATION_SOURCE_CHANGED")
    refused(apply(source, target, forged(extra_action)), "REFUSE_MIGRATION_PLAN")
    refused(
        apply(source, target, forged(lambda value: value.update(successor="copy"))),
        "REFUSE_MIGRATION_PLAN",
    )
    refused(
        apply(source, target, forged(lambda value: value.update(network=True))),
        "REFUSE_MIGRATION_PLAN",
    )
    assert not target.exists()


def test_pointer_recovery_marker_binding(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    plan_value = planned["result"]["plan"]
    plan_hash = planned["result"]["plan_sha256"]
    staging = target.parent / f".{target.name}.rapp-work-migrate-{plan_hash[:24]}"
    (staging / ".rapp-work").mkdir(parents=True, mode=0o700)
    staging.chmod(0o700)
    marker_path = staging / ".rapp-work/migration-recovery.json"
    foreign = {
        "plan_sha256": "0" * 64,
        "schema": "rapp-work-migration-recovery/1",
        "source": str(source),
        "source_binding_sha256": "0" * 64,
        "target": str(target),
    }
    marker_path.write_bytes(canonical_bytes(foreign))
    refused(apply(source, target, planned), "REFUSE_RECOVERY_BINDING")
    assert staging.exists()
    assert marker_path.read_bytes() == canonical_bytes(foreign)
    assert not target.exists()

    exact = {
        "plan_sha256": plan_hash,
        "schema": "rapp-work-migration-recovery/1",
        "source": str(source),
        "source_binding_sha256": canonical_sha256(plan_value["source_binding"]),
        "target": str(target),
    }
    marker_path.write_bytes(canonical_bytes(exact))
    (staging / POINTER_PATH).write_bytes(
        base64.b64decode(plan_value["actions"][0]["content_base64"])
    )
    resumed = apply(source, target, planned)
    assert resumed["status"] == "applied", resumed["refusal"]
    assert not staging.exists()
    assert listing(target) == SUCCESSOR_FILES


def test_pointer_activation_race_never_replaces_winner(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    activate = migration_module.activate_directory_noreplace

    def race(staging: Path, destination: Path) -> None:
        destination.mkdir(mode=0o700)
        (destination / "winner.txt").write_bytes(b"winner")
        activate(staging, destination)

    monkeypatch.setattr(migration_module, "activate_directory_noreplace", race)
    refused(apply(source, target, planned), "REFUSE_CREATE_COLLISION")
    assert listing(target) == ["winner.txt"]


def test_organization_source_pointer_successor(sandbox: Path) -> None:
    organization = sandbox / "organization"
    request = {
        "kind": "organization",
        "mode": "solo",
        "owner_label": "example",
        "root": str(organization),
        "slug": "example-org",
        "world_id": "example-world",
    }
    planned_org = scaffold(request)
    applied_org = scaffold(
        {
            **request,
            "apply": True,
            "plan": planned_org["result"]["plan"],
            "plan_sha256": planned_org["result"]["plan_sha256"],
        }
    )
    assert applied_org["status"] == "applied"
    target = sandbox / "successor"
    planned = planned_ok(organization, target)
    binding = planned["result"]["plan"]["source_binding"]
    assert binding["kind"] == "organization"
    assert [entry["path"] for entry in binding["authority_files"]] == [
        ".rapp-work/managed.json",
        ".rapp-work/sdk.json",
        "organization.json",
        "rappid.json",
        "workspaces.json",
    ]
    assert apply(organization, target, planned)["status"] == "applied"
    record = pointer(target)
    assert record["source_kind"] == "organization"
    assert record["source_profile"] == "rapp-work-sdk/1"
    assert record["source_world_id"] == "example-world"
    assert listing(target) == SUCCESSOR_FILES


def test_pointer_opt_in_and_input_contract(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    without_opt_in = migrate(
        {
            "apply": True,
            "plan": planned["result"]["plan"],
            "plan_sha256": planned["result"]["plan_sha256"],
            "source": str(source),
            "target": str(target),
        }
    )
    refused(without_opt_in, "REFUSE_INPUT_KEYS")
    refused(apply(source, target, planned, hive=hive), "REFUSE_APPLY_REQUIRED")
    refused(
        migrate({"hive": hive, "source": str(source), "target": str(target)}),
        "REFUSE_INPUT_SHAPE",
    )
    refused(
        migrate({"source": str(source), "successor": "copy", "target": str(target), "hive": hive}),
        "REFUSE_INPUT_SHAPE",
    )
    refused(plan(source, target), "REFUSE_POINTER_SOURCE")

    workspace = identity_workspace(sandbox / "workspace", "example-world")
    default = migrate({"source": str(workspace), "target": str(sandbox / "default-successor")})
    assert default["status"] == "planned"
    refused(apply(workspace, sandbox / "default-successor", default), "REFUSE_INPUT_KEYS")
    refused(plan(workspace, sandbox / "w-successor", hive), "REFUSE_POINTER_SOURCE")

    for change, code in (
        ({"unexpected": True}, "REFUSE_INPUT_KEYS"),
        (
            {"hive_rappid": "rappid:@example-owner/example-seeded-hive:" + "Z" * 64},
            "REFUSE_POINTER_SOURCE",
        ),
        ({"hive_rappid": "example-seeded-hive"}, "REFUSE_POINTER_SOURCE"),
        ({"authority_paths": []}, "REFUSE_POINTER_AUTHORITY"),
        ({"authority_paths": ["seed.json", "POLICY.md"]}, "REFUSE_POINTER_AUTHORITY"),
        ({"authority_paths": ["POLICY.md", "POLICY.md"]}, "REFUSE_POINTER_AUTHORITY"),
        ({"authority_paths": ["missing.json"]}, "REFUSE_POINTER_AUTHORITY"),
        (
            {"authority_channel": {"id": "origin", "kind": "ftp", "locator": "x"}},
            "REFUSE_POINTER_CHANNEL",
        ),
        ({"world_id": "w" * 129}, "REFUSE_POINTER_WORLD"),
    ):
        refused(plan(source, sandbox / "bad", {**hive, **change}), code)
    assert not (sandbox / "bad").exists()
    assert not target.exists()


@pytest.mark.parametrize(
    "value",
    [
        "a",
        "w" * 64,
        "w" * 65,
        "w" * 128,
        "example--world",
        "Example World 2026",
        "example.org/team-a",
        "\u00e9" * 128,
        "\u4e16\u754c" * 64,
    ],
)
def test_pointer_world_grammar_accepts(value: str) -> None:
    assert migration_module.pointer_world_id(value, "world") == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "w" * 129,
        "\u00e9" * 129,
        "e\u0301",
        "a\x1fb",
        "a\nb",
        "a\x7fb",
        "a\x85b",
        "a\u202eb",
        "a\u2066b",
        "a\ud800b",
        5,
        None,
    ],
)
def test_pointer_world_grammar_refuses(value: Any) -> None:
    with pytest.raises(Refusal) as error:
        migration_module.pointer_world_id(value, "world")
    assert error.value.code == "REFUSE_POINTER_WORLD"


@pytest.mark.parametrize("length", [1, 64, 65, 128, 129])
def test_pointer_world_boundaries_end_to_end(sandbox: Path, length: int) -> None:
    world = "w" * length
    source = sandbox / "seeded"
    hive = seeded_hive(source, world=world)
    workspace = identity_workspace(sandbox / "workspace", world)
    described = plan(source, sandbox / "hive-successor", {**hive, "world_id": world})
    identified = plan(workspace, sandbox / "workspace-successor")
    default = migrate({"source": str(workspace), "target": str(sandbox / "default-successor")})
    if length <= 128:
        for result in (described, identified):
            assert result["status"] == "planned", result["refusal"]
            assert result["result"]["plan"]["source_binding"]["world_id"] == world
        applied = apply(workspace, sandbox / "workspace-successor", identified)
        assert applied["status"] == "applied"
        record = pointer(sandbox / "workspace-successor")
        assert record["source_world_id"] == world
        assert record["source_kind"] == "workspace"
        assert record["identity_source"] == "source-identity-file"
        assert record["authority_channel"] is None
        assert record["source_profile"] == "rapp-workspace/1"
        assert (
            record["source_rappid"] == json.loads((workspace / "rappid.json").read_text())["rappid"]
        )
    else:
        refused(described, "REFUSE_POINTER_WORLD")
        refused(identified, "REFUSE_POINTER_WORLD")
    if length <= 64:
        assert default["status"] == "planned"
    else:
        refused(default, "REFUSE_MIGRATION_SOURCE")


def test_long_world_is_refused_everywhere_else(sandbox: Path) -> None:
    request = {
        "kind": "workspace",
        "mode": "solo",
        "owner_label": "example",
        "root": str(sandbox / "scaffolded"),
        "slug": "scaffolded",
        "world_id": "w" * 65,
    }
    refused(scaffold(request), "REFUSE_LABEL")
    assert scaffold({**request, "world_id": "w" * 64})["status"] == "planned"

    long_label = identity_workspace(sandbox / "long-label", "w" * 65)
    before = snapshot(long_label)
    refused(update({"root": str(long_label)}), "REFUSE_IDENTITY")
    observed = status({"root": str(long_label)})
    assert observed["result"]["classification"] == "legacy-workspace"
    checked = verify({"root": str(long_label)})
    assert checked["result"]["subject"]["status"] == "verified-legacy-identity-only"
    assert snapshot(long_label) == before
    with pytest.raises(Refusal) as error:
        Workspace.load(long_label)
    assert error.value.code == "REFUSE_IDENTITY"

    organization = sandbox / "organization"
    org_request = {**request, "kind": "organization", "root": str(organization), "slug": "org"}
    org_request["world_id"] = "w" * 64
    planned_org = scaffold(org_request)
    assert (
        scaffold(
            {
                **org_request,
                "apply": True,
                "plan": planned_org["result"]["plan"],
                "plan_sha256": planned_org["result"]["plan_sha256"],
            }
        )["status"]
        == "applied"
    )
    registry = organization / "workspaces.json"
    value = json.loads(registry.read_text(encoding="utf-8"))
    value["workspaces"] = [
        {
            "active": True,
            "mode": "solo",
            "name": "long",
            "path": str(long_label),
            "rappid": mint_rappid("example", "long"),
            "world_id": "w" * 65,
        }
    ]
    registry.write_bytes(canonical_bytes(value))
    with pytest.raises(Refusal) as error:
        Organization.load(organization).pointers()
    assert error.value.code == "REFUSE_ORGANIZATION"

    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    planned = planned_ok(source, target, hive)
    assert apply(source, target, planned)["status"] == "applied"
    assert status({"root": str(target)})["result"]["classification"] == "directory"
    refused(verify({"root": str(target)}), "REFUSE_VERIFY_TARGET")
    refused(update({"root": str(target)}), "REFUSE_PATH_UNSAFE")
    with pytest.raises(Refusal):
        Workspace.load(target)

    sdk_schema = json.loads((ROOT / "protocols/rapp-work-sdk/1/schema.json").read_text())
    assert sdk_schema["properties"]["world_id"]["maxLength"] == 64
    hive_schema = json.loads((ROOT / "protocols/rapp-hive/1/schema.json").read_text())
    assert hive_schema["$defs"]["label"]["maxLength"] == 64
    canonical_schema = json.loads((ROOT / "src/rapp_work/data/rapp-work-1-schema.json").read_text())
    assert canonical_schema["$defs"]["label"]["maxLength"] == 64


@pytest.mark.parametrize(
    ("kind", "locator"),
    [
        ("github", "https://github.com/example-owner/example-hive"),
        ("sharepoint", "https://example.com/sites/example/hive"),
        ("nas", "https://example.com:8443/share/example-hive"),
        ("local", ".rapp-hive/outbox"),
        ("local", "private-filesystem:example-store"),
        ("custom", "example-carrier:hive/main"),
    ],
)
def test_authority_channel_accepts_credential_free_locators(kind: str, locator: str) -> None:
    value = {"id": "origin", "kind": kind, "locator": locator}
    assert migration_module.authority_channel(value) == value


@pytest.mark.parametrize(
    ("kind", "locator"),
    [
        ("github", "https://user:secret@github.com/example-owner/example-hive"),
        ("github", "https://github.com/example-owner/example-hive.git"),
        ("github", "https://example.com/example-owner/example-hive"),
        ("github", "https://github.com/example-owner/.."),
        ("sharepoint", "https://example.com/hive?access_token=synthetic"),
        ("sharepoint", "https://example.com/hive#fragment"),
        ("nas", "http://example.com/share"),
        ("nas", "ftp://example.com/share"),
        ("nas", "file:///share/hive"),
        ("lan", "git@example.com:owner/hive"),
        ("local", "/absolute/path/hive"),
        ("local", "../outside"),
        ("local", "with space"),
        ("local", "tab\there"),
        ("custom", "caf\u00e9"),
        ("custom", ""),
        ("custom", "a" * 2049),
    ],
)
def test_authority_channel_refuses_credentials_and_unsafe_locators(kind: str, locator: str) -> None:
    with pytest.raises(Refusal) as error:
        migration_module.authority_channel({"id": "origin", "kind": kind, "locator": locator})
    assert error.value.code == "REFUSE_POINTER_CHANNEL"
    if any(character in locator for character in "@?#"):
        assert "user information, queries, or fragments" in error.value.message


@pytest.mark.parametrize("channel_id", ["", "Origin", "-origin", "o" * 65, "or igin"])
def test_authority_channel_id_is_a_hive_label(channel_id: str) -> None:
    with pytest.raises(Refusal) as error:
        migration_module.authority_channel({"id": channel_id, "kind": "local", "locator": "outbox"})
    assert error.value.code == "REFUSE_POINTER_CHANNEL"


def test_authority_path_rules(sandbox: Path) -> None:
    source = sandbox / "seeded"
    hive = seeded_hive(source)
    for path, code in (
        (".git/config", "REFUSE_POINTER_AUTHORITY"),
        (".GIT/HEAD", "REFUSE_POINTER_AUTHORITY"),
        ("vendor/.git/HEAD", "REFUSE_POINTER_AUTHORITY"),
        ("../outside.json", "REFUSE_PATH"),
        ("/etc/hosts", "REFUSE_PATH"),
        ("a:b.json", "REFUSE_PATH"),
    ):
        refused(plan(source, sandbox / "bad", {**hive, "authority_paths": [path]}), code)

    outside = sandbox / "outside.json"
    outside.write_bytes(b"{}")
    (source / "linked.json").symlink_to(outside)
    refused(
        plan(source, sandbox / "bad", {**hive, "authority_paths": ["linked.json"]}),
        "REFUSE_PATH_UNSAFE",
    )
    os.link(source / "seed.json", sandbox / "seed-hardlink.json")
    refused(plan(source, sandbox / "bad", hive), "REFUSE_PATH_TYPE")
    (sandbox / "seed-hardlink.json").unlink()
    (source / "linked-dir").symlink_to(source / "requests", target_is_directory=True)
    refused(
        plan(
            source,
            sandbox / "bad",
            {**hive, "authority_paths": ["linked-dir/example-member-a.json"]},
        ),
        "REFUSE_PATH_UNSAFE",
    )
    assert not (sandbox / "bad").exists()


def test_description_is_corroborated_by_recognized_hive_records(sandbox: Path) -> None:
    source = sandbox / "seeded"
    hive = seeded_hive(source, world="example-world")
    declaration = {
        "authority_channel_id": "origin",
        "channels": [
            {
                "id": "origin",
                "kind": "github",
                "locator": hive["authority_channel"]["locator"],
                "role": "authority",
                "writeback": True,
            }
        ],
        "created_utc": "2026-08-01T09:00:00.000Z",
        "hive_rappid": hive["hive_rappid"],
        "members": [],
        "policy": {},
        "rooms": [],
        "schema": "rapp-hive/1-declaration",
        "world_id": "example-world",
    }
    (source / ".rapp-hive").mkdir(mode=0o700)
    declaration_path = source / ".rapp-hive/declaration.json"
    declaration_path.write_bytes(canonical_bytes(declaration))
    matched = planned_ok(source, sandbox / "successor", hive)
    paths = [
        entry["path"] for entry in matched["result"]["plan"]["source_binding"]["authority_files"]
    ]
    assert ".rapp-hive/declaration.json" in paths
    for change in (
        {"hive_rappid": mint_rappid("example-owner", "another-hive")},
        {"world_id": "another-world"},
        {
            "authority_channel": {
                **hive["authority_channel"],
                "locator": "https://github.com/example-owner/other",
            }
        },
    ):
        refused(plan(source, sandbox / "bad", {**hive, **change}), "REFUSE_POINTER_CLAIM")
    declaration_path.unlink()

    anchor = {
        "hive_rappid": hive["hive_rappid"],
        "schema": "rapp-private-hive-owner-anchor/1",
        "world_id": "example-world",
    }
    (source / ".rapp-hive/owner-anchor.json").write_bytes(canonical_bytes(anchor))
    assert plan(source, sandbox / "successor", hive)["status"] == "planned"
    refused(
        plan(source, sandbox / "bad", {**hive, "world_id": "another-world"}), "REFUSE_POINTER_CLAIM"
    )
    assert not (sandbox / "bad").exists()


def test_pointer_record_token_is_closed() -> None:
    record = {
        "authority_channel": {"id": "origin", "kind": "local", "locator": "outbox"},
        "authority_files": [{"bytes": 2, "path": "seed.json", "sha256": "a" * 64}],
        "content_copied": False,
        "execution": "never",
        "grants_authority": False,
        "identity_source": "operator-description",
        "schema": "rapp-work-pointer-successor/1",
        "source": str(ROOT / "example-source"),
        "source_binding_sha256": "b" * 64,
        "source_kind": "hive",
        "source_profile": None,
        "source_rappid": mint_rappid("example-owner", "example-hive"),
        "source_world_id": "w" * 128,
    }
    assert migration_module.validate_pointer_record(record) == record
    for change, code in (
        ({"source_world_id": "w" * 129}, "REFUSE_POINTER_WORLD"),
        ({"grants_authority": True}, "REFUSE_POINTER_RECORD"),
        ({"content_copied": True}, "REFUSE_POINTER_RECORD"),
        ({"execution": "on-demand"}, "REFUSE_POINTER_RECORD"),
        ({"source_kind": "workspace"}, "REFUSE_POINTER_RECORD"),
        ({"source_profile": "rapp-hive/1"}, "REFUSE_POINTER_RECORD"),
        ({"authority_channel": None}, "REFUSE_POINTER_RECORD"),
        ({"authority_files": []}, "REFUSE_POINTER_RECORD"),
        (
            {"authority_files": [{"bytes": 2, "path": "../seed.json", "sha256": "a" * 64}]},
            "REFUSE_PATH",
        ),
        ({"source_kind": ["hive"]}, "REFUSE_POINTER_RECORD"),
        ({"extra": 1}, "REFUSE_INPUT_KEYS"),
        (
            {"authority_channel": {"id": "origin", "kind": "local", "locator": "a@b"}},
            "REFUSE_POINTER_CHANNEL",
        ),
    ):
        with pytest.raises(Refusal) as error:
            migration_module.validate_pointer_record({**record, **change})
        assert error.value.code == code, change


def _deprecated_compat() -> tuple[Any, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return private_hive_prepare(), private_hive()


def test_historical_private_hive_repositories(sandbox: Path) -> None:
    preparation, deployment = _deprecated_compat()
    workspace = sandbox / "workspace"
    workspace.mkdir(mode=0o700)
    (workspace / "rappid.json").write_bytes(
        canonical_bytes(
            {
                "mode": "solo",
                "rappid": mint_rappid("example-owner", "legacy-workspace"),
                "workspace_spec": "legacy-local/1",
            }
        )
    )
    (workspace / "notes.md").write_bytes(b"# Notes\n\nSynthetic workspace content.\n")
    git_seed(workspace)
    key = deployment.keys.create(sandbox / "custody", "example-owner")
    arguments = SimpleNamespace(
        workspace=str(workspace),
        member_rappid=key.rappid,
        hive_name="example-hive",
        world_id="example-world",
    )
    preparation.command_prepare(arguments)
    prepared = migrate({"source": str(workspace), "target": str(sandbox / "prepared-successor")})
    assert prepared["status"] == "planned", prepared["refusal"]

    channels = [
        {
            "id": "example-store",
            "kind": "filesystem",
            "path": str(sandbox / "publication"),
            "role": "authority",
        }
    ]
    publisher = sandbox / "publisher"
    deployment.release.initialize(workspace, publisher, key, channels)
    staged = preparation.command_stage(
        SimpleNamespace(workspace=str(workspace), outbox=str(sandbox / "outbox"))
    )
    built = deployment.release.build(publisher, key, Path(staged["outbox"]))
    deployment.release.approve(publisher, key, built["plan_hash"])
    deployment.release.publish(publisher, key, built["plan_hash"])
    anchor = deployment.release.export_anchor(publisher)

    member = sandbox / "member-client"
    deployment.client.initialize(
        member,
        canonical_bytes(anchor),
        expected_spki_sha256=hashlib.sha256(key.spki).hexdigest(),
    )
    deployment.client.pull(member, channels[0])
    deployment.client.materialize(member, sandbox / "member-copy")
    refused(
        migrate(
            {"source": str(sandbox / "member-copy"), "target": str(sandbox / "copy-successor")}
        ),
        "REFUSE_PATH_UNSAFE",
    )

    checkout = sandbox / "hive-repository"
    shutil.copytree(sandbox / "publication", checkout)
    (checkout / "owner-anchor.json").write_bytes(canonical_bytes(anchor))
    git_seed(checkout)
    before = snapshot(checkout)
    refused(
        migrate({"source": str(checkout), "target": str(sandbox / "successor")}),
        "REFUSE_PATH_UNSAFE",
    )
    genesis = f"objects/wave/{anchor['genesis_frame_hash']}.json"
    hive = {
        "authority_channel": {
            "id": "example-store",
            "kind": "local",
            "locator": "private-filesystem:example-store",
        },
        "authority_paths": [genesis],
        "hive_rappid": anchor["hive_rappid"],
        "world_id": anchor["world_id"],
    }
    other = mint_rappid("example-owner", "other")
    by_frame = plan(checkout, sandbox / "bad", {**hive, "hive_rappid": other})
    refused(by_frame, "REFUSE_POINTER_CLAIM")
    assert by_frame["refusal"]["details"] == {"path": genesis}
    another_world = {**hive, "authority_paths": ["refs/current.json"], "world_id": "other-world"}
    by_anchor = plan(checkout, sandbox / "bad", another_world)
    refused(by_anchor, "REFUSE_POINTER_CLAIM")
    assert by_anchor["refusal"]["details"] == {"path": "owner-anchor.json"}
    planned = planned_ok(checkout, sandbox / "successor", hive)
    bound = [
        entry["path"] for entry in planned["result"]["plan"]["source_binding"]["authority_files"]
    ]
    assert bound == sorted([genesis, "owner-anchor.json", "refs/current.json"])
    assert apply(checkout, sandbox / "successor", planned)["status"] == "applied"
    record = pointer(sandbox / "successor")
    assert record["source_rappid"] == anchor["hive_rappid"]
    assert record["authority_channel"] == hive["authority_channel"]
    assert listing(sandbox / "successor") == SUCCESSOR_FILES
    assert snapshot(checkout) == before


def test_cli_pointer_only_plan_and_exact_apply(sandbox: Path) -> None:
    source, target = sandbox / "seeded", sandbox / "successor"
    hive = seeded_hive(source)
    description = sandbox / "hive.json"
    description.write_text(json.dumps(hive), encoding="utf-8")
    environment = {
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT / "src"),
    }

    def run(*arguments: str) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, "-m", "rapp_work", "migrate", *arguments],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        value = json.loads(completed.stdout)
        assert isinstance(value, dict)
        return value

    base = ("--source", str(source), "--target", str(target), "--successor", "pointer-only")
    planned = run(*base, "--hive", str(description))
    assert planned["status"] == "planned", planned["refusal"]
    plan_file = sandbox / "plan.json"
    plan_file.write_text(json.dumps(planned), encoding="utf-8")
    apply_arguments = (
        "--apply",
        "--plan",
        str(plan_file),
        "--plan-sha256",
        planned["result"]["plan_sha256"],
    )
    refused(run(*base, "--hive", str(description), *apply_arguments), "REFUSE_APPLY_REQUIRED")
    refused(
        run("--source", str(source), "--target", str(target), *apply_arguments), "REFUSE_INPUT_KEYS"
    )
    applied = run(*base, *apply_arguments)
    assert applied["status"] == "applied", applied["refusal"]
    assert listing(target) == SUCCESSOR_FILES


def test_static_api_lists_pointer_only_inputs() -> None:
    operations = {item["name"]: item for item in api_metadata()["operations"]}
    assert operations["migrate"]["required_inputs"] == ["source", "target"]
    assert operations["migrate"]["optional_inputs"] == [
        "apply",
        "hive",
        "plan",
        "plan_sha256",
        "successor",
    ]
    assert migration_module.POINTER_SUCCESSOR == "pointer-only"


def proposed_validators() -> dict[str, Any]:
    import jsonschema
    from referencing import Registry
    from referencing.jsonschema import DRAFT202012

    blocks = re.findall(
        r"<!-- schema: (\S+) -->\n```json\n(.*?)\n```",
        PROPOSAL.read_text(encoding="utf-8"),
        re.S,
    )
    schemas = {name: json.loads(body) for name, body in blocks}
    assert sorted(schemas) == [
        "rapp-work-pointer-successor-plan/1",
        "rapp-work-pointer-successor-source/1",
        "rapp-work-pointer-successor/1",
    ]
    registry: Any = Registry().with_resources(
        (schema["$id"], DRAFT202012.create_resource(schema)) for schema in schemas.values()
    )
    validators = {}
    for name, schema in schemas.items():
        jsonschema.Draft202012Validator.check_schema(schema)
        validators[name] = jsonschema.Draft202012Validator(schema, registry=registry)
    return validators


def test_proposed_schemas_match_the_reference_implementation(sandbox: Path) -> None:
    validators = proposed_validators()
    record_schema = validators["rapp-work-pointer-successor/1"]
    source_schema = validators["rapp-work-pointer-successor-source/1"]
    plan_schema = validators["rapp-work-pointer-successor-plan/1"]
    source = sandbox / "seeded"
    hive = seeded_hive(source)
    workspace = identity_workspace(sandbox / "workspace", "Example World " + "w" * 90)
    plans = [
        planned_ok(source, sandbox / "hive-successor", hive)["result"]["plan"],
        planned_ok(workspace, sandbox / "workspace-successor")["result"]["plan"],
    ]
    records = []
    for value in plans:
        plan_schema.validate(value)
        source_schema.validate(value["source_binding"])
        record = json.loads(base64.b64decode(value["actions"][0]["content_base64"]))
        record_schema.validate(record)
        records.append(record)
        assert migration_module.PointerSuccessorPlan.from_dict(value).to_dict() == value

    described, identified = records
    for change in (
        {"source_world_id": "w" * 129},
        {"source_world_id": ""},
        {"source_world_id": "a\x1fb"},
        {"source_world_id": "a\x85b"},
        {"source_world_id": "a\u202eb"},
        {"grants_authority": True},
        {"content_copied": True},
        {"execution": "on-demand"},
        {"unexpected": 1},
        {"authority_channel": None},
        {"authority_channel": {"id": "origin", "kind": "local", "locator": "a@b"}},
        {"authority_channel": {"id": "Origin", "kind": "local", "locator": "outbox"}},
        {"authority_channel": {"id": "origin", "kind": "ftp", "locator": "outbox"}},
        {"source_kind": "workspace"},
        {"source_profile": "rapp-hive/1"},
        {"authority_files": []},
        {"source_binding_sha256": "X" * 64},
        {"source_rappid": "example-seeded-hive"},
    ):
        forged = {**described, **change}
        assert not record_schema.is_valid(forged), change
        with pytest.raises(Refusal):
            migration_module.validate_pointer_record(forged)
    for change in (
        {"authority_channel": {"id": "origin", "kind": "local", "locator": "outbox"}},
        {"source_kind": "hive"},
        {"source_profile": None},
    ):
        forged = {**identified, **change}
        assert not record_schema.is_valid(forged), change
        with pytest.raises(Refusal):
            migration_module.validate_pointer_record(forged)

    binding = plans[1]["source_binding"]
    for change in (
        {"described_paths": ["notes.md"]},
        {"kind": "hive"},
        {"root_identity": {"device": 1, "inode": 2}},
        {"world_id": "w" * 129},
    ):
        forged_binding = {**binding, **change}
        assert not source_schema.is_valid(forged_binding), change
        with pytest.raises(Refusal):
            migration_module._check_pointer_binding(forged_binding)

    action = plans[0]["actions"][0]
    for change in (
        {"actions": [action, action]},
        {"actions": [{**action, "path": "copied/POLICY.md"}]},
        {"actions": [{**action, "mode": 420}]},
        {"successor": "copy"},
        {"network": True},
    ):
        forged_plan = {**plans[0], **change}
        assert not plan_schema.is_valid(forged_plan), change
        with pytest.raises(Refusal):
            migration_module.PointerSuccessorPlan.from_dict(forged_plan)

    decomposed = {**described, "source_world_id": "e\u0301"}
    assert record_schema.is_valid(decomposed)
    with pytest.raises(Refusal) as error:
        migration_module.validate_pointer_record(decomposed)
    assert error.value.code == "REFUSE_POINTER_WORLD"
