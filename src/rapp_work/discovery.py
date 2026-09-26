from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from ._json import closed_object, strict_json_loads
from ._paths import absolute_path, assert_no_symlinks, read_regular, safe_relative
from ._resources import data_file
from .agent_files import (
    DiscoveredAgent,
    Identity,
    ParseBudget,
    inspect_agent_entry,
    is_agent_file_name,
    live_directory,
)
from .errors import Refusal, require
from .neuron import PortableNeuron

MAX_DISCOVERY_ENTRIES = 10_000
MAX_DISCOVERY_DEPTH = 12
MAX_METADATA_BYTES = 256 * 1024
SKILL_NAME = re.compile(rb"(?m)^name:[ \t]*([a-z0-9][a-z0-9-]{0,99})[ \t]*$")


@dataclass(frozen=True)
class SkillDescriptor:
    name: str
    path: Path
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bytes": self.bytes,
            "executed": False,
            "name": self.name,
            "path": str(self.path),
            "schema": "rapp-work-discovered-skill/1",
            "sha256": self.sha256,
            "treatment": "inert-metadata",
        }


@dataclass(frozen=True)
class PluginDescriptor:
    name: str
    version: str
    manifest: Path
    entrypoint: str
    capabilities: tuple[str, ...]
    manifest_sha256: str
    entrypoint_sha256: str

    @classmethod
    def inspect(cls, path: Path) -> PluginDescriptor:
        raw = read_regular(path, limit=MAX_METADATA_BYTES)
        value = strict_json_loads(raw, where="plugin manifest")
        item = closed_object(
            value,
            required={"capabilities", "entrypoint", "name", "schema", "version"},
            where="plugin manifest",
        )
        require(
            item["schema"] == "rapp-work-plugin/1"
            and isinstance(item["name"], str)
            and 0 < len(item["name"]) <= 100
            and isinstance(item["version"], str)
            and 0 < len(item["version"]) <= 64
            and isinstance(item["capabilities"], list)
            and len(item["capabilities"]) <= 128
            and all(isinstance(value, str) for value in item["capabilities"]),
            "REFUSE_PLUGIN",
            "plugin manifest contract mismatch",
        )
        require(
            all(0 < len(value) <= 128 for value in item["capabilities"]),
            "REFUSE_PLUGIN",
            "plugin capability is empty or too long",
        )
        entrypoint = safe_relative(item["entrypoint"])
        require(
            entrypoint == PurePosixPath(entrypoint).as_posix(),
            "REFUSE_PLUGIN",
            "plugin entrypoint must be a portable relative path",
        )
        entrypoint_raw = read_regular(path.parent / entrypoint)
        return cls(
            name=item["name"],
            version=item["version"],
            manifest=path,
            entrypoint=entrypoint,
            capabilities=tuple(sorted(set(item["capabilities"]))),
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            entrypoint_sha256=hashlib.sha256(entrypoint_raw).hexdigest(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": list(self.capabilities),
            "entrypoint": self.entrypoint,
            "entrypoint_sha256": self.entrypoint_sha256,
            "executed": False,
            "manifest": str(self.manifest),
            "manifest_sha256": self.manifest_sha256,
            "name": self.name,
            "schema": "rapp-work-discovered-plugin/1",
            "treatment": "inert-metadata",
            "version": self.version,
        }


def api_metadata() -> dict[str, Any]:
    value = strict_json_loads(read_regular(data_file("api.json")), where="static API metadata")
    require(isinstance(value, dict), "REFUSE_API_METADATA", "static API metadata must be an object")
    return cast(dict[str, Any], value)


def _skill(path: Path) -> SkillDescriptor:
    raw = read_regular(path, limit=MAX_METADATA_BYTES)
    match = SKILL_NAME.search(raw[: min(len(raw), 8192)])
    name = match.group(1).decode("ascii") if match else path.parent.name
    return SkillDescriptor(
        name=name,
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
    )


def _walk(root: Path, maximum: int) -> tuple[list[Path], list[dict[str, Any]], int]:
    root = assert_no_symlinks(absolute_path(root))
    files: list[Path] = []
    refusals: list[dict[str, Any]] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    observed = 0
    while stack:
        directory, depth = stack.pop()
        require(
            depth <= MAX_DISCOVERY_DEPTH,
            "REFUSE_DISCOVERY_DEPTH",
            "discovery depth exceeds the fixed bound",
            path=str(directory),
        )
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            refusals.append(
                {
                    "code": "REFUSE_DISCOVERY_READ",
                    "message": str(error),
                    "path": str(directory),
                }
            )
            continue
        for entry in entries:
            observed += 1
            require(
                observed <= maximum,
                "REFUSE_DISCOVERY_LIMIT",
                "discovery entry bound exceeded",
                maximum=maximum,
            )
            path = directory / entry.name
            if entry.is_symlink():
                refusals.append(
                    {
                        "code": "REFUSE_SYMLINK",
                        "message": "symlinked discovery entry ignored",
                        "path": str(path),
                    }
                )
            elif entry.is_dir(follow_symlinks=False):
                if entry.name in {".git", "__pycache__", ".venv", "venv", "build", "dist"}:
                    continue
                stack.append((path, depth + 1))
            elif entry.is_file(follow_symlinks=False):
                files.append(path)
            else:
                refusals.append(
                    {
                        "code": "REFUSE_PATH_TYPE",
                        "message": "non-regular discovery entry ignored",
                        "path": str(path),
                    }
                )
    return files, refusals, observed


def discover_roots(
    roots: list[Path],
    *,
    maximum: int = MAX_DISCOVERY_ENTRIES,
    agents: bool = False,
) -> dict[str, Any]:
    require(
        type(maximum) is int and 1 <= maximum <= MAX_DISCOVERY_ENTRIES,
        "REFUSE_DISCOVERY_LIMIT",
        "discovery maximum must be between 1 and 10000",
    )
    require(
        1 <= len(roots) <= 32,
        "REFUSE_DISCOVERY_ROOTS",
        "discover requires one to thirty-two explicit roots",
    )
    skills: list[SkillDescriptor] = []
    plugins: list[PluginDescriptor] = []
    neurons: list[PortableNeuron] = []
    agent_files: list[tuple[Path, Path, Identity | None]] = []
    refusals: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    remaining = maximum
    for root_value in roots:
        root = assert_no_symlinks(absolute_path(root_value))
        info = os.stat(root, follow_symlinks=False)
        identity = (int(info.st_dev), int(info.st_ino))
        if identity in seen:
            continue
        seen.add(identity)
        files, local_refusals, observed = _walk(root, remaining)
        remaining -= observed
        refusals.extend(local_refusals)
        live = live_directory(root) if agents else None
        for path in files:
            if agents and is_agent_file_name(path.name):
                agent_files.append((path, root, live))
                continue
            try:
                if path.name == "SKILL.md":
                    skills.append(_skill(path))
                elif path.name == "rapp-work-plugin.json":
                    plugins.append(PluginDescriptor.inspect(path))
                elif path.name == "agent.py":
                    neurons.append(PortableNeuron.inspect(path))
            except (Refusal, ValueError, OSError) as error:
                code = error.code if isinstance(error, Refusal) else "REFUSE_DISCOVERY_METADATA"
                refusals.append(
                    {
                        "code": code,
                        "message": str(error),
                        "path": str(path),
                    }
                )
    # One parse budget per call, spent in code-point order of path and then root.
    budget = ParseBudget()
    records: list[DiscoveredAgent] = []
    for path, root, live in sorted(agent_files, key=lambda item: (str(item[0]), str(item[1]))):
        entry = inspect_agent_entry(path, root=root, live=live, budget=budget)
        if isinstance(entry, DiscoveredAgent):
            records.append(entry)
        else:
            refusals.append(entry)
    skills.sort(key=lambda value: (value.name, str(value.path)))
    plugins.sort(key=lambda value: (value.name, value.version, str(value.manifest)))
    neurons.sort(key=lambda value: str(value.path))
    refusals.sort(key=lambda value: (value["path"], value["code"], value["message"]))
    result: dict[str, Any] = {
        "api": api_metadata(),
        "executed": False,
        "network": False,
        "neurons": [value.to_dict() for value in neurons],
        "plugins": [value.to_dict() for value in plugins],
        "refusals": refusals,
        "roots": sorted(str(absolute_path(value)) for value in roots),
        "skills": [value.to_dict() for value in skills],
        "status": "discovered",
    }
    # Only a request that opts in with `agents: true` gets this member.
    if agents:
        result["agents"] = [value.to_dict() for value in records]
    return result
