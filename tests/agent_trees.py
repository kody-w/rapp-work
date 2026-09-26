"""Synthetic trees for single-file agent discovery vectors (no rapp_work imports)."""

from __future__ import annotations

import os
from pathlib import Path

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

# 200,000 left-recursive additions: overflows the C stack of an unguarded 3.10 parse.
DEEP_CHAIN_SOURCE = b"x = 1" + b"+1" * 200_000 + b"\n"
AGENT_FILE_LIMIT = 1024 * 1024


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def build_tree_without_agents(root: Path) -> None:
    write(
        root / ".github/skills/example/SKILL.md",
        b"---\nname: example-skill\n---\nNever execute.\n",
    )
    write(root / "plugin/plugin.py", b"raise SystemExit('never run')\n")
    write(
        root / "plugin/rapp-work-plugin.json",
        b'{"capabilities":["example"],"entrypoint":"plugin.py",'
        b'"name":"example-plugin","schema":"rapp-work-plugin/1","version":"1.0.0"}',
    )
    write(
        root / "neurons/example/agent.py",
        b"metadata = {'name': 'Example neuron', 'parameters': {}}\n",
    )
    agents = root / "agents"
    write(agents / "README.md", b"# Agents\n")
    write(agents / "notes_agent.md", b"Not Python.\n")
    write(agents / "Upper_AGENT.py", b"x = 1\n")
    write(agents / "old_agent.py.bak", b"x = 1\n")
    write(agents / "folder_agent.py/inner.txt", b"data\n")
    os.symlink(agents / "README.md", agents / "link_agent.py")
    os.mkfifo(agents / "pipe_agent.py")


def build_mixed_tree(root: Path) -> None:
    """Everything above plus agent files that discovery reads only when asked to."""

    build_tree_without_agents(root)
    agents = root / "agents"
    write(agents / "basic_agent.py", BASE_SOURCE)
    write(agents / "hello_agent.py", HELLO_SOURCE)
    write(agents / "broken_agent.py", b"def broken(:\n")
    write(agents / "deep_agent.py", DEEP_CHAIN_SOURCE)
    write(agents / "experimental/draft_agent.py", DRAFT_SOURCE)
    hard = write(agents / "hard_agent.py", DRAFT_SOURCE)
    os.link(hard, agents / "hardcopy_agent.py")
    write(agents / "oversize_agent.py", b"#" * (AGENT_FILE_LIMIT + 1))


def build_agent_tree(root: Path) -> None:
    agents = root / "agents"
    write(agents / "basic_agent.py", BASE_SOURCE)
    write(agents / "hello_agent.py", HELLO_SOURCE)
    write(agents / "broken_agent.py", b"def broken(:\n")
    write(agents / "latin_agent.py", b"# -*- coding: latin-1 -*-\nname = 'caf\xe9'\n")
    write(agents / "deep_agent.py", DEEP_CHAIN_SOURCE)
    write(agents / "experimental/draft_agent.py", DRAFT_SOURCE)
    write(root / "notes/copy_agent.py", HELLO_SOURCE)
