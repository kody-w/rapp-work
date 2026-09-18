from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from rapp_work._json import canonical_text

ROOT = Path(__file__).resolve().parents[1]


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
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


def test_cli_emits_canonical_json_and_unknown_args_refuse() -> None:
    result = run("status", "--root", str(ROOT))
    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert result.stdout == canonical_text(value) + "\n"
    refused = run("status", "--unknown")
    assert refused.returncode == 2
    value = json.loads(refused.stdout)
    assert value["status"] == "refused"
    assert value["refusal"]["code"] == "REFUSE_CLI_ARGUMENTS"


def test_cli_scaffold_plan_and_exact_apply(sandbox: Path) -> None:
    target = sandbox / "workspace"
    planned = run(
        "scaffold",
        "--root",
        str(target),
        "--kind",
        "workspace",
        "--owner-label",
        "example",
        "--slug",
        "cli",
        "--world-id",
        "example-world",
    )
    assert planned.returncode == 0
    envelope = json.loads(planned.stdout)
    assert envelope["status"] == "planned"
    assert not target.exists()
    plan_file = sandbox / "plan.json"
    plan_file.write_text(planned.stdout, encoding="utf-8")
    applied = run(
        "scaffold",
        "--root",
        str(target),
        "--kind",
        "workspace",
        "--owner-label",
        "example",
        "--slug",
        "cli",
        "--world-id",
        "example-world",
        "--apply",
        "--plan",
        str(plan_file),
        "--plan-sha256",
        envelope["result"]["plan_sha256"],
    )
    assert applied.returncode == 0, applied.stdout
    assert json.loads(applied.stdout)["status"] == "applied"
    assert (target / "rappid.json").is_file()


def test_cli_plan_evidence_without_apply_refuses(sandbox: Path) -> None:
    plan = sandbox / "plan.json"
    plan.write_text("{}", encoding="utf-8")
    result = run("update", "--root", str(sandbox), "--plan", str(plan))
    assert result.returncode == 2
    assert json.loads(result.stdout)["refusal"]["code"] == "REFUSE_APPLY_REQUIRED"
