from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest

import rapp_work.moves as moves_module
import rapp_work.plans as plans_module
import rapp_work.workspace as workspace_module
from rapp_work import (
    Organization,
    Workspace,
    discover,
    migrate,
    scaffold,
    status,
    update,
    verify,
)
from rapp_work._json import canonical_bytes, canonical_text, strict_json_loads
from rapp_work.errors import Refusal
from rapp_work.plans import FileAction, FileMove, MovePlan, ReleasePlan
from rapp_work.rapp1 import mint_rappid

ROOT = Path(__file__).resolve().parents[1]
AGENT = b"class ExampleAgent:\n    name = 'Example'\n"
NOTE = b"# Plan\n\nKeep this note.\n"
SOURCE = "agents/example_agent.py"
DESTINATION = "agents/experimental/example_agent.py"
MARKER = ".rapp-work/move-recovery.json"
V1_PLAN_SHA256 = "196dd7112d6371b94535f7e136dd457491c2efc1c82428ca05bbd9409adb801e"
MOVE_PLAN_SHA256 = "84f659901443ab4500d6664db1073e88852bb8236ad621f6938b8ac82f9f3f5c"
INVERSE_PLAN_SHA256 = "ba4845523f60e4d51d54ffe749ed8b1b2298d0e95e2435cec9c25cf8e77c347b"
VERSION_2 = b"# version 2: the owner's latest save\n"


class SimulatedCrash(BaseException):
    """Stands in for process death: no SDK handler may intercept it."""


def crash(*_: Any, **__: Any) -> None:
    raise SimulatedCrash


def hook_flip(
    monkeypatch: pytest.MonkeyPatch,
    *,
    before: Any = None,
    after: Any = None,
    name: str = "example_agent.py",
) -> None:
    """Run another process's action around the first rename of ``name`` into place only."""
    real = moves_module._rename_exclusive
    fired: list[bool] = []

    def hooked(source_directory: int, source: str, destination_directory: int, target: str) -> None:
        hit = source == name and target != moves_module.MOVE_RECOVERY_NAME and not fired
        if hit:
            fired.append(True)
            if before is not None:
                before()
        real(source_directory, source, destination_directory, target)
        if hit and after is not None:
            after()

    monkeypatch.setattr(moves_module, "_rename_exclusive", hooked)


def atomic_save(path: Path, data: bytes) -> None:
    """What editors do: write a temporary file, then rename it over the original."""
    temporary = path.with_name(path.name + ".save-tmp")
    temporary.write_bytes(data)
    temporary.chmod(0o644)
    os.rename(temporary, path)


def make_root(sandbox: Path, *, kind: str = "workspace") -> Path:
    root = sandbox / kind
    request = {
        "kind": kind,
        "mode": "solo",
        "owner_label": "example",
        "root": str(root),
        "slug": "finance" if kind == "workspace" else "company",
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
    (root / "agents" / "experimental").mkdir(parents=True)
    (root / SOURCE).write_bytes(AGENT)
    (root / SOURCE).chmod(0o644)
    return root


def tree(root: Path) -> dict[str, tuple[Any, ...]]:
    """Every entry below the root: kind, bytes, permission mode, inode, and links."""
    entries: dict[str, tuple[Any, ...]] = {}
    for directory, directories, files in os.walk(root):
        for name in [*directories, *files]:
            path = Path(directory) / name
            info = path.lstat()
            relative = path.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode):
                entries[relative] = ("symlink", os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                entries[relative] = ("directory", stat.S_IMODE(info.st_mode), info.st_ino)
            elif stat.S_ISREG(info.st_mode):
                entries[relative] = (
                    "file",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    stat.S_IMODE(info.st_mode),
                    info.st_ino,
                    info.st_nlink,
                )
            else:
                entries[relative] = ("special", stat.S_IFMT(info.st_mode))
    return entries


def moves(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"destination": destination, "source": source} for source, destination in pairs]


def plan_moves(root: Path, *pairs: tuple[str, str]) -> dict[str, Any]:
    planned = update({"moves": moves(*pairs), "root": str(root)})
    assert planned["status"] == "planned", planned["refusal"]
    return dict(planned["result"])


def apply(root: Path, planned: dict[str, Any], *, plan_sha256: str | None = None) -> dict[str, Any]:
    return update(
        {
            "apply": True,
            "plan": planned["plan"],
            "plan_sha256": planned["plan_sha256"] if plan_sha256 is None else plan_sha256,
            "root": str(root),
        }
    )


def inverse(root: Path, planned: dict[str, Any]) -> dict[str, Any]:
    result = update({"inverse_of": planned["plan"], "root": str(root)})
    assert result["status"] == "planned", result["refusal"]
    return dict(result["result"])


def refusal(result: dict[str, Any]) -> str:
    assert result["status"] == "refused", result
    assert result["result"] is None
    return str(result["refusal"]["code"])


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_float(item) for item in value)
    return False


def test_move_is_plan_only_by_default(sandbox: Path) -> None:
    root = make_root(sandbox)
    before = tree(root)
    planned = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert planned["status"] == "planned"
    result = planned["result"]
    plan = result["plan"]
    assert result["effects"] is False
    assert set(plan) == {
        "moves",
        "network",
        "operation",
        "preconditions",
        "profile",
        "protocol",
        "schema",
        "subject",
        "target",
    }
    assert plan["schema"] == "rapp-work-move-plan/1"
    assert plan["operation"] == "update"
    assert plan["network"] is False
    assert plan["moves"] == [
        {
            "bytes": len(AGENT),
            "destination": DESTINATION,
            "mode": 0o644,
            "operation": "move",
            "sha256": sha256(AGENT),
            "source": SOURCE,
        }
    ]
    assert set(plan["preconditions"]) == {"identity_sha256", "root_identity"}
    assert result["plan_sha256"] == sha256(canonical_bytes(plan))
    assert tree(root) == before
    assert not (root / MARKER).exists()


def test_move_apply_requires_explicit_complete_exact_plan(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    assert refusal(apply(root, planned, plan_sha256="0" * 64)) == "REFUSE_PLAN_HASH"
    missing_plan = update({"apply": True, "plan_sha256": planned["plan_sha256"], "root": str(root)})
    assert refusal(missing_plan) == "REFUSE_APPLY_REQUIRED"
    missing_hash = update({"apply": True, "plan": planned["plan"], "root": str(root)})
    assert refusal(missing_hash) == "REFUSE_APPLY_REQUIRED"
    implicit = update(
        {"plan": planned["plan"], "plan_sha256": planned["plan_sha256"], "root": str(root)}
    )
    assert refusal(implicit) == "REFUSE_APPLY_REQUIRED"
    assert tree(root) == before

    source_inode = (root / SOURCE).stat().st_ino
    applied = apply(root, planned)
    assert applied["status"] == "applied"
    assert applied["result"]["status"] == "moved"
    assert applied["result"]["recovered"] is False
    assert applied["result"]["plan_sha256"] == planned["plan_sha256"]
    assert applied["result"]["verification"]["status"] == "verified"
    assert not (root / SOURCE).exists()
    moved = (root / DESTINATION).lstat()
    assert (root / DESTINATION).read_bytes() == AGENT
    assert (moved.st_ino, moved.st_nlink, stat.S_IMODE(moved.st_mode)) == (source_inode, 1, 0o644)
    assert not (root / MARKER).exists()
    assert verify({"root": str(root)})["status"] == "ok"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("edit", "REFUSE_PRECONDITION"),
        ("chmod", "REFUSE_PRECONDITION"),
        ("remove", "REFUSE_MOVE_SOURCE"),
        ("hardlink", "REFUSE_PATH_TYPE"),
    ],
)
def test_changed_source_is_refused_before_any_write(sandbox: Path, change: str, code: str) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    if change == "edit":
        (root / SOURCE).write_bytes(AGENT + b"# edited\n")
    elif change == "chmod":
        (root / SOURCE).chmod(0o600)
    elif change == "remove":
        (root / SOURCE).unlink()
    else:
        os.link(root / SOURCE, root / "agents/twin_agent.py")
    before = tree(root)
    assert refusal(apply(root, planned)) == code
    assert tree(root) == before
    assert not (root / DESTINATION).exists()
    assert not (root / MARKER).exists()


@pytest.mark.parametrize("kind", ["file", "dangling-symlink", "directory"])
def test_destination_created_after_planning_is_never_replaced(sandbox: Path, kind: str) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    winner = root / DESTINATION
    if kind == "file":
        winner.write_bytes(b"winner")
    elif kind == "dangling-symlink":
        winner.symlink_to(root / "missing-target")
    else:
        winner.mkdir()
    before = tree(root)
    assert refusal(apply(root, planned)) == "REFUSE_MOVE_COLLISION"
    assert tree(root) == before
    assert (root / SOURCE).read_bytes() == AGENT
    assert not (root / MARKER).exists()


def test_same_size_change_after_the_replay_is_refused_before_the_flip(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    real = moves_module._create_locked_marker

    def change_after_marker(directory: int, data: bytes) -> int:
        descriptor = real(directory, data)
        with (root / SOURCE).open("r+b") as stream:
            stream.write(AGENT.upper())
        return descriptor

    monkeypatch.setattr(moves_module, "_create_locked_marker", change_after_marker)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_PRECONDITION"
    assert refused["refusal"]["details"]["recovery"] == "none"
    assert (root / SOURCE).read_bytes() == AGENT.upper()
    assert (root / SOURCE).stat().st_nlink == 1
    assert not (root / DESTINATION).exists()
    assert not (root / MARKER).exists()


@pytest.mark.parametrize("kind", ["file", "directory", "dangling-symlink"])
def test_flip_race_never_replaces_the_winner(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    winner = root / DESTINATION

    def create_the_winner() -> None:
        if kind == "file":
            winner.write_bytes(b"winner")
        elif kind == "directory":
            winner.mkdir()
        else:
            winner.symlink_to(root / "missing-target")

    hook_flip(monkeypatch, before=create_the_winner)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_MOVE_COLLISION"
    assert refused["refusal"]["details"]["recovery"] == "none"
    if kind == "file":
        assert winner.read_bytes() == b"winner"
    elif kind == "directory":
        assert winner.is_dir() and list(winner.iterdir()) == []
    else:
        assert os.readlink(winner) == str(root / "missing-target")
    assert (root / SOURCE).read_bytes() == AGENT
    assert (root / SOURCE).stat().st_nlink == 1
    assert not (root / MARKER).exists()


@pytest.mark.parametrize(
    ("race", "reason"),
    [
        ("atomic-save", "source-replaced"),
        ("renamed-away-and-replaced", "source-replaced"),
        ("in-place-edit", "source-changed"),
        ("same-size-edit", "source-changed"),
        ("hardlink", "source-changed"),
        ("chmod", "source-changed"),
    ],
)
def test_a_concurrent_change_of_the_source_is_undone_and_never_lost(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    race: str,
    reason: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    source = root / SOURCE
    backup = root / "agents/example_agent.py.bak"

    def concurrent_writer() -> None:
        if race == "atomic-save":
            atomic_save(source, VERSION_2)
        elif race == "renamed-away-and-replaced":
            os.rename(source, backup)
            source.write_bytes(VERSION_2)
            source.chmod(0o644)
        elif race == "in-place-edit":
            with source.open("ab") as stream:
                stream.write(b"# appended by the owner\n")
        elif race == "same-size-edit":
            with source.open("r+b") as stream:
                stream.write(AGENT.upper())
        elif race == "hardlink":
            os.link(source, root / "agents/twin_agent.py")
        else:
            source.chmod(0o600)

    expected = {
        "atomic-save": VERSION_2,
        "renamed-away-and-replaced": VERSION_2,
        "in-place-edit": AGENT + b"# appended by the owner\n",
        "same-size-edit": AGENT.upper(),
        "hardlink": AGENT,
        "chmod": AGENT,
    }[race]
    hook_flip(monkeypatch, before=concurrent_writer)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_FILE_RACE"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"]) == (reason, True)
    assert (details["completed_moves"], details["recovery"]) == (0, "none")
    assert source.read_bytes() == expected
    assert not (root / DESTINATION).exists()
    assert not (root / MARKER).exists()
    if race == "hardlink":
        assert (root / "agents/twin_agent.py").read_bytes() == AGENT
    if race == "renamed-away-and-replaced":
        assert backup.read_bytes() == AGENT


def test_an_atomic_save_after_the_flip_keeps_both_versions(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    hook_flip(monkeypatch, after=lambda: atomic_save(root / SOURCE, VERSION_2))
    applied = apply(root, planned)
    assert applied["status"] == "applied"
    assert (root / DESTINATION).read_bytes() == AGENT
    assert (root / SOURCE).read_bytes() == VERSION_2
    assert not (root / MARKER).exists()


def test_a_blocked_undo_keeps_every_version_and_the_marker(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    version_3 = b"# version 3: saved again while the move was undone\n"
    hook_flip(
        monkeypatch,
        before=lambda: atomic_save(root / SOURCE, VERSION_2),
        after=lambda: atomic_save(root / SOURCE, version_3),
    )
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_FILE_RACE"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "source-replaced",
        False,
        "pending",
    )
    assert (root / SOURCE).read_bytes() == version_3
    assert (root / DESTINATION).read_bytes() == VERSION_2
    assert (root / MARKER).is_file()
    assert refusal(apply(root, planned)) == "REFUSE_RECOVERY_STATE"
    assert (root / SOURCE).read_bytes() == version_3
    assert (root / DESTINATION).read_bytes() == VERSION_2


def test_a_destination_taken_after_the_flip_is_reported_not_chased(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    elsewhere = root / "agents/elsewhere_agent.py"
    hook_flip(monkeypatch, after=lambda: os.rename(root / DESTINATION, elsewhere))
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_FILE_RACE"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "destination-missing",
        False,
        "pending",
    )
    assert elsewhere.read_bytes() == AGENT
    assert not (root / SOURCE).exists()
    assert (root / MARKER).is_file()


def folds(directory: Path, folding: str) -> bool:
    """Whether this filesystem resolves another case or normalization of a stored name."""
    stored, other = {
        "case": ("fold-probe.txt", "FOLD-PROBE.txt"),
        "normalization": ("fold-probe-\u00e9.txt", "fold-probe-e\u0301.txt"),
    }[folding]
    probe = directory / stored
    probe.write_bytes(b"")
    try:
        return os.path.lexists(directory / other)
    finally:
        probe.unlink()


def stored_note(root: Path) -> tuple[str, str]:
    """Create ``notes/café.md``; return its stored name and its other normalization form."""
    (root / "notes/archive").mkdir(parents=True)
    (root / "notes/caf\u00e9.md").write_bytes(NOTE)
    stored = next(name for name in os.listdir(root / "notes") if name != "archive")
    composed = unicodedata.normalize("NFC", stored)
    return stored, unicodedata.normalize("NFD", stored) if stored == composed else composed


@pytest.mark.parametrize(
    ("alias", "folding"),
    [
        ("case-source-name", "case"),
        ("case-source-directory", "case"),
        ("case-destination-directory", "case"),
        ("normalization-source-name", "normalization"),
        ("case-note-destination-directory", "case"),
    ],
)
def test_existing_entries_are_named_by_their_stored_spelling(
    sandbox: Path,
    alias: str,
    folding: str,
) -> None:
    root = make_root(sandbox)
    stored, other = stored_note(root)
    if not folds(root, folding):
        pytest.skip(f"this filesystem keeps other {folding} spellings apart")
    pair = {
        "case-source-name": ("agents/Example_Agent.py", "agents/experimental/Example_Agent.py"),
        "case-source-directory": ("Agents/example_agent.py", DESTINATION),
        "case-destination-directory": (SOURCE, "agents/Experimental/example_agent.py"),
        "normalization-source-name": ("notes/" + other, "notes/archive/" + other),
        "case-note-destination-directory": ("notes/" + stored, "Notes/archive/" + stored),
    }[alias]
    before = tree(root)
    result = update({"moves": moves(pair), "root": str(root)})
    assert refusal(result) == "REFUSE_PATH_SPELLING"
    assert result["refusal"]["details"]["reason"] == "stored-spelling"
    assert tree(root) == before


def test_a_stored_non_ascii_name_round_trips_exactly(sandbox: Path) -> None:
    root = make_root(sandbox)
    stored, _ = stored_note(root)
    source = "notes/" + stored
    before = tree(root)
    planned = plan_moves(root, (source, "notes/archive/" + stored))
    assert apply(root, planned)["status"] == "applied"
    undo = inverse(root, planned)
    assert apply(root, undo)["status"] == "applied"
    assert tree(root) == before
    assert os.listdir(root / "notes/archive") == []


def test_a_source_respelled_after_planning_is_refused_by_the_replay(sandbox: Path) -> None:
    root = make_root(sandbox)
    if not folds(root, "case"):
        pytest.skip("this filesystem keeps other case spellings apart")
    planned = plan_moves(root, (SOURCE, DESTINATION))
    os.rename(root / SOURCE, root / "agents/Example_agent.py")
    before = tree(root)
    assert refusal(apply(root, planned)) == "REFUSE_PATH_SPELLING"
    assert tree(root) == before


def test_a_destination_the_filesystem_stores_differently_is_undone(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    real = moves_module._stored

    def respelled(directory: int, name: str, *, path: str) -> bool:
        # A filesystem that normalizes new names (HFS+ stores decomposed forms) keeps none
        # under the planned spelling.
        return False if path == DESTINATION else real(directory, name, path=path)

    monkeypatch.setattr(moves_module, "_stored", respelled)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_PATH_SPELLING"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "destination-spelling",
        True,
        "none",
    )
    assert tree(root) == before


def test_a_destination_name_the_filesystem_rewrites_is_undone(sandbox: Path) -> None:
    root = make_root(sandbox)
    stored, other = stored_note(root)
    probe = root / "notes/archive" / other
    probe.write_bytes(b"")
    rewritten = os.listdir(root / "notes/archive") != [other]
    probe.unlink()
    if not rewritten:
        pytest.skip("this filesystem stores new names as spelled")
    planned = plan_moves(root, ("notes/" + stored, "notes/archive/" + other))
    before = tree(root)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_PATH_SPELLING"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "destination-spelling",
        True,
        "none",
    )
    assert tree(root) == before


def test_an_undo_that_would_move_another_file_back_is_not_reported_undone(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    version_3 = b"# version 3: saved at the destination during the undo\n"
    real = moves_module._rename_exclusive
    calls: list[str] = []

    def hooked(source_directory: int, source: str, destination_directory: int, target: str) -> None:
        if source == "example_agent.py" and target == "example_agent.py":
            calls.append(source)
            if len(calls) == 1:
                atomic_save(root / SOURCE, VERSION_2)
            elif len(calls) == 2:
                atomic_save(root / DESTINATION, version_3)
        real(source_directory, source, destination_directory, target)

    monkeypatch.setattr(moves_module, "_rename_exclusive", hooked)
    refused = apply(root, planned)
    assert len(calls) == 2
    assert refusal(refused) == "REFUSE_FILE_RACE"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "source-replaced",
        False,
        "pending",
    )
    assert (root / SOURCE).read_bytes() == version_3
    assert (root / MARKER).is_file()


def test_a_parent_swapped_while_it_is_opened_is_refused(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    real = moves_module._lstat_at
    swapped: list[bool] = []

    def swapping_lstat(directory: int, name: str) -> os.stat_result | None:
        info = real(directory, name)
        if name == "experimental" and not swapped:
            swapped.append(True)
            os.rename(root / "agents/experimental", root / "agents/experimental-old")
            (root / "agents/experimental").mkdir()
        return info

    monkeypatch.setattr(moves_module, "_lstat_at", swapping_lstat)
    result = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert swapped == [True]
    assert refusal(result) == "REFUSE_FILE_RACE"
    assert result["refusal"]["message"] == "move parent changed while it was opened"
    assert (root / SOURCE).read_bytes() == AGENT
    assert not (root / MARKER).exists()


def test_a_marker_edited_in_place_during_apply_is_never_removed(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    marker = root / MARKER

    def edit_the_marker() -> None:
        with marker.open("r+b") as stream:
            stream.write(b" ")

    hook_flip(monkeypatch, after=edit_the_marker)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_RECOVERY_BINDING"
    assert marker.read_bytes().startswith(b" ")
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / SOURCE).exists()


def test_a_resume_refuses_a_path_the_sdk_inventory_now_owns(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    monkeypatch.setattr(moves_module, "_flip", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    assert (root / MARKER).is_file()
    real = moves_module._integration

    def owning(path: Path, identity: dict[str, Any]) -> tuple[set[str], tuple[str, ...]]:
        owned, owned_paths = real(path, identity)
        return owned | {plans_module.fold_path(DESTINATION)}, owned_paths

    monkeypatch.setattr(moves_module, "_integration", owning)
    before = tree(root)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_MOVE_PROTECTED"
    assert refused["refusal"]["details"]["reason"] == "sdk-managed-file"
    assert tree(root) == before


@pytest.mark.parametrize("where", ["source", "source-parent", "destination-parent"])
def test_symlinks_are_refused_at_planning(sandbox: Path, where: str) -> None:
    root = make_root(sandbox)
    outside = sandbox / "outside"
    outside.mkdir()
    if where == "source":
        (root / "agents/link_agent.py").symlink_to(root / SOURCE)
        request = ("agents/link_agent.py", "agents/experimental/link_agent.py")
    elif where == "source-parent":
        (root / "linked").symlink_to(root / "agents", target_is_directory=True)
        request = ("linked/example_agent.py", DESTINATION)
    else:
        (root / "agents/outside").symlink_to(outside, target_is_directory=True)
        request = (SOURCE, "agents/outside/example_agent.py")
    before = tree(root)
    result = update({"moves": moves(request), "root": str(root)})
    assert refusal(result) == "REFUSE_SYMLINK"
    assert tree(root) == before
    assert list(outside.iterdir()) == []


def test_symlinked_root_is_refused(sandbox: Path) -> None:
    root = make_root(sandbox)
    alias = sandbox / "alias"
    alias.symlink_to(root, target_is_directory=True)
    assert refusal(update({"moves": moves((SOURCE, DESTINATION)), "root": str(alias)})) == (
        "REFUSE_SYMLINK"
    )


def test_parent_swapped_for_symlink_after_planning_is_refused(sandbox: Path) -> None:
    root = make_root(sandbox)
    outside = sandbox / "outside"
    outside.mkdir()
    planned = plan_moves(root, (SOURCE, DESTINATION))
    (root / "agents/experimental").rmdir()
    (root / "agents/experimental").symlink_to(outside, target_is_directory=True)
    before = tree(root)
    assert refusal(apply(root, planned)) == "REFUSE_SYMLINK"
    assert tree(root) == before
    assert list(outside.iterdir()) == []
    assert (root / SOURCE).read_bytes() == AGENT


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("hardlink", "REFUSE_PATH_TYPE"),
        ("fifo", "REFUSE_PATH_TYPE"),
        ("directory", "REFUSE_PATH_TYPE"),
        ("setuid", "REFUSE_PERMISSIONS"),
        ("oversize", "REFUSE_FILE_LIMIT"),
        ("missing", "REFUSE_MOVE_SOURCE"),
    ],
)
def test_unmovable_sources_are_refused(sandbox: Path, setup: str, code: str) -> None:
    root = make_root(sandbox)
    source = root / "agents/special_agent.py"
    if setup == "hardlink":
        os.link(root / SOURCE, source)
    elif setup == "fifo":
        os.mkfifo(source)
    elif setup == "directory":
        source.mkdir()
    elif setup == "setuid":
        source.write_bytes(AGENT)
        source.chmod(0o4755)
    elif setup == "oversize":
        with source.open("wb") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
    before = tree(root)
    request = ("agents/special_agent.py", "agents/experimental/special_agent.py")
    assert refusal(update({"moves": moves(request), "root": str(root)})) == code
    assert tree(root) == before


@pytest.mark.parametrize(
    "unsafe",
    [
        "../escape.py",
        "/absolute.py",
        "agents/../escape.py",
        "agents\\example_agent.py",
        "agents/example\x00_agent.py",
        "agents/example\x7f_agent.py",
        "./agents/example_agent.py",
        "agents//example_agent.py",
        "agents/example_agent.py/",
        "agents/./example_agent.py",
        "C:example_agent.py",
        ".",
        "",
        "a" * 513,
        7,
    ],
)
@pytest.mark.parametrize("side", ["source", "destination"])
def test_unsafe_paths_are_refused(sandbox: Path, unsafe: Any, side: str) -> None:
    root = make_root(sandbox)
    request = {"destination": DESTINATION, "source": SOURCE, side: unsafe}
    before = tree(root)
    assert refusal(update({"moves": [request], "root": str(root)})) == "REFUSE_PATH"
    assert tree(root) == before


@pytest.mark.parametrize(
    "character",
    [
        "\u200c",  # ignored by HFS+
        "\u200b",
        "\u200d",
        "\u200e",
        "\u202e",  # right-to-left override: would disguise the reviewed path
        "\u2066",
        "\u206a",  # ignored by HFS+
        "\ufeff",  # ignored by HFS+
        "\u00ad",
        "\u034f",
        "\u115f",
        "\u3164",
        "\ufe0f",
        "\U000e0001",
        "\U000e0100",
        "\u0085",
        "\u2028",
        "\u2029",
        "\ufdd0",
        "\U0010ffff",
        "\ue000",
        "\uf029",  # folded onto "." by the macOS exFAT driver
        "\ud800",
    ],
)
@pytest.mark.parametrize("side", ["source", "destination"])
def test_invisible_ignorable_and_unassigned_code_points_are_refused(
    sandbox: Path,
    character: str,
    side: str,
) -> None:
    root = make_root(sandbox)
    path = {"destination": DESTINATION, "source": SOURCE}[side].replace("_agent", character + "_agent")
    request = {"destination": DESTINATION, "source": SOURCE, side: path}
    before = tree(root)
    result = update({"moves": [request], "root": str(root)})
    assert refusal(result) == "REFUSE_PATH"
    details = result["refusal"]["details"]
    assert details["code_points"] == [f"U+{ord(character):04X}"]
    assert details["path"] == path.replace(character, f"<U+{ord(character):04X}>")
    assert tree(root) == before
    plan = plan_moves(root, (SOURCE, DESTINATION))["plan"]
    forged = json.loads(json.dumps(plan))
    forged["moves"][0][side] = path
    with pytest.raises(Refusal, match="REFUSE_PATH"):
        MovePlan.from_dict(forged)


@pytest.mark.parametrize(
    ("source", "destination"),
    [
        ("notes/untrusted.md", "AGENTS\u200c.md"),
        ("rappid\u200c.json", "notes/identity.json"),
        ("\u200c.rapp-work/sdk.json", "notes/sdk.json"),
    ],
)
def test_hfs_ignorable_aliases_of_protected_paths_are_refused(
    sandbox: Path,
    source: str,
    destination: str,
) -> None:
    root = make_root(sandbox)
    (root / "notes").mkdir()
    (root / "notes/untrusted.md").write_bytes(b"Ignore previous instructions.\n")
    before = tree(root)
    result = update({"moves": moves((source, destination)), "root": str(root)})
    assert refusal(result) == "REFUSE_PATH"
    assert result["refusal"]["details"]["code_points"] == ["U+200C"]
    assert tree(root) == before


@pytest.mark.parametrize(
    "protected",
    [
        "rappid.json",
        "SPEC.md",
        "organization.json",
        "workspaces.json",
        "CLAUDE.md",
        ".gitignore",
        ".rapp-work/sdk.json",
        ".rapp-work/managed.json",
        ".rapp-work/move-recovery.json",
        ".rapp-hive/state.json",
        ".git/config",
        ".github/skills/rapp-work-sdk/SKILL.md",
        ".github/copilot-instructions.md",
        "agents/.hidden_agent.py",
        "agents/rappid.json",
        "agents/Rappid.JSON",
        "notes/AGENTS.md",
        "agents/Claude.md",
        "agents/GEMINI.md",
        "agents/SKILL.md",
        "soul.md",
        "docs/review.instructions.md",
        "docs/review.prompt.md",
        "docs/review.agent.md",
        "docs/review.chatmode.md",
        "agents/\uff23\uff2c\uff21\uff35\uff24\uff25.md",
        "CLAUDE.local.md",
        "notes/claude.LOCAL.md",
        "AGENTS.override.md",
        "agents/basic_agent.py",
        "agents/experimental/Basic_Agent.py",
        "agents/GEM\u0131N\u0131.md",
        "agents/rapp\u0131d.json",
        "docs/review.\u0131nstruct\u0131ons.md",
    ],
)
@pytest.mark.parametrize("side", ["source", "destination"])
def test_authority_instruction_and_hidden_paths_are_refused(
    sandbox: Path,
    protected: str,
    side: str,
) -> None:
    root = make_root(sandbox)
    request = {"destination": DESTINATION, "source": SOURCE, side: protected}
    before = tree(root)
    result = update({"moves": [request], "root": str(root)})
    assert refusal(result) == "REFUSE_MOVE_PROTECTED"
    assert result["refusal"]["details"]["path"] == protected
    assert tree(root) == before


def test_sdk_owned_inventory_paths_are_refused(sandbox: Path) -> None:
    root = make_root(sandbox)
    identity = Workspace.load(root).identity
    before = tree(root)
    owned = moves_module._integration(root, identity)[0]
    assert moves_module.fold_path(".github/skills/rapp-work-sdk/SKILL.md") in owned
    with pytest.raises(Refusal, match="REFUSE_MOVE_PROTECTED"):
        moves_module._require_unowned(".github/skills/rapp-work-sdk/SKILL.md", owned)
    assert tree(root) == before


@pytest.mark.parametrize(
    "source",
    ["rappid.json", "SPEC.md", "agents/CLAUDE.md", "agents/basic_agent.py"],
)
def test_a_source_that_is_another_name_of_a_protected_file_is_refused(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    """Filesystem aliases the lexical rule cannot foresee are caught by file identity."""
    root = make_root(sandbox)
    (root / "agents/CLAUDE.md").write_bytes(b"# agent instructions\n")
    (root / "agents/basic_agent.py").write_bytes(b"class BasicAgent:\n    pass\n")
    monkeypatch.setattr(plans_module, "move_path_protection", lambda path: None)
    before = tree(root)
    result = update({"moves": moves((source, "agents/experimental/copy.md")), "root": str(root)})
    assert refusal(result) == "REFUSE_MOVE_PROTECTED"
    assert result["refusal"]["details"]["reason"] == "protected-file-alias"
    assert tree(root) == before


def test_a_resumed_source_that_became_a_protected_alias_is_refused(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    monkeypatch.setattr(moves_module, "_flip", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    source = (root / SOURCE).lstat()
    real = moves_module._protected_identities
    monkeypatch.setattr(
        moves_module,
        "_protected_identities",
        lambda *arguments: real(*arguments) | {(source.st_dev, source.st_ino)},
    )
    before = tree(root)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_MOVE_PROTECTED"
    assert refused["refusal"]["details"]["reason"] == "protected-file-alias"
    assert refused["refusal"]["details"]["recovery"] == "pending"
    assert tree(root) == before


def test_a_destination_that_becomes_a_protected_name_is_undone(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    monkeypatch.setattr(plans_module, "move_path_protection", lambda path: None)
    planned = plan_moves(root, (SOURCE, "agents/CLAUDE.md"))
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_MOVE_PROTECTED"
    details = refused["refusal"]["details"]
    assert (details["reason"], details["undone"], details["recovery"]) == (
        "protected-name-alias",
        True,
        "none",
    )
    assert (root / SOURCE).read_bytes() == AGENT
    assert not (root / "agents/CLAUDE.md").exists()
    assert not (root / MARKER).exists()


@pytest.mark.parametrize(
    ("marker", "side"),
    [("rappid.json", "into"), (".git", "into"), ("rappid.json", "out")],
)
def test_nested_identity_or_repository_roots_are_boundaries(
    sandbox: Path,
    marker: str,
    side: str,
) -> None:
    root = make_root(sandbox)
    nested = root / "agents/nested"
    nested.mkdir()
    (nested / marker).write_bytes(b"{}")
    if side == "into":
        request = (SOURCE, "agents/nested/example_agent.py")
    else:
        (nested / "inner_agent.py").write_bytes(AGENT)
        request = ("agents/nested/inner_agent.py", "agents/inner_agent.py")
    before = tree(root)
    assert refusal(update({"moves": moves(request), "root": str(root)})) == "REFUSE_MOVE_BOUNDARY"
    assert tree(root) == before


@pytest.mark.parametrize(
    "destination",
    ["agents/new-folder/example_agent.py", "agents/example_agent.py/inner.py"],
)
def test_moves_never_create_directories(sandbox: Path, destination: str) -> None:
    root = make_root(sandbox)
    before = tree(root)
    result = update({"moves": moves((SOURCE, destination)), "root": str(root)})
    assert refusal(result) == "REFUSE_MOVE_PARENT"
    assert tree(root) == before
    assert not (root / "agents/new-folder").exists()


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ([], "REFUSE_INPUT_SHAPE"),
        ("agents/example_agent.py", "REFUSE_INPUT_SHAPE"),
        (moves(*[(f"a{index}.md", f"b{index}.md") for index in range(65)]), "REFUSE_INPUT_SHAPE"),
        ([{"destination": DESTINATION, "extra": 1, "source": SOURCE}], "REFUSE_INPUT_KEYS"),
        ([{"source": SOURCE}], "REFUSE_INPUT_KEYS"),
        (moves((SOURCE, "a.md"), (SOURCE, "b.md")), "REFUSE_MOVE_PLAN"),
        (moves(("a.md", DESTINATION), ("b.md", DESTINATION)), "REFUSE_MOVE_PLAN"),
        (moves(("a.md", "b.md"), ("b.md", "c.md")), "REFUSE_MOVE_PLAN"),
        (moves(("a.md", "b.md"), ("b.md", "a.md")), "REFUSE_MOVE_PLAN"),
        (moves(("agents/Example_agent.py", "x.md"), (SOURCE, "y.md")), "REFUSE_MOVE_PLAN"),
        (moves((SOURCE, SOURCE)), "REFUSE_MOVE_PLAN"),
        (moves((SOURCE, "agents/Example_agent.py")), "REFUSE_MOVE_PLAN"),
        (moves(("notes/a\u0131.md", "x.md"), ("notes/ai.md", "y.md")), "REFUSE_MOVE_PLAN"),
        (moves(("notes/stra\u00dfe.md", "notes/STRASSE.md")), "REFUSE_MOVE_PLAN"),
    ],
)
def test_move_requests_are_closed_bounded_and_disjoint(
    sandbox: Path,
    value: Any,
    code: str,
) -> None:
    root = make_root(sandbox)
    before = tree(root)
    assert refusal(update({"moves": value, "root": str(root)})) == code
    assert tree(root) == before


def test_move_inputs_stay_inside_the_closed_update_operation(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    both = update(
        {"inverse_of": planned["plan"], "moves": moves((SOURCE, DESTINATION)), "root": str(root)}
    )
    assert refusal(both) == "REFUSE_INPUT_SHAPE"
    for extra in ({"moves": moves((SOURCE, DESTINATION))}, {"inverse_of": planned["plan"]}):
        refused = update(
            {
                **extra,
                "apply": True,
                "plan": planned["plan"],
                "plan_sha256": planned["plan_sha256"],
                "root": str(root),
            }
        )
        assert refusal(refused) == "REFUSE_INPUT_SHAPE"
    unknown = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root), "rename": True})
    assert refusal(unknown) == "REFUSE_INPUT_KEYS"
    for operation in (scaffold, verify, status, migrate, discover):
        assert refusal(operation({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})) == (
            "REFUSE_INPUT_KEYS"
        )
    assert tree(root) == before


def test_move_plan_parser_is_closed_and_old_parsers_fail_closed(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    plan = planned["plan"]
    assert MovePlan.from_dict(plan).to_dict() == plan
    with pytest.raises(Refusal, match="REFUSE_INPUT_KEYS"):
        ReleasePlan.from_dict(plan)
    with pytest.raises(Refusal, match="REFUSE_INPUT_KEYS"):
        MovePlan.from_dict({**plan, "actions": []})
    with pytest.raises(Refusal, match="REFUSE_MOVE_PLAN"):
        MovePlan.from_dict({**plan, "schema": "rapp-work-release-plan/1"})
    with pytest.raises(Refusal, match="REFUSE_MOVE_PLAN"):
        MovePlan.from_dict({**plan, "network": True})
    with pytest.raises(Refusal, match="REFUSE_MOVE_PLAN"):
        MovePlan.from_dict({**plan, "moves": []})
    floating = json.loads(json.dumps(plan))
    floating["moves"][0]["bytes"] = float(len(AGENT))
    with pytest.raises(Refusal, match="REFUSE_MOVE_PLAN"):
        MovePlan.from_dict(floating)
    protected = json.loads(json.dumps(plan))
    protected["moves"][0]["destination"] = "CLAUDE.md"
    with pytest.raises(Refusal, match="REFUSE_MOVE_PROTECTED"):
        MovePlan.from_dict(protected)
    unsorted = json.loads(json.dumps(plan))
    unsorted["moves"] = [
        {**unsorted["moves"][0], "source": "b.md", "destination": "c.md"},
        {**unsorted["moves"][0], "source": "a.md", "destination": "d.md"},
    ]
    with pytest.raises(Refusal, match="REFUSE_MOVE_PLAN"):
        MovePlan.from_dict(unsorted)
    release = ReleasePlan(
        operation="update",
        target=str(root),
        subject={},
        actions=(FileAction("create", "notes.md", b"x"),),
        preconditions=(),
    )
    with pytest.raises(Refusal, match="REFUSE_INPUT_KEYS"):
        MovePlan.from_dict(release.to_dict())


def test_forged_rehashed_plan_is_refused_by_the_replay(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    forged = json.loads(json.dumps(planned["plan"]))
    forged["moves"][0]["sha256"] = "0" * 64
    forged_sha256 = MovePlan.from_dict(forged).sha256
    before = tree(root)
    refused = update(
        {"apply": True, "plan": forged, "plan_sha256": forged_sha256, "root": str(root)}
    )
    assert refusal(refused) == "REFUSE_PRECONDITION"
    assert tree(root) == before
    assert not (root / MARKER).exists()


def test_inverse_round_trips_the_exact_tree(sandbox: Path) -> None:
    root = make_root(sandbox)
    (root / "notes").mkdir()
    (root / "archive").mkdir()
    (root / "notes/plan.md").write_bytes(NOTE)
    (root / "notes/plan.md").chmod(0o640)
    (root / "agents/experimental/draft_agent.py").write_bytes(b"# draft\n")
    original = tree(root)
    planned = plan_moves(
        root,
        (SOURCE, DESTINATION),
        ("notes/plan.md", "archive/plan.md"),
        ("agents/experimental/draft_agent.py", "agents/draft_agent.py"),
    )
    assert [move["source"] for move in planned["plan"]["moves"]] == [
        "agents/example_agent.py",
        "agents/experimental/draft_agent.py",
        "notes/plan.md",
    ]
    undo = inverse(root, planned)
    assert undo["effects"] is False
    assert tree(root) == original
    assert undo["plan_sha256"] != planned["plan_sha256"]
    assert undo["plan_sha256"] == sha256(canonical_bytes(undo["plan"]))
    assert {
        (move["source"], move["destination"], move["sha256"], move["bytes"], move["mode"])
        for move in undo["plan"]["moves"]
    } == {
        (move["destination"], move["source"], move["sha256"], move["bytes"], move["mode"])
        for move in planned["plan"]["moves"]
    }
    assert inverse(root, undo)["plan"] == planned["plan"]
    assert MovePlan.from_dict(undo["plan"]).inverse().sha256 == planned["plan_sha256"]

    assert apply(root, planned)["status"] == "applied"
    assert tree(root) != original
    assert refusal(apply(root, undo, plan_sha256=planned["plan_sha256"])) == "REFUSE_PLAN_HASH"
    restored = apply(root, undo)
    assert restored["status"] == "applied"
    assert restored["result"]["plan_sha256"] == undo["plan_sha256"]
    assert tree(root) == original


def test_inverse_is_plan_only_and_bound_to_its_root(sandbox: Path) -> None:
    root = make_root(sandbox)
    other = sandbox / "other"
    other.mkdir()
    planned = plan_moves(root, (SOURCE, DESTINATION))
    undo = inverse(root, planned)
    before = tree(root)
    assert refusal(apply(root, undo)) == "REFUSE_PLAN_APPLIED"
    assert tree(root) == before
    workspace_plan = dict(planned["plan"])
    workspace_plan["target"] = str(other)
    assert refusal(update({"inverse_of": workspace_plan, "root": str(root)})) == "REFUSE_PLAN_TARGET"
    assert tree(root) == before


def test_replaying_an_applied_plan_is_refused_and_redo_follows_undo(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    undo = inverse(root, planned)
    assert apply(root, planned)["status"] == "applied"
    after = tree(root)
    replay = apply(root, planned)
    assert refusal(replay) == "REFUSE_PLAN_APPLIED"
    assert tree(root) == after
    assert not (root / MARKER).exists()
    assert apply(root, undo)["status"] == "applied"
    assert refusal(apply(root, undo)) == "REFUSE_PLAN_APPLIED"
    redo = apply(root, planned)
    assert redo["status"] == "applied"
    assert tree(root) == after


def test_a_pending_move_blocks_other_moves_but_not_the_sdk_update(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    (root / "notes").mkdir()
    (root / "notes/plan.md").write_bytes(NOTE)
    source_inode = (root / SOURCE).stat().st_ino
    planned = plan_moves(root, (SOURCE, DESTINATION))
    other = plan_moves(root, ("notes/plan.md", "agents/plan.md"))
    monkeypatch.setattr(moves_module, "_arrival_problem", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()

    assert not (root / SOURCE).exists()
    assert (root / DESTINATION).read_bytes() == AGENT
    marker = (root / MARKER).read_bytes()
    assert marker == canonical_bytes(
        {
            "plan": planned["plan"],
            "plan_sha256": planned["plan_sha256"],
            "schema": "rapp-work-move-recovery/1",
        }
    )
    assert stat.S_IMODE((root / MARKER).stat().st_mode) == 0o600
    interrupted = tree(root)
    assert verify({"root": str(root)})["status"] == "ok"
    pending = update({"moves": moves(("notes/plan.md", "agents/plan.md")), "root": str(root)})
    assert refusal(pending) == "REFUSE_RECOVERY_PENDING"
    assert pending["refusal"]["details"]["plan_sha256"] == planned["plan_sha256"]
    undo_pending = update({"inverse_of": other["plan"], "root": str(root)})
    assert refusal(undo_pending) == "REFUSE_RECOVERY_PENDING"
    assert refusal(apply(root, other)) == "REFUSE_RECOVERY_BINDING"
    sdk_update = update({"root": str(root)})
    assert sdk_update["result"]["plan"]["actions"] == []
    assert apply(root, sdk_update["result"])["result"]["status"] == "unchanged"
    assert tree(root) == interrupted

    resumed = apply(root, planned)
    assert resumed["status"] == "applied"
    assert resumed["result"]["recovered"] is True
    assert not (root / SOURCE).exists()
    moved = (root / DESTINATION).lstat()
    assert (moved.st_ino, moved.st_nlink) == (source_inode, 1)
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / MARKER).exists()


@pytest.mark.parametrize(
    "row",
    ["before-flip", "after-flip", "during-undo", "before-marker-removal"],
)
def test_crash_matrix_rows_resume_or_refuse_exactly(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    row: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    if row == "before-flip":
        monkeypatch.setattr(moves_module, "_flip", crash)
    elif row == "after-flip":
        monkeypatch.setattr(moves_module, "_arrival_problem", crash)
    elif row == "during-undo":
        hook_flip(monkeypatch, before=lambda: atomic_save(root / SOURCE, VERSION_2))
        monkeypatch.setattr(moves_module, "_undo", crash)
    else:
        monkeypatch.setattr(moves_module, "_remove_marker", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    assert (root / MARKER).is_file()
    interrupted = tree(root)
    if row == "during-undo":
        assert not (root / SOURCE).exists()
        assert (root / DESTINATION).read_bytes() == VERSION_2
        refused = apply(root, planned)
        assert refusal(refused) == "REFUSE_RECOVERY_STATE"
        assert refused["refusal"]["details"]["recovery"] == "pending"
        assert tree(root) == interrupted
        return
    if row == "before-flip":
        assert (root / SOURCE).read_bytes() == AGENT
        assert not (root / DESTINATION).exists()
    else:
        assert not (root / SOURCE).exists()
        assert (root / DESTINATION).read_bytes() == AGENT
    resumed = apply(root, planned)
    assert resumed["status"] == "applied"
    assert resumed["result"]["recovered"] is True
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / SOURCE).exists()
    assert not (root / MARKER).exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "edited",
        "same-size-edit",
        "second-link",
        "source-reappears",
        "both-missing",
        "source-edited-before-flip",
        "destination-appears-before-flip",
    ],
)
def test_ambiguous_interrupted_state_is_refused_and_left_in_place(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    seam = "_flip" if tamper.endswith("before-flip") else "_arrival_problem"
    monkeypatch.setattr(moves_module, seam, crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    if tamper == "edited":
        with (root / DESTINATION).open("ab") as stream:
            stream.write(b"# owner edit\n")
    elif tamper == "same-size-edit":
        with (root / DESTINATION).open("r+b") as stream:
            stream.write(AGENT.upper())
    elif tamper == "second-link":
        os.link(root / DESTINATION, root / "agents/copy_agent.py")
    elif tamper == "source-reappears":
        (root / SOURCE).write_bytes(AGENT)
        (root / SOURCE).chmod(0o644)
    elif tamper == "both-missing":
        (root / DESTINATION).unlink()
    elif tamper == "source-edited-before-flip":
        with (root / SOURCE).open("r+b") as stream:
            stream.write(AGENT.upper())
    else:
        (root / DESTINATION).write_bytes(b"winner")
    before = tree(root)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_RECOVERY_STATE"
    assert refused["refusal"]["details"]["recovery"] == "pending"
    assert tree(root) == before
    assert (root / MARKER).is_file()


def test_an_identical_replacement_after_the_flip_counts_as_moved(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    monkeypatch.setattr(moves_module, "_arrival_problem", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    (root / DESTINATION).unlink()
    (root / DESTINATION).write_bytes(AGENT)
    (root / DESTINATION).chmod(0o644)
    resumed = apply(root, planned)
    assert resumed["status"] == "applied"
    assert resumed["result"]["recovered"] is True
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / MARKER).exists()


@pytest.mark.parametrize("finish", ["removed", "replaced"])
def test_a_stale_resume_never_runs_beside_a_newer_apply(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    finish: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    marker = root / MARKER
    marker.write_bytes(
        canonical_bytes(
            {
                "plan": planned["plan"],
                "plan_sha256": planned["plan_sha256"],
                "schema": "rapp-work-move-recovery/1",
            }
        )
    )
    marker.chmod(0o600)
    real = moves_module._flock

    def the_holder_finishes_first(descriptor: int, *, blocking: bool) -> None:
        marker.unlink()
        if finish == "replaced":
            marker.write_bytes(b"a newer apply's marker")
        real(descriptor, blocking=blocking)

    monkeypatch.setattr(moves_module, "_flock", the_holder_finishes_first)
    before = {path: entry for path, entry in tree(root).items() if path != MARKER}
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_RECOVERY_BUSY"
    assert {path: entry for path, entry in tree(root).items() if path != MARKER} == before
    assert (root / SOURCE).read_bytes() == AGENT
    assert not (root / DESTINATION).exists()
    if finish == "replaced":
        assert marker.read_bytes() == b"a newer apply's marker"
    else:
        assert not marker.exists()


def test_a_second_apply_is_refused_while_another_holds_the_marker(sandbox: Path) -> None:
    import fcntl

    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    marker = root / MARKER
    marker.write_bytes(
        canonical_bytes(
            {
                "plan": planned["plan"],
                "plan_sha256": planned["plan_sha256"],
                "schema": "rapp-work-move-recovery/1",
            }
        )
    )
    marker.chmod(0o600)
    before = tree(root)
    with marker.open("rb") as holder:
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        busy = apply(root, planned)
        assert refusal(busy) == "REFUSE_RECOVERY_BUSY"
        assert tree(root) == before
    resumed = apply(root, planned)
    assert resumed["status"] == "applied"
    assert resumed["result"]["recovered"] is True
    assert not marker.exists()


def test_marker_creation_failure_leaves_nothing_behind(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import fcntl

    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)

    def unavailable(*_: Any) -> None:
        raise OSError(errno.ENOLCK, os.strerror(errno.ENOLCK))

    monkeypatch.setattr(fcntl, "flock", unavailable)
    assert refusal(apply(root, planned)) == "REFUSE_PLATFORM"
    assert tree(root) == before
    assert not (root / MARKER).exists()


def test_racing_first_applies_never_share_a_marker(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    (root / MARKER).write_bytes(b"another apply")
    before = tree(root)
    monkeypatch.setattr(moves_module, "_present", lambda path: False)
    monkeypatch.setattr(moves_module, "_marker_present", lambda directory: False)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_RECOVERY_PENDING"
    assert tree(root) == before
    assert (root / MARKER).read_bytes() == b"another apply"


@pytest.mark.parametrize("death", ["process-death", "interrupted"])
def test_the_marker_appears_complete_or_not_at_all(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    death: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    real_fsync = os.fsync
    calls: list[int] = []

    def die_while_the_marker_is_written(descriptor: int) -> None:
        calls.append(descriptor)
        if len(calls) == 1:
            raise SimulatedCrash
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", die_while_the_marker_is_written)
    if death == "process-death":
        monkeypatch.setattr(moves_module, "_discard_own", lambda *_: None)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    assert not (root / MARKER).exists()
    strays = [
        path.name
        for path in (root / ".rapp-work").iterdir()
        if path.name.startswith(".move-recovery-")
    ]
    if death == "interrupted":
        assert strays == []
        assert tree(root) == before
    else:
        assert len(strays) == 1
        assert strays[0].endswith(".tmp")
        assert verify({"root": str(root)})["status"] == "ok"
    applied = apply(root, planned)
    assert applied["status"] == "applied"
    assert applied["result"]["recovered"] is False
    assert (root / DESTINATION).read_bytes() == AGENT
    for name in strays:
        assert (root / ".rapp-work" / name).is_file()


def test_a_marker_replaced_during_apply_is_never_removed(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    foreign = b"another program's file at the marker path"

    def replace_the_marker() -> None:
        stand_in = root / ".rapp-work/stand-in"
        stand_in.write_bytes(foreign)
        os.rename(stand_in, root / MARKER)

    hook_flip(monkeypatch, before=replace_the_marker)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_RECOVERY_BINDING"
    assert (root / MARKER).read_bytes() == foreign
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / SOURCE).exists()


def test_foreign_or_forged_marker_is_never_repaired(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    (root / MARKER).write_bytes(canonical_bytes({"schema": "rapp-work-move-recovery/1"}))
    before = tree(root)
    assert refusal(apply(root, planned)) == "REFUSE_RECOVERY_BINDING"
    assert tree(root) == before
    pending = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert refusal(pending) == "REFUSE_RECOVERY_PENDING"


def test_partial_multi_move_failure_keeps_the_marker(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    (root / "notes").mkdir()
    (root / "notes/plan.md").write_bytes(NOTE)
    planned = plan_moves(root, (SOURCE, DESTINATION), ("notes/plan.md", "agents/plan.md"))
    hook_flip(
        monkeypatch,
        before=lambda: (root / "agents/plan.md").write_bytes(b"winner"),
        name="plan.md",
    )
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_MOVE_COLLISION"
    assert refused["refusal"]["details"]["completed_moves"] == 1
    assert refused["refusal"]["details"]["recovery"] == "pending"
    monkeypatch.undo()
    assert (root / DESTINATION).read_bytes() == AGENT
    assert (root / "notes/plan.md").read_bytes() == NOTE
    assert (root / "agents/plan.md").read_bytes() == b"winner"
    assert (root / MARKER).is_file()
    assert refusal(apply(root, planned)) == "REFUSE_RECOVERY_STATE"


@pytest.mark.parametrize(
    ("number", "code"),
    [
        (errno.EXDEV, "REFUSE_MOVE_CROSS_DEVICE"),
        (errno.EINVAL, "REFUSE_PLATFORM"),
        (errno.ENOTSUP, "REFUSE_PLATFORM"),
        (errno.ENOENT, "REFUSE_PRECONDITION"),
        (errno.EACCES, "REFUSE_PATH_UNSAFE"),
    ],
)
def test_rename_errors_are_refused_without_effects(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    number: int,
    code: str,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    real = moves_module._rename_exclusive

    def failing(directory: int, source: str, target_directory: int, target: str) -> None:
        if target == moves_module.MOVE_RECOVERY_NAME:
            real(directory, source, target_directory, target)
            return
        raise OSError(number, os.strerror(number))

    monkeypatch.setattr(moves_module, "_rename_exclusive", failing)
    refused = apply(root, planned)
    assert refusal(refused) == code
    assert refused["refusal"]["details"]["recovery"] == "none"
    assert tree(root) == before
    assert not (root / MARKER).exists()


def test_a_filesystem_without_exclusive_rename_refuses_before_any_move(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)

    def unsupported(*_: Any) -> None:
        raise OSError(errno.ENOTSUP, os.strerror(errno.ENOTSUP))

    monkeypatch.setattr(moves_module, "_rename_exclusive", unsupported)
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_PLATFORM"
    assert tree(root) == before


def test_a_platform_without_a_no_replace_rename_refuses_moves(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    before = tree(root)
    monkeypatch.setattr(moves_module, "_exclusive_rename", lambda: None)
    for result in (
        update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)}),
        update({"inverse_of": planned["plan"], "root": str(root)}),
        apply(root, planned),
    ):
        assert refusal(result) == "REFUSE_PLATFORM"
    assert tree(root) == before


def test_parent_on_another_device_is_refused_at_planning(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    real = moves_module._root_device
    monkeypatch.setattr(moves_module, "_root_device", lambda path: real(path) + 1)
    result = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert refusal(result) == "REFUSE_MOVE_CROSS_DEVICE"


def test_legacy_workspace_first_adopts_the_sdk(sandbox: Path) -> None:
    root = sandbox / "legacy"
    root.mkdir(mode=0o700)
    identity = canonical_bytes(
        {
            "kind": "workspace",
            "mode": "solo",
            "name": "legacy",
            "rappid": mint_rappid("example", "legacy"),
            "schema": "rapp/1",
            "workspace_spec": "rapp-workspace/2.0",
            "world_id": "example-world",
        }
    )
    (root / "rappid.json").write_bytes(identity)
    (root / "agents/experimental").mkdir(parents=True)
    (root / SOURCE).write_bytes(AGENT)
    before = tree(root)
    refused = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert refusal(refused) == "REFUSE_SDK_PROFILE"
    assert tree(root) == before
    adopted = update({"root": str(root)})
    assert apply(root, adopted["result"])["status"] == "applied"
    planned = plan_moves(root, (SOURCE, DESTINATION))
    assert apply(root, planned)["status"] == "applied"
    assert (root / "rappid.json").read_bytes() == identity
    assert (root / DESTINATION).read_bytes() == AGENT


def test_stale_sdk_integration_must_update_first(sandbox: Path) -> None:
    root = make_root(sandbox)
    sdk_path = root / ".rapp-work/sdk.json"
    sdk = strict_json_loads(sdk_path.read_bytes())
    stale = canonical_bytes({**sdk, "sdk_version": "0.9.0"})
    sdk_path.write_bytes(stale)
    managed_path = root / ".rapp-work/managed.json"
    managed = strict_json_loads(managed_path.read_bytes())
    for entry in managed["files"]:
        if entry["path"] == ".rapp-work/sdk.json":
            entry.update({"bytes": len(stale), "sha256": sha256(stale)})
    managed_path.write_bytes(canonical_bytes(managed))
    before = tree(root)
    refused = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    assert refusal(refused) == "REFUSE_SDK_PROFILE"
    assert tree(root) == before
    refreshed = update({"root": str(root)})
    assert refreshed["result"]["plan"]["schema"] == "rapp-work-release-plan/1"
    assert apply(root, refreshed["result"])["status"] == "applied"
    assert apply(root, plan_moves(root, (SOURCE, DESTINATION)))["status"] == "applied"


def test_an_sdk_upgrade_during_a_pending_move_never_deadlocks(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    monkeypatch.setattr(moves_module, "_flip", crash)
    with pytest.raises(SimulatedCrash):
        apply(root, planned)
    monkeypatch.undo()
    marker = (root / MARKER).read_bytes()
    monkeypatch.setattr(workspace_module, "SDK_VERSION", "1.0.1")
    refused = apply(root, planned)
    assert refusal(refused) == "REFUSE_SDK_PROFILE"
    assert "may run while a move is pending" in refused["refusal"]["message"]
    refresh = update({"root": str(root)})
    assert [action["path"] for action in refresh["result"]["plan"]["actions"]] == [
        ".rapp-work/managed.json",
        ".rapp-work/sdk.json",
    ]
    assert apply(root, refresh["result"])["result"]["status"] == "updated"
    assert (root / MARKER).read_bytes() == marker
    assert (root / SOURCE).read_bytes() == AGENT
    resumed = apply(root, planned)
    assert resumed["status"] == "applied"
    assert resumed["result"]["recovered"] is True
    assert resumed["result"]["verification"]["status"] == "verified"
    assert (root / DESTINATION).read_bytes() == AGENT
    assert not (root / MARKER).exists()


def test_a_stored_undo_survives_an_sdk_update(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_root(sandbox)
    source = (root / SOURCE).lstat()
    planned = plan_moves(root, (SOURCE, DESTINATION))
    undo = inverse(root, planned)
    assert apply(root, planned)["status"] == "applied"
    monkeypatch.setattr(workspace_module, "SDK_VERSION", "1.0.1")
    assert refusal(apply(root, undo)) == "REFUSE_SDK_PROFILE"
    refresh = update({"root": str(root)})
    assert apply(root, refresh["result"])["result"]["status"] == "updated"
    restored = apply(root, undo)
    assert restored["status"] == "applied"
    back = (root / SOURCE).lstat()
    assert (back.st_ino, stat.S_IMODE(back.st_mode), back.st_nlink) == (source.st_ino, 0o644, 1)
    assert (root / SOURCE).read_bytes() == AGENT
    assert not (root / DESTINATION).exists()


def test_pending_update_recovery_blocks_moves(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = plan_moves(root, (SOURCE, DESTINATION))
    (root / ".rapp-work/update-recovery.json").write_bytes(b"{}")
    before = tree(root)
    assert refusal(update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})) == (
        "REFUSE_RECOVERY_PENDING"
    )
    assert refusal(apply(root, planned)) == "REFUSE_RECOVERY_PENDING"
    assert tree(root) == before


def test_organization_moves_never_touch_pointers(sandbox: Path) -> None:
    organization_root = make_root(sandbox, kind="organization")
    workspace_root = make_root(sandbox)
    organization = Organization.load(organization_root)
    registration = organization.plan_register(Workspace.load(workspace_root))
    organization.apply_register(
        Workspace.load(workspace_root),
        registration,
        plan_sha256=registration.sha256,
    )
    pointers = (organization_root / "workspaces.json").read_bytes()
    (organization_root / "docs").mkdir()
    (organization_root / "archive").mkdir()
    (organization_root / "docs/charter.md").write_bytes(NOTE)
    planned = plan_moves(organization_root, ("docs/charter.md", "archive/charter.md"))
    assert planned["plan"]["subject"]["kind"] == "organization"
    applied = apply(organization_root, planned)
    assert applied["status"] == "applied"
    assert applied["result"]["verification"]["pointers"] == 1
    assert (organization_root / "workspaces.json").read_bytes() == pointers
    assert (organization_root / "archive/charter.md").read_bytes() == NOTE
    refused = update(
        {
            "moves": moves(("workspaces.json", "archive/workspaces.json")),
            "root": str(organization_root),
        }
    )
    assert refusal(refused) == "REFUSE_MOVE_PROTECTED"


def test_default_update_still_plans_release_plan_v1(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = update({"root": str(root)})
    assert planned["status"] == "planned"
    assert planned["result"]["plan"]["schema"] == "rapp-work-release-plan/1"
    assert planned["result"]["plan"]["actions"] == []
    assert ReleasePlan.from_dict(planned["result"]["plan"]).sha256 == planned["result"]["plan_sha256"]


def test_release_plan_v1_hash_vector_is_unchanged() -> None:
    plan = ReleasePlan(
        operation="update",
        target="/example/workspace",
        subject={
            "kind": "workspace",
            "rappid": "rappid:@example/finance:" + "a" * 64,
            "sdk_version": "1.0.0",
            "world_id": "example-world",
        },
        actions=(
            FileAction("replace", ".rapp-work/managed.json", b"[]\n", 0o600, "b" * 64),
            FileAction("create", ".rapp-work/sdk.json", b"{}\n", 0o600),
        ),
        preconditions=(
            {
                "identity_sha256": "c" * 64,
                "managed_files": [],
                "managed_sha256": None,
                "root_identity": {"device": 1, "inode": 2, "mode": 448},
            },
        ),
    )
    assert plan.sha256 == V1_PLAN_SHA256
    assert ReleasePlan.from_dict(plan.to_dict()).sha256 == V1_PLAN_SHA256


def test_move_plan_conformance_vector() -> None:
    plan = MovePlan(
        target="/example/workspace",
        subject={
            "kind": "workspace",
            "rappid": "rappid:@example/finance:" + "a" * 64,
            "world_id": "example-world",
        },
        preconditions={
            "identity_sha256": "c" * 64,
            "root_identity": {"device": 1, "inode": 2, "mode": 448},
        },
        moves=(
            FileMove(SOURCE, DESTINATION, "e" * 64, 42, 0o644),
            FileMove(
                "agents/experimental/notes_agent.py",
                "agents/notes_agent.py",
                "f" * 64,
                7,
                0o600,
            ),
        ),
    )
    assert plan.sha256 == MOVE_PLAN_SHA256
    assert plan.inverse().sha256 == INVERSE_PLAN_SHA256
    assert plan.inverse().inverse().to_dict() == plan.to_dict()
    raw = canonical_bytes(plan.to_dict())
    assert sha256(raw) == MOVE_PLAN_SHA256
    assert raw.startswith(b'{"moves":[{"bytes":42,"destination":"agents/experimental/')
    assert b'"preconditions":{"identity_sha256":"' + b"c" * 64 + b'","root_identity":' in raw
    assert MovePlan.from_dict(strict_json_loads(raw)).sha256 == MOVE_PLAN_SHA256
    with pytest.raises(Refusal, match="REFUSE_INPUT_KEYS"):
        MovePlan.from_dict(
            {
                **plan.to_dict(),
                "preconditions": {**plan.to_dict()["preconditions"], "managed_sha256": "d" * 64},
            }
        )
    assert [move["source"] for move in plan.inverse().to_dict()["moves"]] == [
        DESTINATION,
        "agents/notes_agent.py",
    ]


def test_move_envelopes_are_canonical_without_floats(sandbox: Path) -> None:
    root = make_root(sandbox)
    planned = update({"moves": moves((SOURCE, DESTINATION)), "root": str(root)})
    applied = apply(root, planned["result"])
    refused = apply(root, planned["result"])
    for envelope in (planned, applied, refused):
        text = canonical_text(envelope)
        assert strict_json_loads(text) == envelope
        assert not contains_float(envelope)


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(ROOT / "src"),
    }
    return subprocess.run(
        [sys.executable, "-m", "rapp_work", *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_move_plan_inverse_and_exact_apply(sandbox: Path) -> None:
    root = make_root(sandbox)
    original = tree(root)
    planned = run_cli("update", "--root", str(root), "--move", SOURCE, DESTINATION)
    assert planned.returncode == 0, planned.stdout
    envelope = json.loads(planned.stdout)
    assert planned.stdout == canonical_text(envelope) + "\n"
    assert envelope["status"] == "planned"
    plan_file = sandbox / "move-plan.json"
    plan_file.write_text(planned.stdout, encoding="utf-8")
    undone = run_cli("update", "--root", str(root), "--inverse-of", str(plan_file))
    assert undone.returncode == 0, undone.stdout
    undo_file = sandbox / "undo-plan.json"
    undo_file.write_text(undone.stdout, encoding="utf-8")
    mixed = run_cli(
        "update",
        "--root",
        str(root),
        "--move",
        SOURCE,
        DESTINATION,
        "--apply",
        "--plan",
        str(plan_file),
        "--plan-sha256",
        envelope["result"]["plan_sha256"],
    )
    assert mixed.returncode == 2
    assert json.loads(mixed.stdout)["refusal"]["code"] == "REFUSE_INPUT_SHAPE"
    applied = run_cli(
        "update",
        "--root",
        str(root),
        "--apply",
        "--plan",
        str(plan_file),
        "--plan-sha256",
        envelope["result"]["plan_sha256"],
    )
    assert applied.returncode == 0, applied.stdout
    assert json.loads(applied.stdout)["result"]["status"] == "moved"
    restored = run_cli(
        "update",
        "--root",
        str(root),
        "--apply",
        "--plan",
        str(undo_file),
        "--plan-sha256",
        json.loads(undone.stdout)["result"]["plan_sha256"],
    )
    assert restored.returncode == 0, restored.stdout
    assert tree(root) == original
