from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import importlib.util
import json
import os
import runpy
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from rapp_work import discover
from rapp_work._json import canonical_text
from rapp_work.agent_files import MAX_AGENT_BYTES, MAX_AGENT_CLASSES, MAX_CLASS_NAME_CHARS
from rapp_work.cli import main

# Computed from the unmodified `rapp-work-sdk/1` 1.0.0 implementation (origin/main 29ead23)
# for `build_tree_without_agents`, on Python 3.10 and 3.13.
LEGACY_TREE_SHA256 = "104820080267095c3d8aee9b05934957b26c9e18f5b6ac267f3019e8d03921ba"
AGENT_TREE_SHA256 = "e71ec3c56a5d5765a5e7b3dce0859e009a79cf746f01e635e83edc8c85d09c49"
RECORD_KEYS = {
    "authority",
    "bytes",
    "classes",
    "executed",
    "language",
    "live",
    "manifest",
    "manifest_status",
    "path",
    "role",
    "root",
    "schema",
    "sha256",
    "syntax",
    "treatment",
}
MANIFEST_KEYS = {"description", "display_name", "name", "schema", "version"}

BASE_SOURCE = b'''class BasicAgent:
    def __init__(self, name=None, metadata=None):
        self.name = name or "BasicAgent"

    def perform(self, **kwargs):
        return "Not implemented."
'''

HELLO_SOURCE = b'''"""A small example agent."""

from agents.basic_agent import BasicAgent

__manifest__ = {
    "schema": "rapp-agent/1.0",
    "name": "@example/hello_agent",
    "version": "1.0.0",
    "display_name": "Hello",
    "description": "Says hello to example.com.",
    "tags": ["example", "greeting"],
    "requires_env": [],
}


class HelloAgent(BasicAgent):
    def __init__(self):
        super().__init__(name="Hello")

    def perform(self, **kwargs):
        return "hello"
'''

DRAFT_SOURCE = b'''from agents.basic_agent import BasicAgent


class DraftAgent(BasicAgent):
    def perform(self, **kwargs):
        return "draft"
'''


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _normalized_sha256(value: Any, root: Path) -> str:
    text = canonical_text(value).replace(str(root), "<root>")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _records(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    assert envelope["status"] == "ok", envelope
    return list(envelope["result"].get("agents", []))


def _by_path(envelope: dict[str, Any], root: Path) -> dict[str, dict[str, Any]]:
    return {
        str(Path(record["path"]).relative_to(root)): record for record in _records(envelope)
    }


def _refusals(envelope: dict[str, Any], root: Path) -> dict[str, str]:
    return {
        str(Path(value["path"]).relative_to(root)): value["code"]
        for value in envelope["result"]["refusals"]
    }


def build_tree_without_agents(root: Path) -> None:
    _write(
        root / ".github/skills/example/SKILL.md",
        b"---\nname: example-skill\n---\nNever execute.\n",
    )
    _write(root / "plugin/plugin.py", b"raise SystemExit('never run')\n")
    _write(
        root / "plugin/rapp-work-plugin.json",
        b'{"capabilities":["example"],"entrypoint":"plugin.py",'
        b'"name":"example-plugin","schema":"rapp-work-plugin/1","version":"1.0.0"}',
    )
    _write(
        root / "neurons/example/agent.py",
        b"metadata = {'name': 'Example neuron', 'parameters': {}}\n",
    )
    agents = root / "agents"
    _write(agents / "README.md", b"# Agents\n")
    _write(agents / "notes_agent.md", b"Not Python.\n")
    _write(agents / "Upper_AGENT.py", b"x = 1\n")
    _write(agents / "old_agent.py.bak", b"x = 1\n")
    _write(agents / "folder_agent.py/inner.txt", b"data\n")
    os.symlink(agents / "README.md", agents / "link_agent.py")
    os.mkfifo(agents / "pipe_agent.py")


def build_agent_tree(root: Path) -> None:
    agents = root / "agents"
    _write(agents / "basic_agent.py", BASE_SOURCE)
    _write(agents / "hello_agent.py", HELLO_SOURCE)
    _write(agents / "broken_agent.py", b"def broken(:\n")
    _write(agents / "latin_agent.py", b"# -*- coding: latin-1 -*-\nname = 'caf\xe9'\n")
    _write(agents / "experimental/draft_agent.py", DRAFT_SOURCE)
    _write(root / "notes/copy_agent.py", HELLO_SOURCE)


@contextmanager
def _execution_tripwires(literal_nodes: list[str], violations: list[str]) -> Iterator[None]:
    original_compile = builtins.compile
    original_import_module = importlib.import_module
    original_literal_eval = ast.literal_eval

    def violation(name: str) -> AssertionError:
        violations.append(name)
        return AssertionError(f"discovery attempted {name}")

    def refuse(name: str) -> Any:
        def refused(*args: Any, **kwargs: Any) -> Any:
            raise violation(name)

        return refused

    def ast_only_compile(
        source: Any, filename: Any, mode: Any, flags: int = 0, *args: Any, **kwargs: Any
    ) -> Any:
        if not flags & ast.PyCF_ONLY_AST:
            raise violation("compile to a code object")
        return original_compile(source, filename, mode, flags, *args, **kwargs)

    def loaded_only_import_module(name: str, package: str | None = None) -> Any:
        if name not in sys.modules:
            raise violation(f"import_module({name})")
        return original_import_module(name, package)

    def recorded_literal_eval(node: Any) -> Any:
        literal_nodes.append(type(node).__name__)
        return original_literal_eval(node)

    replacements = [
        (builtins, "exec", refuse("exec")),
        (builtins, "eval", refuse("eval")),
        (builtins, "compile", ast_only_compile),
        (importlib, "import_module", loaded_only_import_module),
        (importlib.util, "spec_from_file_location", refuse("spec_from_file_location")),
        (importlib.util, "module_from_spec", refuse("module_from_spec")),
        (runpy, "run_path", refuse("run_path")),
        (runpy, "run_module", refuse("run_module")),
        (ast, "literal_eval", recorded_literal_eval),
    ]
    saved = [(owner, name, getattr(owner, name)) for owner, name, _ in replacements]
    try:
        for owner, name, replacement in replacements:
            setattr(owner, name, replacement)
        yield
    finally:
        for owner, name, value in saved:
            setattr(owner, name, value)


def test_top_level_agents_directory_files_are_live_and_subfolders_are_organization(
    sandbox: Path,
) -> None:
    home = sandbox / "brainstem"
    _write(home / "agents/alpha_agent.py", DRAFT_SOURCE)
    _write(home / "agents/_agent.py", DRAFT_SOURCE)
    _write(home / "agents/.hidden_agent.py", DRAFT_SOURCE)
    _write(home / "agents/experimental/beta_agent.py", DRAFT_SOURCE)
    _write(home / "agents/agents/gamma_agent.py", DRAFT_SOURCE)
    _write(home / "loose_agent.py", DRAFT_SOURCE)
    _write(home / "vendor/agents/delta_agent.py", DRAFT_SOURCE)

    as_home = _by_path(discover({"roots": [str(home)]}), home)
    assert {path: record["live"] for path, record in as_home.items()} == {
        "agents/.hidden_agent.py": False,
        "agents/_agent.py": True,
        "agents/agents/gamma_agent.py": False,
        "agents/alpha_agent.py": True,
        "agents/experimental/beta_agent.py": False,
        "loose_agent.py": False,
        "vendor/agents/delta_agent.py": False,
    }
    assert all(record["root"] == str(home) for record in as_home.values())

    agents_root = home / "agents"
    as_agents_dir = _by_path(discover({"roots": [str(agents_root)]}), agents_root)
    assert {path: record["live"] for path, record in as_agents_dir.items()} == {
        ".hidden_agent.py": False,
        "_agent.py": True,
        "agents/gamma_agent.py": False,
        "alpha_agent.py": True,
        "experimental/beta_agent.py": False,
    }


def test_live_is_relative_to_each_scanned_root(sandbox: Path) -> None:
    home = sandbox / "brainstem"
    agent = _write(home / "agents/alpha_agent.py", DRAFT_SOURCE)
    records = _records(discover({"roots": [str(home), str(sandbox)]}))
    assert [(record["path"], record["root"], record["live"]) for record in records] == [
        (str(agent), str(sandbox), False),
        (str(agent), str(home), True),
    ]


def test_base_class_file_is_recorded_as_base_class_never_as_an_agent(sandbox: Path) -> None:
    _write(sandbox / "agents/basic_agent.py", BASE_SOURCE)
    _write(sandbox / "agents/archive/basic_agent.py", BASE_SOURCE)
    _write(
        sandbox / "agents/tampered/basic_agent.py",
        BASE_SOURCE + b"\n\nclass Smuggled(BasicAgent):\n    pass\n",
    )
    records = _by_path(discover({"roots": [str(sandbox)]}), sandbox)
    top = records["agents/basic_agent.py"]
    assert (top["role"], top["live"], top["classes"], top["syntax"]) == (
        "base-class",
        True,
        [],
        "parsed",
    )
    archived = records["agents/archive/basic_agent.py"]
    assert (archived["role"], archived["live"]) == ("base-class", False)
    assert records["agents/tampered/basic_agent.py"]["classes"] == ["Smuggled"]
    assert records["agents/tampered/basic_agent.py"]["role"] == "base-class"


def test_basic_agent_subclasses_are_named_by_syntax_only(sandbox: Path) -> None:
    source = b'''import agents.basic_agent as base
from agents.basic_agent import BasicAgent


class Meta(type):
    pass


class Other:
    pass


class A(BasicAgent):
    pass


class B(base.BasicAgent):
    pass


class C(Other):
    pass


class D(Other, BasicAgent, metaclass=Meta):
    pass


class _E(BasicAgent):
    pass


class H(BasicAgentMixin):
    pass


class A(BasicAgent):
    pass


if True:
    class F(BasicAgent):
        pass


def factory():
    class G(BasicAgent):
        pass
    return G
'''
    _write(sandbox / "agents/classes_agent.py", source)
    (record,) = _records(discover({"roots": [str(sandbox)]}))
    assert record["classes"] == ["A", "B", "D", "_E"]


def test_class_bounds_refuse_the_record(sandbox: Path) -> None:
    many = b"".join(
        f"class A{index}(BasicAgent):\n    pass\n".encode()
        for index in range(MAX_AGENT_CLASSES + 1)
    )
    _write(sandbox / "agents/many_agent.py", many)
    long_name = "L" * (MAX_CLASS_NAME_CHARS + 1)
    _write(sandbox / "agents/long_agent.py", f"class {long_name}(BasicAgent):\n    pass\n".encode())
    at_bound = b"".join(
        f"class A{index}(BasicAgent):\n    pass\n".encode() for index in range(MAX_AGENT_CLASSES)
    )
    _write(sandbox / "agents/bound_agent.py", at_bound)
    envelope = discover({"roots": [str(sandbox)]})
    assert _refusals(envelope, sandbox) == {
        "agents/long_agent.py": "REFUSE_AGENT_METADATA",
        "agents/many_agent.py": "REFUSE_AGENT_METADATA",
    }
    (record,) = _records(envelope)
    assert len(record["classes"]) == MAX_AGENT_CLASSES


def test_literal_manifest_fields_are_extracted_as_bounded_data(sandbox: Path) -> None:
    _write(sandbox / "agents/hello_agent.py", HELLO_SOURCE)
    _write(
        sandbox / "agents/annotated_agent.py",
        b'__manifest__: dict = {\n    # comments and trailing commas are fine\n'
        b'    "schema": "rapp-agent/1.0",\n    "name": "@example/" "annotated_agent",\n'
        b'    "version": "2.0.0",\n    "limits": {"max": -1, "ratio": 0.5, "set": {1, 2}},\n'
        b'    "flags": (True, None, ...),\n}\n',
    )
    long_text = "x" * 1025
    _write(
        sandbox / "agents/typed_agent.py",
        (
            '__manifest__ = {"schema": b"rapp-agent/1.0", "name": "\\ud800", '
            '"version": 1, "display_name": "\\uffff", '
            f'"description": "{long_text}"}}\n'
        ).encode(),
    )
    _write(sandbox / "agents/bare_agent.py", b"x = 1\n")
    _write(sandbox / "agents/declared_agent.py", b"__manifest__: dict\n")
    records = _by_path(discover({"roots": [str(sandbox)]}), sandbox)

    hello = records["agents/hello_agent.py"]
    assert hello["manifest_status"] == "literal"
    assert hello["manifest"] == {
        "description": "Says hello to example.com.",
        "display_name": "Hello",
        "name": "@example/hello_agent",
        "schema": "rapp-agent/1.0",
        "version": "1.0.0",
    }
    annotated = records["agents/annotated_agent.py"]
    assert annotated["manifest_status"] == "literal"
    assert annotated["manifest"] == {
        "description": None,
        "display_name": None,
        "name": "@example/annotated_agent",
        "schema": "rapp-agent/1.0",
        "version": "2.0.0",
    }
    typed = records["agents/typed_agent.py"]
    assert typed["manifest_status"] == "literal"
    assert typed["manifest"] == dict.fromkeys(MANIFEST_KEYS)
    for name in ("bare_agent.py", "declared_agent.py"):
        assert records["agents/" + name]["manifest_status"] == "absent"
        assert records["agents/" + name]["manifest"] is None
    canonical_text(records)


def test_non_literal_ambiguous_and_oversized_manifests_are_never_evaluated(
    sandbox: Path,
) -> None:
    sentinel = sandbox / "manifest-evaluated"
    effect = f"__import__('pathlib').Path({str(sentinel)!r}).write_text('ran')"
    literal = '{"schema": "rapp-agent/1.0", "name": "@example/x"}'
    cases = {
        "call": f"__manifest__ = dict(name={effect})\n",
        "name_value": f"BASE = {literal}\n__manifest__ = BASE\n",
        "effect_value": f'__manifest__ = {{"schema": "rapp-agent/1.0", "name": {effect}}}\n',
        "fstring": '__manifest__ = {"name": f"@example/{1 + 1}"}\n',
        "spread": f"BASE = {literal}\n__manifest__ = {{**BASE}}\n",
        "comprehension": "__manifest__ = {key: key for key in ('a', 'b')}\n",
        "concatenation": '__manifest__ = {"name": "@example/" + "x"}\n',
        "name_key": 'KEY = "name"\n__manifest__ = {KEY: "@example/x"}\n',
        "twice": f"__manifest__ = {literal}\n__manifest__ = {literal}\n",
        "conditional": f"if True:\n    __manifest__ = {literal}\n",
        "mutated": f"__manifest__ = {literal}\n__manifest__['name'] = {effect}\n",
        "imported": f"import os as __manifest__\n__manifest__ = {literal}\n",
        "only_import": "from os import path as __manifest__\n",
        "chained": f"__manifest__ = __manifest__ = {literal}\n",
        "loop": f"__manifest__ = {literal}\nfor __manifest__ in (): pass\n",
        "deleted": f"__manifest__ = {literal}\ndel __manifest__\n",
        "walrus": f"__manifest__ = {literal}\n(__manifest__ := 1)\n",
        "function": f"__manifest__ = {literal}\ndef __manifest__():\n    return {effect}\n",
        "duplicate_key": '__manifest__ = {"name": "@example/a", "name": "@example/b"}\n',
        "deep": "__manifest__ = {\"x\": " + "[" * 20 + "]" * 20 + "}\n",
        "wide": "__manifest__ = {\"x\": [" + ", ".join(["0"] * 5000) + "]}\n",
        "wide_call_last": "__manifest__ = {\"x\": [" + ", ".join(["0"] * 5000) + f", {effect}]}}\n",
        "wide_call_first": f"__manifest__ = {{\"x\": [{effect}, " + ", ".join(["0"] * 5000) + "]}\n",
        "repeat_with_call": f'__manifest__ = {{"name": "@example/a", "name": {effect}}}\n',
        "unhashable_member": '__manifest__ = {"name": "@example/a", "set": {(1, [2])}}\n',
        "wide_unhashable": "__manifest__ = {\"x\": [" + ", ".join(["0"] * 5000) + "], \"s\": {(1, [2])}}\n",
    }
    for name, source in cases.items():
        _write(sandbox / f"agents/{name}_agent.py", source.encode())
    literal_nodes: list[str] = []
    violations: list[str] = []
    with _execution_tripwires(literal_nodes, violations):
        envelope = discover({"roots": [str(sandbox)]})
    assert violations == []
    statuses = {
        Path(record["path"]).name.removesuffix("_agent.py"): record["manifest_status"]
        for record in _records(envelope)
    }
    assert statuses == {
        "call": "not-literal",
        "name_value": "not-literal",
        "effect_value": "not-literal",
        "fstring": "not-literal",
        "spread": "not-literal",
        "comprehension": "not-literal",
        "concatenation": "not-literal",
        "name_key": "not-literal",
        "twice": "ambiguous",
        "conditional": "ambiguous",
        "mutated": "ambiguous",
        "imported": "ambiguous",
        "only_import": "ambiguous",
        "chained": "ambiguous",
        "loop": "ambiguous",
        "deleted": "ambiguous",
        "walrus": "ambiguous",
        "function": "ambiguous",
        "duplicate_key": "ambiguous",
        "deep": "over-limit",
        "wide": "over-limit",
        "wide_call_last": "not-literal",
        "wide_call_first": "not-literal",
        "repeat_with_call": "ambiguous",
        "unhashable_member": "not-literal",
        "wide_unhashable": "over-limit",
    }
    assert all(record["manifest"] is None for record in _records(envelope))
    assert literal_nodes == ["Dict"]
    assert not sentinel.exists()


def test_side_effect_agents_never_execute_or_enter_sys_modules(sandbox: Path) -> None:
    sentinel = sandbox / "SENTINEL"
    environment_key = "RAPP_WORK_G3_TRAP"
    trap = f'''from pathlib import Path
Path({str(sentinel)!r}).write_text("top-level")
__import__("os").environ[{environment_key!r}] = "1"
import agents.basic_agent


def decorate(cls):
    Path({str(sentinel)!r}).write_text("decorator")
    return cls


class Meta(type):
    def __new__(mcls, name, bases, namespace):
        Path({str(sentinel)!r}).write_text("metaclass")
        return super().__new__(mcls, name, bases, namespace)


class BasicAgent:
    def __init_subclass__(cls, **kwargs):
        Path({str(sentinel)!r}).write_text("init-subclass")


@decorate
class TrapAgent(BasicAgent, metaclass=Meta):
    Path({str(sentinel)!r}).write_text("class-body")

    def perform(self, **kwargs):
        return Path({str(sentinel)!r}).write_text("perform")


__manifest__ = {{"schema": "rapp-agent/1.0", "name": "@example/trap_agent"}}
if __name__ == "__main__":
    Path({str(sentinel)!r}).write_text("main")
'''
    trap_path = _write(sandbox / "agents/trap_agent.py", trap.encode())
    _write(sandbox / "agents/experimental/nested_trap_agent.py", trap.encode())
    before = set(sys.modules)
    envelope = discover({"roots": [str(sandbox)]})
    records = _by_path(envelope, sandbox)
    assert not sentinel.exists()
    assert environment_key not in os.environ
    added = set(sys.modules) - before
    assert "trap_agent" not in sys.modules
    assert "nested_trap_agent" not in sys.modules
    assert not [
        name
        for name in added
        if str(getattr(sys.modules[name], "__file__", "") or "").startswith(str(sandbox))
    ]
    top = records["agents/trap_agent.py"]
    assert top["executed"] is False
    assert top["live"] is True
    assert top["classes"] == ["TrapAgent"]
    assert top["manifest"]["name"] == "@example/trap_agent"
    assert top["sha256"] == hashlib.sha256(trap_path.read_bytes()).hexdigest()
    assert top["bytes"] == len(trap_path.read_bytes())


def test_tripwires_prove_no_import_compile_or_exec(sandbox: Path) -> None:
    build_agent_tree(sandbox)
    _write(sandbox / "agents/trap_agent.py", b"raise SystemExit('never run')\n")
    literal_nodes: list[str] = []
    violations: list[str] = []
    with _execution_tripwires(literal_nodes, violations):
        envelope = discover({"roots": [str(sandbox)]})
    assert violations == []
    records = _by_path(envelope, sandbox)
    literal = [record for record in records.values() if record["manifest_status"] == "literal"]
    assert literal_nodes == ["Dict"] * len(literal) == ["Dict", "Dict"]


def test_invalid_and_unsupported_sources_are_recorded_without_parsing_trust(
    sandbox: Path,
) -> None:
    manifest = b'__manifest__ = {"name": "@example/bom_agent"}\n'
    sources = {
        "syntax": b"def broken(:\n",
        "nul": b"x = 1\x00\n",
        "not_utf8": b"name = '\xff\xfe'\n",
        "latin1_cookie": b"# -*- coding: latin-1 -*-\nx = 1\n",
        "line2_cookie": b"#!/usr/bin/env python\n# coding: unicode_escape\nx = 1\n",
        "cr_cookie": b"#!/usr/bin/env python\r# vim: set fileencoding=cp1252 :\rx = 1\r",
        "bom_latin1": b"\xef\xbb\xbf# coding: latin-1\nx = 1\n",
        "utf8_cookie": b"# -*- coding: UTF_8 -*-\n" + manifest,
        "utf8_alias": b"# vim: set fileencoding=utf8 :\n" + manifest,
        "bom": b"\xef\xbb\xbf" + manifest,
        "too_complex": b"x = " + b"-" * 20000 + b"1\n",
        "compile_only_error": b"return 1\n",
    }
    for name, data in sources.items():
        _write(sandbox / f"agents/{name}_agent.py", data)
    records = {
        Path(record["path"]).name.removesuffix("_agent.py"): record
        for record in _records(discover({"roots": [str(sandbox)]}))
    }
    assert {name: record["syntax"] for name, record in records.items()} == {
        "syntax": "invalid",
        "nul": "invalid",
        "not_utf8": "unsupported-encoding",
        "latin1_cookie": "unsupported-encoding",
        "line2_cookie": "unsupported-encoding",
        "cr_cookie": "unsupported-encoding",
        "bom_latin1": "unsupported-encoding",
        "utf8_cookie": "parsed",
        "utf8_alias": "parsed",
        "bom": "parsed",
        "too_complex": "invalid",
        "compile_only_error": "parsed",
    }
    for record in records.values():
        if record["syntax"] != "parsed":
            assert (record["classes"], record["manifest_status"], record["manifest"]) == (
                None,
                None,
                None,
            )
    assert records["bom"]["manifest"]["name"] == "@example/bom_agent"
    assert records["utf8_cookie"]["manifest_status"] == "literal"


def test_parser_verdict_follows_the_running_interpreter(sandbox: Path) -> None:
    sources = {
        "generic": b"class Generic[T]:\n    pass\n",
        "huge_integer": b"x = " + b"9" * 5000 + b"\n",
    }
    expected = {}
    for name, data in sources.items():
        _write(sandbox / f"agents/{name}_agent.py", data)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                ast.parse(data.decode("utf-8"))
            expected[name] = "parsed"
        except SyntaxError:
            expected[name] = "invalid"
    records = _records(discover({"roots": [str(sandbox)]}))
    assert {
        Path(record["path"]).name.removesuffix("_agent.py"): record["syntax"] for record in records
    } == expected
    assert expected["generic"] == ("parsed" if sys.version_info >= (3, 12) else "invalid")


def test_host_warning_filters_do_not_change_the_verdict(sandbox: Path) -> None:
    _write(sandbox / "agents/warning_agent.py", b'x = "\\d"\ny = 1 if 1else 2\n')
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        (record,) = _records(discover({"roots": [str(sandbox)]}))
    assert record["syntax"] == "parsed"


def test_unsafe_agent_entries_are_refused_deterministically(sandbox: Path) -> None:
    agents = sandbox / "agents"
    _write(agents / "limit_agent.py", b"#" * MAX_AGENT_BYTES)
    _write(agents / "oversize_agent.py", b"#" * (MAX_AGENT_BYTES + 1))
    outside = _write(sandbox / "outside.py", b"raise SystemExit('outside')\n")
    os.symlink(outside, agents / "link_agent.py")
    os.mkfifo(agents / "pipe_agent.py")
    hard = _write(agents / "hard_agent.py", DRAFT_SOURCE)
    os.link(hard, agents / "hardcopy_agent.py")
    _write(agents / "folder_agent.py/inner.txt", b"data\n")
    envelope = discover({"roots": [str(sandbox)]})
    assert _refusals(envelope, sandbox) == {
        "agents/hard_agent.py": "REFUSE_PATH_TYPE",
        "agents/hardcopy_agent.py": "REFUSE_PATH_TYPE",
        "agents/link_agent.py": "REFUSE_SYMLINK",
        "agents/oversize_agent.py": "REFUSE_FILE_LIMIT",
        "agents/pipe_agent.py": "REFUSE_PATH_TYPE",
    }
    records = _by_path(envelope, sandbox)
    assert list(records) == ["agents/limit_agent.py"]
    assert records["agents/limit_agent.py"]["bytes"] == MAX_AGENT_BYTES
    assert records["agents/limit_agent.py"]["syntax"] == "parsed"


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="requires POSIX non-root")
def test_unreadable_agent_is_refused(sandbox: Path) -> None:
    locked = _write(sandbox / "agents/locked_agent.py", DRAFT_SOURCE)
    locked.chmod(0)
    try:
        envelope = discover({"roots": [str(sandbox)]})
    finally:
        locked.chmod(0o600)
    assert _refusals(envelope, sandbox) == {"agents/locked_agent.py": "REFUSE_PATH_UNSAFE"}
    assert _records(envelope) == []


def test_undecodable_agent_name_is_refused_with_an_escaped_path(sandbox: Path) -> None:
    raw_name = os.fsencode(sandbox) + b"/\xff_agent.py"
    try:
        descriptor = os.open(raw_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError:
        pytest.skip("filesystem requires UTF-8 file names")
    os.close(descriptor)
    envelope = discover({"roots": [str(sandbox)]})
    (refusal,) = envelope["result"]["refusals"]
    assert refusal["code"] == "REFUSE_AGENT_NAME"
    assert refusal["path"].endswith("\\udcff_agent.py")
    assert _records(envelope) == []
    canonical_text(envelope)


def test_agent_records_are_closed_canonical_and_inert(sandbox: Path) -> None:
    build_agent_tree(sandbox)
    records = _records(discover({"roots": [str(sandbox)]}))
    assert len(records) == 6
    for record in records:
        assert set(record) == RECORD_KEYS
        assert record["schema"] == "rapp-work-discovered-agent/1"
        assert record["executed"] is False
        assert record["authority"] == "discovery-only"
        assert record["treatment"] == "inert-data"
        assert record["language"] == "python"
        assert record["role"] in {"agent", "base-class"}
        assert record["syntax"] in {"parsed", "invalid", "unsupported-encoding"}
        assert record["manifest_status"] in {
            None,
            "absent",
            "literal",
            "not-literal",
            "ambiguous",
            "over-limit",
        }
        assert record["manifest"] is None or set(record["manifest"]) == MANIFEST_KEYS
        raw = Path(record["path"]).read_bytes()
        assert record["sha256"] == hashlib.sha256(raw).hexdigest()
        assert record["bytes"] == len(raw)
        assert json.loads(canonical_text(record)) == record


def test_agent_discovery_is_sorted_and_deterministic(sandbox: Path) -> None:
    first = sandbox / "first"
    second = sandbox / "second"
    for name in ("zeta_agent.py", "alpha_agent.py", "mid_agent.py"):
        _write(first / "agents" / name, DRAFT_SOURCE)
    for name in ("beta_agent.py", "aardvark_agent.py"):
        _write(second / "agents" / name, DRAFT_SOURCE)
    forward = discover({"roots": [str(first), str(second)]})
    backward = discover({"roots": [str(second), str(first)]})
    again = discover({"roots": [str(first), str(second)]})
    assert canonical_text(forward) == canonical_text(backward) == canonical_text(again)
    paths = [record["path"] for record in _records(forward)]
    assert paths == sorted(paths)
    assert [Path(path).name for path in paths] == [
        "alpha_agent.py",
        "mid_agent.py",
        "zeta_agent.py",
        "aardvark_agent.py",
        "beta_agent.py",
    ]


def test_agent_tree_output_matches_its_golden_vector(sandbox: Path) -> None:
    build_agent_tree(sandbox)
    envelope = discover({"roots": [str(sandbox)]})
    records = _by_path(envelope, sandbox)
    assert {
        path: (record["role"], record["live"], record["syntax"]) for path, record in records.items()
    } == {
        "agents/basic_agent.py": ("base-class", True, "parsed"),
        "agents/broken_agent.py": ("agent", True, "invalid"),
        "agents/experimental/draft_agent.py": ("agent", False, "parsed"),
        "agents/hello_agent.py": ("agent", True, "parsed"),
        "agents/latin_agent.py": ("agent", True, "unsupported-encoding"),
        "notes/copy_agent.py": ("agent", False, "parsed"),
    }
    assert _normalized_sha256(envelope, sandbox) == AGENT_TREE_SHA256


def test_agent_files_share_the_max_entries_bound(sandbox: Path) -> None:
    first = sandbox / "first"
    second = sandbox / "second"
    for name in ("a_agent.py", "b_agent.py", "c_agent.py"):
        _write(first / "agents" / name, DRAFT_SOURCE)
    _write(second / "d_agent.py", DRAFT_SOURCE)
    exact = discover({"roots": [str(first)], "max_entries": 4})
    assert len(_records(exact)) == 3
    refused = discover({"roots": [str(first)], "max_entries": 3})
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_DISCOVERY_LIMIT"
    shared = discover({"roots": [str(first), str(second)], "max_entries": 4})
    assert shared["status"] == "refused"
    assert shared["refusal"]["code"] == "REFUSE_DISCOVERY_LIMIT"
    assert len(_records(discover({"roots": [str(first), str(second)], "max_entries": 5}))) == 4


def test_trees_without_agent_files_keep_their_exact_output(sandbox: Path) -> None:
    build_tree_without_agents(sandbox)
    envelope = discover({"roots": [str(sandbox)]})
    assert envelope["status"] == "ok"
    assert "agents" not in envelope["result"]
    assert sorted(envelope["result"]) == [
        "api",
        "executed",
        "network",
        "neurons",
        "plugins",
        "refusals",
        "roots",
        "skills",
        "status",
    ]
    assert _normalized_sha256(envelope, sandbox) == LEGACY_TREE_SHA256


def test_cli_discover_emits_canonical_agent_records(
    sandbox: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(sandbox / "agents/hello_agent.py", HELLO_SOURCE)
    assert main(["discover", "--root", str(sandbox)]) == 0
    output = capsys.readouterr().out
    value = json.loads(output)
    assert output == canonical_text(value) + "\n"
    (record,) = value["result"]["agents"]
    assert (record["live"], record["classes"]) == (True, ["HelloAgent"])
