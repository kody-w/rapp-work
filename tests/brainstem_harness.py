"""A test double of the Brainstem hot-load contract (newest channel, brainstem-v0.6.16).

Written from the Brainstem's documented behavior; no kernel bytes are copied:

* only top-level ``agents/*_agent.py`` files are live (a flat glob, sorted);
* each load runs ``importlib.util.spec_from_file_location`` and ``exec_module``
  under a fresh module name, and the Brainstem loads again on every request, so
  an agent instance lives for exactly one request; the newest Brainstem runs
  requests on threads, so several ``Turn`` objects can be in flight at once;
* ``agents.basic_agent`` resolves to a shim registered in ``sys.modules``;
* every class defined in the file that has ``perform``, is not ``BasicAgent`` and
  does not start with ``_`` is instantiated and must pass the hot-load boundary:
  a tool-safe ``name``, a ``metadata`` dict with a string description, and
  JSON-schema ``parameters`` of type ``object`` whose nested schemas are well formed;
* a ``ModuleNotFoundError`` escaping a file's load is exactly what makes the real
  Brainstem run ``pip install <name>``; this harness raises ``AutoInstallWouldRun``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import os
import re
import shutil
import stat
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AGENT_SOURCE = ROOT / "integrations" / "brainstem" / "agents" / "rapp_work_agent.py"
TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")
PLAN_LINE = re.compile(r"^Plan SHA-256 \(full\): ([0-9a-f]{64})$", re.MULTILINE)

BASIC_AGENT_SHIM = '''\
class BasicAgent:
    """Test shim with the documented BasicAgent surface."""

    def __init__(self, name=None, metadata=None):
        if name is not None:
            self.name = name
        elif not hasattr(self, "name"):
            self.name = "BasicAgent"
        if metadata is not None:
            self.metadata = metadata
        elif not hasattr(self, "metadata"):
            self.metadata = {"name": self.name, "description": "", "parameters": {"type": "object"}}

    def perform(self, **kwargs):
        return "Not implemented."

    def system_context(self):
        return None

    def to_tool(self):
        parameters = self.metadata.get("parameters", {"type": "object", "properties": {}})
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.metadata.get("description", ""),
                "parameters": parameters,
            },
        }
'''


class AutoInstallWouldRun(AssertionError):
    """A load raised ModuleNotFoundError: the real Brainstem would run pip here."""


class Quarantined(AssertionError):
    """The hot-load boundary would skip this agent."""


def schema_problem(schema: Any, where: str) -> str | None:
    """The provider-critical JSON-schema shape rules the Brainstem enforces at hot-load."""
    if not isinstance(schema, dict):
        return f"{where} is not a schema object"
    kind = schema.get("type")
    if "type" in schema and not (
        isinstance(kind, str)
        or (isinstance(kind, list) and kind and all(isinstance(item, str) for item in kind))
    ):
        return f"{where}.type is neither a string nor a list of strings"
    if "description" in schema and not isinstance(schema["description"], str):
        return f"{where}.description is not a string"
    required = schema.get("required", [])
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        return f"{where}.required is not a list of strings"
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        return f"{where}.properties is not an object"
    for name, child in properties.items():
        if not isinstance(name, str):
            return f"{where}.properties has a non-string name"
        problem = schema_problem(child, f"{where}.properties[{name!r}]")
        if problem:
            return problem
    if "items" in schema:
        problem = schema_problem(schema["items"], f"{where}.items")
        if problem:
            return problem
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in schema:
            branches = schema[keyword]
            if not isinstance(branches, list) or not branches:
                return f"{where}.{keyword} is not a non-empty list"
            for index, branch in enumerate(branches):
                problem = schema_problem(branch, f"{where}.{keyword}[{index}]")
                if problem:
                    return problem
    if "not" in schema:
        problem = schema_problem(schema["not"], f"{where}.not")
        if problem:
            return problem
    extra = schema.get("additionalProperties", True)
    if not isinstance(extra, bool):
        return schema_problem(extra, f"{where}.additionalProperties")
    return None


def instance_problem(instance: Any) -> str | None:
    name = getattr(instance, "name", None)
    if not isinstance(name, str) or not TOOL_NAME.match(name):
        return f"name {name!r} is not tool-safe"
    metadata = getattr(instance, "metadata", None)
    if not isinstance(metadata, dict):
        return "metadata is not a dict"
    if "description" in metadata and not isinstance(metadata["description"], str):
        return "metadata description is not a string"
    if "parameters" in metadata:
        parameters = metadata["parameters"]
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            return "metadata parameters is not an object schema"
        return schema_problem(parameters, "parameters")
    return None


class Turn:
    """One Brainstem message: every tool call in it reaches the same fresh instance."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent

    @property
    def module_globals(self) -> dict[str, Any]:
        return type(self.agent).perform.__globals__  # type: ignore[no-any-return]

    def __call__(self, **arguments: Any) -> str:
        wire = json.loads(json.dumps(arguments))
        result = self.agent.perform(**wire)
        assert isinstance(result, str), type(result)
        return result


class Brainstem:
    """An emulated Brainstem folder holding agents/basic_agent.py and one agent file."""

    _loads = itertools.count()

    def __init__(self, root: Path, *, agent_source: Path = AGENT_SOURCE) -> None:
        self.root = root
        self.agents_dir = root / "agents"
        self.agents_dir.mkdir(parents=True, mode=0o700)
        (self.agents_dir / "basic_agent.py").write_text(BASIC_AGENT_SHIM, encoding="utf-8")
        self.agent_file = self.agents_dir / "rapp_work_agent.py"
        shutil.copyfile(agent_source, self.agent_file)

    def shim_modules(self) -> dict[str, types.ModuleType]:
        spec = importlib.util.spec_from_file_location(
            "agents.basic_agent", self.agents_dir / "basic_agent.py"
        )
        assert spec is not None and spec.loader is not None
        basic = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(basic)
        package = types.ModuleType("agents")
        package.__path__ = [str(self.agents_dir)]
        package.basic_agent = basic  # type: ignore[attr-defined]
        return {"agents": package, "agents.basic_agent": basic}

    def load_agents(self) -> dict[str, Any]:
        loaded: dict[str, Any] = {}
        for path in sorted(self.agents_dir.glob("*_agent.py")):
            module_name = f"agent_{path.stem}_{next(self._loads)}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except ModuleNotFoundError as error:
                raise AutoInstallWouldRun(f"{path.name}: {error}") from error
            for attribute in dir(module):
                candidate = getattr(module, attribute)
                if not (
                    isinstance(candidate, type)
                    and candidate.__module__ == module.__name__
                    and hasattr(candidate, "perform")
                    and attribute not in {"BasicAgent", "object"}
                    and not attribute.startswith("_")
                ):
                    continue
                instance = candidate()
                problem = instance_problem(instance)
                if problem:
                    raise Quarantined(f"{path.name}: {problem}")
                if instance.name in loaded:
                    raise Quarantined(f"{path.name}: duplicate agent name {instance.name!r}")
                json.dumps(instance.to_tool())
                loaded[instance.name] = instance
        return loaded

    def turn(self) -> Turn:
        return Turn(self.load_agents()["RappWork"])


def plan_hash(output: str) -> str:
    match = PLAN_LINE.search(output)
    assert match, output
    return match.group(1)


def snapshot(path: Path) -> dict[str, tuple[str, int, str]] | None:
    """Every entry under `path`, never following symlinks: kind, mode and content hash."""
    if not os.path.lexists(path):
        return None
    entries: dict[str, tuple[str, int, str]] = {}
    for current, directories, files in os.walk(path, followlinks=False):
        for name in [*directories, *files]:
            full = Path(current) / name
            info = full.lstat()
            if stat.S_ISLNK(info.st_mode):
                entries[str(full.relative_to(path))] = ("link", 0, os.readlink(full))
            elif stat.S_ISDIR(info.st_mode):
                entries[str(full.relative_to(path))] = ("dir", stat.S_IMODE(info.st_mode), "")
            else:
                digest = hashlib.sha256(full.read_bytes()).hexdigest()
                entries[str(full.relative_to(path))] = (
                    "file",
                    stat.S_IMODE(info.st_mode),
                    digest,
                )
    return entries
