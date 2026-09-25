"""Isolation tests for the RappWork agent in clean interpreters.

Each child runs with ``-I -S`` (no site-packages, no user site, no environment
paths), records every write, socket and process event through an audit hook, and
watches every non-standard-library import through a meta-path finder, the way
RAR's ``tests/test_brainstem_hotload.py`` blocks optional dependencies.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from brainstem_harness import AGENT_SOURCE, BASIC_AGENT_SHIM, ROOT

SRC = ROOT / "src"
PINNED = "git+https://github.com/kody-w/rapp-work@29ead23b21645f8d7682ee00414930ffa9ce0ca6"
STATE_ENV = "BRAINSTEM_RAPP_WORK_PATH"
CROSS_PLATFORM_STDLIB = {
    "__future__",
    "collections",
    "contextlib",
    "errno",
    "hashlib",
    "importlib",
    "json",
    "os",
    "re",
    "secrets",
    "stat",
    "sys",
    "time",
    "typing",
    "unicodedata",
}
PROCESS_OR_NETWORK = (
    "socket.",
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.posix_spawn",
    "os.spawn",
    "os.fork",
    "os.forkpty",
    "pty.spawn",
    "webbrowser.open",
    "urllib.Request",
)

CHILD = r'''
import importlib.abc
import importlib.util
import json
import os
import re
import sys
import types

sys.dont_write_bytecode = True
config = json.loads(sys.argv[1])
events = []
active = [False]
WRITE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
MUTATING = {"os.mkdir", "os.rename", "os.remove", "os.rmdir", "os.symlink", "os.link",
            "os.truncate", "os.chmod", "shutil.rmtree"}
DENIED = tuple(config["denied_events"])


def hook(event, args):
    if not active[0]:
        return
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and bool(flags & WRITE)
        )
        if writing:
            events.append(["write", str(path)])
    elif event in MUTATING:
        events.append([event, str(args[0]) if args else ""])
    elif event.startswith(DENIED):
        events.append([event, repr(args)[:160]])
        if config.get("deny"):
            raise RuntimeError("denied " + event)


sys.addaudithook(hook)
lookups = []
# "org" is the standard library's own Jython probe (copy.py on Python 3.11 and older).
allowed = set(sys.stdlib_module_names) | {"agents", "basic_agent", "org"}
allowed |= set(config.get("allow", []))


class Watch(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in allowed:
            lookups.append(fullname)
            if config.get("block"):
                raise ModuleNotFoundError("blocked " + fullname, name=fullname)
        return None


sys.meta_path.insert(0, Watch())
for entry in reversed(config.get("path", [])):
    sys.path.insert(0, entry)
os.environ.update(config.get("env", {}))
if config.get("shim"):
    namespace = {}
    exec(compile(config["shim"], "basic_agent_shim", "exec"), namespace)
    package = types.ModuleType("agents")
    package.__path__ = []
    basic = types.ModuleType("agents.basic_agent")
    basic.BasicAgent = namespace["BasicAgent"]
    package.basic_agent = basic
    sys.modules["agents"] = package
    sys.modules["agents.basic_agent"] = basic
result = {"events": events, "lookups": lookups, "outputs": [], "load_error": None}
active[0] = bool(config.get("audit_load"))
try:
    spec = importlib.util.spec_from_file_location("agent_under_test", config["agent"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except ModuleNotFoundError as error:
    result["load_error"] = "ModuleNotFoundError: " + str(error)
    print(json.dumps(result))
    raise SystemExit(0)
active[0] = True
instances = {}
latest = None
for turn, arguments in config.get("calls", []):
    if turn not in instances:
        instances[turn] = module.RappWorkAgent()
    arguments = {k: (latest if v == "$PLAN" else v) for k, v in arguments.items()}
    output = instances[turn].perform(**arguments)
    if not isinstance(output, str):
        output = "NOT A STRING: " + repr(output)
    match = re.search(r"^Plan SHA-256 \(full\): ([0-9a-f]{64})$", output, re.MULTILINE)
    if match:
        latest = match.group(1)
    result["outputs"].append(output)
if not config.get("calls"):
    instances[0] = module.RappWorkAgent()
active[0] = False
result["base"] = [base.__name__ for base in type(instances[min(instances)]).__mro__]
result["rapp_work_modules"] = sorted(n for n in sys.modules if n.split(".")[0] == "rapp_work")
print(json.dumps(result))
'''


def run_child(config: dict[str, Any], cwd: Path) -> dict[str, Any]:
    payload = {"denied_events": list(PROCESS_OR_NETWORK), **config}
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", CHILD, json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


def process_or_network(events: list[list[str]]) -> list[list[str]]:
    return [event for event in events if event[0].startswith(PROCESS_OR_NETWORK)]


def brainstem_copy(root: Path) -> Path:
    agents = root / "agents"
    agents.mkdir(parents=True, mode=0o700)
    target = agents / "rapp_work_agent.py"
    target.write_bytes(AGENT_SOURCE.read_bytes())
    return target


def module_level_imports(tree: ast.Module) -> list[str]:
    names: list[str] = []
    pending: list[ast.stmt] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        else:
            for field in ("body", "orelse", "finalbody", "handlers"):
                for child in getattr(node, field, []) or []:
                    if isinstance(child, ast.ExceptHandler):
                        pending.extend(child.body)
                    elif isinstance(child, ast.stmt):
                        pending.append(child)
    return names


def test_module_top_level_imports_only_cross_platform_stdlib_and_basic_agent() -> None:
    tree = ast.parse(AGENT_SOURCE.read_text(encoding="utf-8"))
    names = module_level_imports(tree)
    assert "agents.basic_agent" in names and "basic_agent" in names
    for name in names:
        top = name.split(".")[0]
        if name in {"agents.basic_agent", "basic_agent"}:
            continue
        assert top in CROSS_PLATFORM_STDLIB, name
        assert top in sys.stdlib_module_names, name


def test_the_sdk_is_imported_in_exactly_one_lazy_place_and_nothing_runs_code() -> None:
    tree = ast.parse(AGENT_SOURCE.read_text(encoding="utf-8"))
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    owners: list[str] = []
    for function in functions:
        for node in ast.walk(function):
            if isinstance(node, ast.Import) and any(
                alias.name.split(".")[0] == "rapp_work" for alias in node.names
            ):
                owners.append(function.name)
            assert not (
                isinstance(node, ast.ImportFrom) and (node.module or "").startswith("rapp_work")
            )
    assert owners == ["_sdk"]
    forbidden_builtins = {"exec", "eval", "compile", "__import__", "breakpoint"}
    forbidden_attributes = {
        "import_module",
        "run_path",
        "run_module",
        "exec_module",
        "load_module",
        "system",
        "popen",
        "Popen",
        "execv",
        "execve",
        "spawnv",
        "fork",
    }
    forbidden_modules = {"subprocess", "runpy", "pip", "ensurepip", "urllib", "http", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = node.func
            if isinstance(called, ast.Name):
                assert called.id not in forbidden_builtins, called.id
            if isinstance(called, ast.Attribute):
                assert called.attr not in forbidden_attributes, called.attr
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            assert not {module.split(".")[0] for module in modules} & forbidden_modules


@pytest.mark.parametrize("shim", [True, False])
def test_load_and_first_use_never_look_up_a_third_party_module(sandbox: Path, shim: bool) -> None:
    agent = brainstem_copy(sandbox / "brainstem")
    result = run_child(
        {
            "agent": str(agent),
            "block": True,
            "shim": BASIC_AGENT_SHIM if shim else None,
            "audit_load": True,
            "env": {STATE_ENV: str(sandbox / "state")},
            "calls": [[0, {}]],
        },
        sandbox,
    )
    assert result["load_error"] is None
    assert result["lookups"] == []
    assert result["events"] == []
    assert result["outputs"][0].startswith("RappWork (newest Brainstem channel)")
    assert "BasicAgent" in result["base"]
    assert result["rapp_work_modules"] == []
    assert not (sandbox / "state").exists()


def test_a_missing_sdk_is_reported_with_its_pinned_source_and_no_side_effects(
    sandbox: Path,
) -> None:
    agent = brainstem_copy(sandbox / "brainstem")
    folder = str(sandbox)
    digest = "a" * 64
    calls = [
        {"action": "status"},
        {"action": "status", "root": folder},
        {"action": "verify", "root": folder},
        {"action": "discover", "roots": [folder]},
        {"action": "propose", "operation": "update", "root": folder},
        {"action": "confirm", "plan_sha256": digest},
        {"action": "apply", "plan_sha256": digest},
        {"action": "undo", "plan_sha256": digest},
    ]
    result = run_child(
        {
            "agent": str(agent),
            "shim": BASIC_AGENT_SHIM,
            "env": {STATE_ENV: str(sandbox / "state")},
            "calls": [[index, call] for index, call in enumerate(calls)],
        },
        sandbox,
    )
    outputs = result["outputs"]
    assert "RAPP Work SDK: not found" in outputs[0] and PINNED in outputs[0]
    for output in outputs[1:5]:
        assert "AGENT_REFUSE_SDK_MISSING" in output and PINNED in output
        assert "never installs anything itself" in output
    for output in outputs[5:]:
        assert "AGENT_REFUSE_UNKNOWN_PLAN" in output
    assert set(result["lookups"]) == {"rapp_work"}
    assert result["rapp_work_modules"] == []
    assert result["events"] == []
    assert not (sandbox / "state").exists()


def test_the_constructor_and_the_load_have_no_side_effects(sandbox: Path) -> None:
    agent = brainstem_copy(sandbox / "brainstem")
    result = run_child(
        {
            "agent": str(agent),
            "shim": BASIC_AGENT_SHIM,
            "audit_load": True,
            "block": True,
            "env": {STATE_ENV: str(sandbox / "state")},
        },
        sandbox,
    )
    assert result["load_error"] is None
    assert result["events"] == [] and result["lookups"] == []


@pytest.mark.parametrize("isolated", [True, False])
def test_standalone_execution_exits_zero_and_writes_nothing(sandbox: Path, isolated: bool) -> None:
    agent = brainstem_copy(sandbox / "brainstem")
    flags = ["-I", "-S"] if isolated else []
    completed = subprocess.run(
        [sys.executable, *flags, str(agent)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=sandbox,
        env={STATE_ENV: str(sandbox / "state"), "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("RappWork (newest Brainstem channel)")
    assert not (sandbox / "state").exists()


@pytest.mark.parametrize(
    "shadow",
    ["agents/rapp_work/__init__.py", "agents/rapp_work.py", "rapp_work.py", "rapp_work/__init__.py"],
)
def test_a_rapp_work_inside_the_brainstem_folders_is_never_imported(
    sandbox: Path, shadow: str
) -> None:
    brainstem = sandbox / "brainstem"
    agent = brainstem_copy(brainstem)
    sentinel = sandbox / "SHADOW-RAN"
    trap = brainstem / shadow
    trap.parent.mkdir(parents=True, exist_ok=True)
    trap.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('ran')\n"
        "def status(inputs):\n    return {}\n",
        encoding="utf-8",
    )
    result = run_child(
        {
            "agent": str(agent),
            "shim": BASIC_AGENT_SHIM,
            "allow": ["rapp_work"],
            "path": [str(brainstem / "agents"), str(brainstem), str(SRC)],
            "env": {STATE_ENV: str(sandbox / "state")},
            "calls": [
                [0, {"action": "status", "root": str(sandbox)}],
                [0, {"action": "propose", "operation": "update", "root": str(sandbox)}],
                [0, {"action": "status"}],
            ],
        },
        sandbox,
    )
    assert "AGENT_REFUSE_SDK_SHADOWED" in result["outputs"][0]
    assert "AGENT_REFUSE_SDK_SHADOWED" in result["outputs"][1]
    assert "RAPP Work SDK: REFUSED" in result["outputs"][2]
    assert result["rapp_work_modules"] == []
    assert not sentinel.exists()
    assert not (sandbox / "state").exists()


def test_a_full_flow_in_a_clean_interpreter_never_touches_network_or_processes(
    sandbox: Path,
) -> None:
    agent = brainstem_copy(sandbox / "brainstem")
    target = sandbox / "work" / "finance"
    target.parent.mkdir(mode=0o700)
    propose = {
        "action": "propose",
        "operation": "scaffold",
        "root": str(target),
        "owner_label": "example",
        "slug": "finance",
        "world_id": "example-world",
    }
    result = run_child(
        {
            "agent": str(agent),
            "shim": BASIC_AGENT_SHIM,
            "allow": ["rapp_work"],
            "block": True,
            "deny": True,
            "path": [str(SRC)],
            "env": {STATE_ENV: str(sandbox / "state")},
            "calls": [
                [0, propose],
                [0, {"action": "confirm", "plan_sha256": "$PLAN"}],
                [1, {"action": "confirm", "plan_sha256": "$PLAN"}],
                [1, {"action": "apply", "plan_sha256": "$PLAN"}],
                [1, {"action": "verify", "root": str(target)}],
                [1, {"action": "discover", "roots": [str(target)]}],
                [1, {"action": "undo", "plan_sha256": "$PLAN"}],
                [2, {"action": "status"}],
            ],
        },
        sandbox,
    )
    outputs = result["outputs"]
    assert "plan proposed by the RAPP Work SDK" in outputs[0]
    assert "AGENT_REFUSE_SAME_TURN" in outputs[1]
    assert "confirmed" in outputs[2]
    assert "(status created)" in outputs[3] and "verified" in outputs[3]
    assert ": verified" in outputs[4]
    assert "inert" in outputs[5]
    assert "AGENT_REFUSE_UNDO_AFTER_APPLY" in outputs[6]
    assert "plans: 1 applied" in outputs[7]
    assert result["lookups"] == []
    assert process_or_network(result["events"]) == []
    assert any(event[0] == "write" for event in result["events"])
    assert (target / "rappid.json").is_file()
