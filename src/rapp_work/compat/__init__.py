from __future__ import annotations

import argparse
import sqlite3
import warnings
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

from .._json import strict_json_loads
from .._paths import private_directory, read_regular
from ..errors import Refusal, require
from ._loader import (
    private_hive_cli_module,
    private_hive_package,
    private_hive_prepare_module,
    workspace_manager_module,
)

__all__ = [
    "private_hive",
    "private_hive_prepare",
    "run_private_hive_cli",
    "workspace_manager",
]


def _deprecated(name: str) -> None:
    warnings.warn(
        f"{name} is a legacy compatibility surface; prefer the typed rapp_work SDK",
        DeprecationWarning,
        stacklevel=2,
    )


def workspace_manager() -> ModuleType:
    _deprecated("workspace manager")
    return workspace_manager_module()


def private_hive_prepare() -> ModuleType:
    _deprecated("Private Hive preparation")
    return private_hive_prepare_module()


def private_hive() -> ModuleType:
    _deprecated("Private Hive deployment")
    return private_hive_package()


class _NoAbbrevParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["allow_abbrev"] = False
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        raise Refusal(
            "REFUSE_COMPATIBILITY",
            "invalid legacy Private Hive CLI arguments",
            {"error": message},
        )


def _private_hive_parser() -> argparse.ArgumentParser:
    root = _NoAbbrevParser()
    root.add_argument("--preflight", action="store_true")
    groups = root.add_subparsers(dest="group")

    key = groups.add_parser("key", aliases=["keys"]).add_subparsers(
        dest="operation",
        required=True,
    )
    create = key.add_parser("create")
    create.add_argument("--key-dir", type=Path, required=True)
    create.add_argument("--owner-label", required=True)
    create.add_argument("--slug", default="owner")
    load = key.add_parser("load")
    load.add_argument("--key-dir", type=Path, required=True)
    load.add_argument("--expected-rappid", required=True)

    authority = groups.add_parser("authority").add_subparsers(
        dest="operation",
        required=True,
    )
    for name in ("init", "import"):
        command = authority.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        command.add_argument("--publisher-dir", type=Path, required=True)
        command.add_argument("--key-dir", type=Path, required=True)
        command.add_argument("--channels", type=Path, required=True)
        command.add_argument("--adopt-prepared-owner")
        command.add_argument("--created-utc")
        if name == "import":
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument("--source", type=Path)
            source.add_argument("--source-channel-id")
            command.add_argument("--read-state-dir", type=Path)
            command.add_argument("--github-evidence", type=Path)
            command.add_argument("--github-token-file", type=Path)
            command.add_argument("--anchor", type=Path, required=True)
            command.add_argument("--expected-spki-sha256", required=True)
    anchor = authority.add_parser("anchor")
    anchor.add_argument("--publisher-dir", type=Path, required=True)
    anchor.add_argument("--out", type=Path)

    releases = groups.add_parser("release").add_subparsers(
        dest="operation",
        required=True,
    )
    for name in ("build", "show", "approve", "publish", "status", "discard"):
        command = releases.add_parser(name)
        command.add_argument("--publisher-dir", type=Path, required=True)
        if name in {"build", "approve", "publish"}:
            command.add_argument("--key-dir", type=Path, required=True)
        if name in {"show", "approve", "publish", "discard"}:
            command.add_argument("--plan-hash", required=True)
        if name == "build":
            command.add_argument("--stage-root", type=Path, required=True)
            command.add_argument("--expected-ref", action="append", default=[])
            command.add_argument("--created-utc")
        if name == "publish":
            command.add_argument("--github-evidence", type=Path)
            command.add_argument("--github-token-file", type=Path)

    clients = groups.add_parser("client").add_subparsers(
        dest="operation",
        required=True,
    )
    for name in ("init", "pull", "verify", "materialize"):
        command = clients.add_parser(name)
        command.add_argument("--client-dir", type=Path, required=True)
        if name == "init":
            command.add_argument("--anchor", type=Path, required=True)
            command.add_argument("--expected-spki-sha256", required=True)
        if name == "pull":
            command.add_argument("--channels", type=Path, required=True)
            command.add_argument("--channel-id", required=True)
            command.add_argument("--github-evidence", type=Path)
            command.add_argument("--github-token-file", type=Path)
        if name in {"materialize", "verify"}:
            command.add_argument("--destination", type=Path, required=name == "materialize")
    for name in (
        "sharepoint",
        "public-git",
        "federation",
        "seal",
        "key-release",
        "rotate-owner",
        "topology",
    ):
        command = groups.add_parser(name)
        command.add_argument("arguments", nargs=argparse.REMAINDER)
    return root


def _channels(path: Path) -> tuple[dict[str, Any], ...]:
    value = strict_json_loads(
        read_regular(path),
        where="legacy channel configuration",
    )
    require(
        isinstance(value, dict)
        and set(value) == {"schema", "channels"}
        and value.get("schema") == "rapp-private-hive-channels/1"
        and isinstance(value.get("channels"), list),
        "REFUSE_COMPATIBILITY",
        "legacy channel configuration is invalid",
    )
    result: list[dict[str, Any]] = []
    for channel in value["channels"]:
        require(
            isinstance(channel, dict) and channel.get("kind") in {"filesystem", "github"},
            "REFUSE_COMPATIBILITY",
            "legacy channel configuration contains an unsupported channel",
        )
        result.append(channel)
    return tuple(result)


def _publisher_channels(path: Path) -> tuple[dict[str, Any], ...]:
    root = private_directory(path)
    raw = read_regular(
        root / "state.sqlite3",
        limit=512 * 1024 * 1024,
        require_private=True,
    )
    database = sqlite3.connect(":memory:")
    try:
        deserialize = getattr(database, "deserialize", None)
        require(
            callable(deserialize),
            "REFUSE_PLATFORM",
            "safe in-memory inspection of legacy publisher state is unavailable",
        )
        assert callable(deserialize)
        deserialize(raw)
        database.execute("PRAGMA query_only=ON")
        row = database.execute(
            "SELECT value FROM metadata WHERE key='config'",
        ).fetchone()
        require(
            row is not None and isinstance(row[0], bytes),
            "REFUSE_COMPATIBILITY",
            "legacy publisher configuration is missing",
        )
        config = strict_json_loads(row[0], where="legacy publisher configuration")
    except sqlite3.Error as error:
        raise Refusal(
            "REFUSE_COMPATIBILITY",
            "legacy publisher state could not be inspected safely",
        ) from error
    finally:
        database.close()
    require(
        isinstance(config, dict) and isinstance(config.get("channels"), list),
        "REFUSE_COMPATIBILITY",
        "legacy publisher configuration is invalid",
    )
    channels = config["channels"]
    require(
        all(
            isinstance(channel, dict) and channel.get("kind") in {"filesystem", "github"}
            for channel in channels
        ),
        "REFUSE_COMPATIBILITY",
        "legacy publisher configuration contains an unsupported channel",
    )
    return tuple(channels)


def _network_capable(argv: list[str]) -> bool:
    require(
        isinstance(argv, list) and all(isinstance(value, str) for value in argv),
        "REFUSE_COMPATIBILITY",
        "legacy Private Hive CLI arguments must be strings",
    )
    if any(value in {"-h", "--help"} for value in argv):
        return False
    args = _private_hive_parser().parse_args(argv)
    if args.preflight:
        return False
    if args.group in {"sharepoint", "public-git", "federation"}:
        return True
    if getattr(args, "github_evidence", None) is not None:
        return True
    if getattr(args, "github_token_file", None) is not None:
        return True
    if getattr(args, "source_channel_id", None) is not None:
        return True
    if args.group == "authority" and args.operation in {"init", "import"}:
        return any(channel["kind"] == "github" for channel in _channels(args.channels))
    if args.group == "client" and args.operation == "pull":
        channels = _channels(args.channels)
        selected = [channel for channel in channels if channel.get("id") == args.channel_id]
        require(
            len(selected) == 1,
            "REFUSE_COMPATIBILITY",
            "legacy client channel selection is invalid",
        )
        return any(channel["kind"] == "github" for channel in channels)
    if args.group == "release" and args.operation == "publish":
        return any(
            channel["kind"] == "github"
            for channel in _publisher_channels(args.publisher_dir)
        )
    return False


def run_private_hive_cli(
    argv: list[str],
    *,
    allow_network: bool = False,
) -> int:
    _deprecated("Private Hive CLI")
    require(
        allow_network or not _network_capable(argv),
        "REFUSE_NETWORK",
        "legacy hosted private-Git operations require explicit allow_network",
    )
    module = private_hive_cli_module()
    return int(module.main(argv))
