from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

from ._json import canonical_text, strict_json_loads
from ._paths import read_regular
from .api import execute
from .constants import PUBLIC_OPERATIONS, SDK_VERSION
from .errors import Refusal


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise Refusal("REFUSE_CLI_ARGUMENTS", message)


def parser() -> JSONArgumentParser:
    root = JSONArgumentParser(prog="rapp-work", description="Typed offline-first RAPP Work SDK")
    root.add_argument("--version", action="store_true")
    commands = root.add_subparsers(dest="operation")

    for name in ("status", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--root", default=str(Path.cwd()))
        if name == "verify":
            command.add_argument("--require-instruction-inventory", action="store_true")

    discover = commands.add_parser("discover")
    discover.add_argument("--root", action="append", dest="roots", required=True)
    discover.add_argument("--max-entries", type=int, default=10_000)

    scaffold = commands.add_parser("scaffold")
    scaffold.add_argument("--root", required=True)
    scaffold.add_argument("--kind", choices=("workspace", "organization"), required=True)
    scaffold.add_argument("--owner-label", required=True)
    scaffold.add_argument("--slug", required=True)
    scaffold.add_argument("--world-id", required=True)
    scaffold.add_argument("--mode", choices=("solo", "hive"), default="solo")
    _apply_arguments(scaffold)

    update = commands.add_parser("update")
    update.add_argument("--root", required=True)
    _apply_arguments(update)

    migrate = commands.add_parser("migrate")
    migrate.add_argument("--source", required=True)
    migrate.add_argument("--target", required=True)
    _apply_arguments(migrate)
    return root


def _apply_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--apply", action="store_true")
    command.add_argument("--plan", type=Path)
    command.add_argument("--plan-sha256")


def _plan(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = strict_json_loads(read_regular(path), where="reviewed plan file")
    if isinstance(value, dict) and value.get("schema") == "rapp-work-result/1":
        result = value.get("result")
        if isinstance(result, dict) and isinstance(result.get("plan"), dict):
            return cast(dict[str, Any], result["plan"])
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    raise Refusal("REFUSE_PLAN", "plan file must contain a plan object or plan result envelope")


def _inputs(args: argparse.Namespace) -> dict[str, Any]:
    operation = args.operation
    if operation == "verify" and args.require_instruction_inventory:
        return {"require_instruction_inventory": True, "root": args.root}
    if operation in {"status", "verify"}:
        return {"root": args.root}
    if operation == "discover":
        return {"max_entries": args.max_entries, "roots": args.roots}
    if operation == "scaffold":
        value: dict[str, Any] = {
            "kind": args.kind,
            "mode": args.mode,
            "owner_label": args.owner_label,
            "root": args.root,
            "slug": args.slug,
            "world_id": args.world_id,
        }
    elif operation == "update":
        value = {"root": args.root}
    elif operation == "migrate":
        value = {"source": args.source, "target": args.target}
    else:
        raise Refusal(
            "REFUSE_OPERATION",
            "unknown public operation",
            {"allowed": list(PUBLIC_OPERATIONS)},
        )
    if args.apply:
        value.update(
            {
                "apply": True,
                "plan": _plan(args.plan),
                "plan_sha256": args.plan_sha256,
            }
        )
    elif args.plan is not None or args.plan_sha256 is not None:
        raise Refusal(
            "REFUSE_APPLY_REQUIRED",
            "--plan and --plan-sha256 are accepted only with --apply",
        )
    return value


def main(argv: Sequence[str] | None = None) -> int:
    operation = "cli"
    try:
        args = parser().parse_args(argv)
        if args.version:
            result = {
                "operation": "version",
                "profile": "rapp-work-sdk/1",
                "protocol": "rapp-work/1",
                "refusal": None,
                "result": {"sdk_version": SDK_VERSION},
                "schema": "rapp-work-result/1",
                "status": "ok",
            }
        else:
            if args.operation is None:
                raise Refusal(
                    "REFUSE_CLI_ARGUMENTS",
                    "choose one public operation",
                    {"allowed": list(PUBLIC_OPERATIONS)},
                )
            operation = args.operation
            result = execute(operation, _inputs(args))
    except Refusal as error:
        result = {
            "operation": operation,
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "refusal": error.as_dict(),
            "result": None,
            "schema": "rapp-work-result/1",
            "status": "refused",
        }
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        refusal = Refusal("REFUSE_RUNTIME", str(error))
        result = {
            "operation": operation,
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "refusal": refusal.as_dict(),
            "result": None,
            "schema": "rapp-work-result/1",
            "status": "refused",
        }
    sys.stdout.write(canonical_text(result) + "\n")
    return 0 if result["status"] != "refused" else 2


if __name__ == "__main__":
    raise SystemExit(main())
