from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rapp_work import FilesystemTransport, PrivateGitTransport, SignedRelease
from rapp_work.errors import Refusal
from rapp_work.rapp1 import mint_rappid


def test_filesystem_transport_is_immutable_and_cas_bound(sandbox: Path) -> None:
    transport = FilesystemTransport(sandbox / "store")
    files = {"objects/a": b"one"}
    pointer = b"pointer-1"
    plan = transport.publication_plan(
        files,
        pointer,
        expected_pointer_sha256=None,
    )
    with pytest.raises(Refusal, match="REFUSE_APPLY_REQUIRED"):
        transport.publish(
            files,
            pointer,
            expected_pointer_sha256=None,
            apply=False,
            plan_sha256=plan.sha256,
            plan=plan,
        )
    first = transport.publish(
        files,
        pointer,
        expected_pointer_sha256=None,
        apply=True,
        plan_sha256=plan.sha256,
        plan=plan.to_dict(),
    )
    assert first["network"] is False
    cas_plan = transport.publication_plan(
        files,
        b"pointer-2",
        expected_pointer_sha256="0" * 64,
    )
    with pytest.raises(Refusal, match="REFUSE_TRANSPORT_CAS"):
        transport.publish(
            files,
            b"pointer-2",
            expected_pointer_sha256="0" * 64,
            apply=True,
            plan_sha256=cas_plan.sha256,
            plan=cas_plan,
        )
    collision_plan = transport.publication_plan(
        {"objects/a": b"changed"},
        pointer,
        expected_pointer_sha256=first["pointer_sha256"],
    )
    with pytest.raises(Refusal, match="REFUSE_IMMUTABLE_COLLISION"):
        transport.publish(
            {"objects/a": b"changed"},
            pointer,
            expected_pointer_sha256=first["pointer_sha256"],
            apply=True,
            plan_sha256=collision_plan.sha256,
            plan=collision_plan,
        )


def test_filesystem_transport_refuses_unbound_or_changed_plan_before_effects(
    sandbox: Path,
) -> None:
    root = sandbox / "store"
    transport = FilesystemTransport(root)
    files = {"release.json": b"one"}
    plan = transport.publication_plan(files, b"pointer", expected_pointer_sha256=None)
    with pytest.raises(Refusal, match="REFUSE_PLAN"):
        transport.publish(
            files,
            b"pointer",
            expected_pointer_sha256=None,
            apply=True,
            plan_sha256="a" * 64,
        )
    with pytest.raises(Refusal, match="REFUSE_PLAN"):
        transport.publish(
            {"release.json": b"changed"},
            b"pointer",
            expected_pointer_sha256=None,
            apply=True,
            plan_sha256=plan.sha256,
            plan=plan,
        )
    with pytest.raises(Refusal, match="REFUSE_PLAN"):
        transport.publish(
            files,
            b"changed-pointer",
            expected_pointer_sha256=None,
            apply=True,
            plan_sha256=plan.sha256,
            plan=plan,
        )
    assert not root.exists()


def test_private_git_transport_uses_no_ambient_credentials(sandbox: Path) -> None:
    repository = sandbox / "private.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--template=", str(repository)],
        check=True,
        capture_output=True,
    )
    transport = PrivateGitTransport(repository)
    environment = transport.sanitized_environment()
    assert "HOME" not in environment
    assert "GH_TOKEN" not in environment
    assert "GITHUB_TOKEN" not in environment
    assert "SSH_AUTH_SOCK" not in environment
    files = {"release.json": b"{}"}
    created_utc = "2026-09-18T12:00:00.000Z"
    plan = transport.publication_plan(
        files,
        expected_ref=None,
        created_utc=created_utc,
    )
    signed = SignedRelease(plan, mint_rappid("example", "transport"), "fixture-signature")
    first = transport.publish(
        files,
        expected_ref=None,
        created_utc=created_utc,
        apply=True,
        plan_sha256=plan.sha256,
        plan=signed,
    )
    assert first["network"] is False
    assert transport.snapshot() == files
    next_files = {"release.json": b'{"next":true}'}
    next_utc = "2026-09-18T12:00:01.000Z"
    next_plan = transport.publication_plan(
        next_files,
        expected_ref=None,
        created_utc=next_utc,
    )
    with pytest.raises(Refusal, match="REFUSE_TRANSPORT_CAS"):
        transport.publish(
            next_files,
            expected_ref=None,
            created_utc=next_utc,
            apply=True,
            plan_sha256=next_plan.sha256,
            plan=next_plan,
        )


def test_private_git_transport_binds_files_ref_and_timestamp_before_writes(
    sandbox: Path,
) -> None:
    repository = sandbox / "private.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "--template=", str(repository)],
        check=True,
        capture_output=True,
    )
    transport = PrivateGitTransport(repository)
    files = {"release.json": b"{}"}
    created_utc = "2026-09-18T12:00:00.000Z"
    plan = transport.publication_plan(
        files,
        expected_ref=None,
        created_utc=created_utc,
    )
    attempts = (
        ({"release.json": b'{"changed":true}'}, None, created_utc),
        (files, "0" * transport.oid_length, created_utc),
        (files, None, "2026-09-18T12:00:01.000Z"),
    )
    for changed_files, expected_ref, timestamp in attempts:
        with pytest.raises(Refusal, match="REFUSE_PLAN"):
            transport.publish(
                changed_files,
                expected_ref=expected_ref,
                created_utc=timestamp,
                apply=True,
                plan_sha256=plan.sha256,
                plan=plan,
            )
        assert transport.current_ref() is None


def test_private_git_network_locator_refuses() -> None:
    with pytest.raises(Refusal, match="REFUSE_NETWORK"):
        PrivateGitTransport(Path("https://example.invalid/private.git"))
