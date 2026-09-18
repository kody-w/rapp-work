from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

import rapp_work.compat as compatibility
from rapp_work.compat import (
    private_hive,
    private_hive_prepare,
    run_private_hive_cli,
    workspace_manager,
)
from rapp_work.errors import Refusal


def write_channels(path: Path, kind: str, *, channel_id: str = "selected") -> None:
    channel = {"id": channel_id, "kind": kind, "role": "authority"}
    if kind == "filesystem":
        channel["path"] = str(path.parent / "publication")
    else:
        channel.update(
            {
                "actor_id": 3,
                "actor_login": "example",
                "owner_id": 2,
                "ref": "refs/heads/main",
                "repository": "example/private",
                "repository_id": 1,
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema": "rapp-private-hive-channels/1",
                "channels": [channel],
            }
        )
    )


def refuse_before_load(monkeypatch: pytest.MonkeyPatch, argv: list[str], code: str) -> None:
    def unexpected_load() -> None:
        raise AssertionError("compatibility implementation loaded before the network gate")

    monkeypatch.setattr(compatibility, "private_hive_cli_module", unexpected_load)
    with pytest.deprecated_call(), pytest.raises(Refusal, match=code):
        run_private_hive_cli(argv)


def test_workspace_manager_and_private_hive_are_sdk_wrapped() -> None:
    with pytest.deprecated_call():
        manager = workspace_manager()
    with pytest.deprecated_call():
        preparation = private_hive_prepare()
    with pytest.deprecated_call():
        deployment = private_hive()
    assert callable(manager.create)
    assert callable(preparation.command_migrate)
    assert callable(deployment.release.status)


def test_compatibility_wrapper_refuses_network_by_default(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channels = sandbox / "github.json"
    write_channels(channels, "github")
    refuse_before_load(
        monkeypatch,
        [
            "client",
            "pull",
            "--client-dir",
            str(sandbox / "client"),
            "--channels",
            str(channels),
            "--channel-id",
            "selected",
        ],
        "REFUSE_NETWORK",
    )


def test_compatibility_network_gate_closes_equals_repeat_and_source_bypasses(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = sandbox / "local.json"
    hosted = sandbox / "hosted.json"
    write_channels(local, "filesystem")
    write_channels(hosted, "github")
    refuse_before_load(
        monkeypatch,
        [
            "client",
            "pull",
            f"--client-dir={sandbox / 'client'}",
            f"--channels={local}",
            "--channels",
            str(hosted),
            "--channel-id=selected",
        ],
        "REFUSE_NETWORK",
    )

    monkeypatch.undo()
    refuse_before_load(
        monkeypatch,
        [
            "authority",
            "import",
            f"--workspace={sandbox / 'workspace'}",
            f"--publisher-dir={sandbox / 'publisher'}",
            f"--key-dir={sandbox / 'keys'}",
            f"--channels={local}",
            "--source-channel-id=selected",
            f"--read-state-dir={sandbox / 'read'}",
            f"--anchor={sandbox / 'anchor.json'}",
            f"--expected-spki-sha256={'0' * 64}",
        ],
        "REFUSE_NETWORK",
    )


def test_compatibility_network_gate_rejects_abbreviations_before_load(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refuse_before_load(
        monkeypatch,
        [
            "release",
            "publish",
            f"--publisher-dir={sandbox / 'publisher'}",
            f"--key-dir={sandbox / 'keys'}",
            f"--plan-hash={'0' * 64}",
            f"--github-evi={sandbox / 'evidence.json'}",
        ],
        "REFUSE_COMPATIBILITY",
    )


def test_compatibility_network_gate_reads_release_publisher_channels(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = sandbox / "publisher"
    publisher.mkdir(mode=0o700)
    database = publisher / "state.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE metadata (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
        )
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES('config',?)",
            (
                json.dumps(
                    {
                        "channels": [{"id": "hosted", "kind": "github"}],
                    }
                ).encode(),
            ),
        )
    database.chmod(0o600)
    refuse_before_load(
        monkeypatch,
        [
            "release",
            "publish",
            f"--publisher-dir={publisher}",
            f"--key-dir={sandbox / 'keys'}",
            f"--plan-hash={'0' * 64}",
        ],
        "REFUSE_NETWORK",
    )


def test_compatibility_parser_preserves_offline_alias(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []
    module = SimpleNamespace(main=lambda argv: seen.append(argv) or 7)
    monkeypatch.setattr(compatibility, "private_hive_cli_module", lambda: module)
    argv = [
        "keys",
        "create",
        f"--key-dir={sandbox / 'keys'}",
        "--owner-label=example",
    ]
    with pytest.deprecated_call():
        assert run_private_hive_cli(argv) == 7
    assert seen == [argv]
