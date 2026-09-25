from __future__ import annotations

import hashlib
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from ._json import canonical_bytes, closed_object, strict_json_loads
from ._paths import (
    _nofollow_flags,
    absolute_path,
    assert_no_symlinks,
    directory_fd,
    read_regular_at,
    safe_relative,
)
from .constants import SDK_VERSION, WORKSPACE_PROFILE_ID
from .errors import Refusal, require

INSTRUCTION_INVENTORY_PATH = ".rapp-work/instructions.json"
INSTRUCTION_INVENTORY_SCHEMA = "rapp-work-instruction-inventory/1"
INSTRUCTION_REVIEW_SCHEMA = "rapp-work-instruction-review/1"
INSTRUCTION_SET_ID = "rapp-work-instruction-set/1"

MAX_SCAN_ENTRIES = 100_000
MAX_SCAN_DEPTH = 32
MAX_INSTRUCTION_FILES = 1_024
MAX_INSTRUCTION_FILE_BYTES = 1024 * 1024
MAX_INSTRUCTION_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REPORTED_FINDINGS = 64

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# rapp-work-instruction-set/1. Every value is already folded; never edit in place.
EXCLUDED_NAMES = frozenset({".git"})
INSTRUCTION_NAMES = frozenset(
    {
        ".cursorrules",
        "agents.md",
        "agents.override.md",
        "claude.local.md",
        "claude.md",
        "gemini.md",
    }
)
PARENT_FILES = frozenset({(".github", "copilot-instructions.md")})
CONTAINERS: tuple[tuple[str, str, str, str], ...] = (
    (".agents", "skills", "name", "skill.md"),
    (".claude", "agents", "suffix", ".md"),
    (".claude", "commands", "suffix", ".md"),
    (".claude", "rules", "suffix", ".md"),
    (".claude", "skills", "name", "skill.md"),
    (".cursor", "rules", "suffix", ".mdc"),
    (".github", "agents", "suffix", ".md"),
    (".github", "chatmodes", "suffix", ".chatmode.md"),
    (".github", "instructions", "suffix", ".instructions.md"),
    (".github", "prompts", "suffix", ".prompt.md"),
    (".github", "skills", "name", "skill.md"),
)
CONTAINER_PAIRS = frozenset((first, second) for first, second, _, _ in CONTAINERS)
CONTAINER_ROOTS = frozenset(first for first, _ in CONTAINER_PAIRS) | frozenset(
    parent for parent, _ in PARENT_FILES
)

Entries = dict[str, tuple[int, str]]


def fold(value: str) -> str:
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", value).casefold())


def _matches_folded(folded: tuple[str, ...]) -> bool:
    name = folded[-1]
    if name in INSTRUCTION_NAMES:
        return True
    if len(folded) >= 2 and (folded[-2], name) in PARENT_FILES:
        return True
    ancestors = folded[:-1]
    for index in range(len(ancestors) - 1):
        pair = (ancestors[index], ancestors[index + 1])
        for first, second, kind, value in CONTAINERS:
            if pair == (first, second) and (
                name == value if kind == "name" else name.endswith(value)
            ):
                return True
    return False


def _exposes_instructions(folded: tuple[str, ...]) -> bool:
    return (
        _matches_folded(folded)
        or folded[-1] in CONTAINER_ROOTS
        or any(
            (folded[index], folded[index + 1]) in CONTAINER_PAIRS
            for index in range(len(folded) - 1)
        )
    )


def _display(relative: str) -> str:
    try:
        relative.encode("utf-8")
    except UnicodeEncodeError:
        return relative.encode("utf-8", "surrogateescape").decode("ascii", "backslashreplace")
    return relative


def _recordable(relative: str) -> bool:
    try:
        relative.encode("utf-8")
        return safe_relative(relative) == relative
    except (Refusal, UnicodeEncodeError):
        return False


def is_instruction_path(relative: str) -> bool:
    require(
        _recordable(relative),
        "REFUSE_INSTRUCTION_PATH",
        "instruction path is outside the portable relative path grammar",
        path=_display(relative),
        reason="path-grammar",
    )
    return _matches_folded(tuple(fold(part) for part in PurePosixPath(relative).parts))


def _refuse_path(relative: str, reason: str) -> NoReturn:
    raise Refusal(
        "REFUSE_INSTRUCTION_PATH",
        "instruction paths must be regular, single-link files reached without links",
        {"path": _display(relative), "reason": reason},
    )


def _refuse_limit(reason: str, limit: int, relative: str | None = None) -> NoReturn:
    details: dict[str, Any] = {"limit": limit, "reason": reason}
    if relative is not None:
        details["path"] = _display(relative)
    raise Refusal(
        "REFUSE_INSTRUCTION_SCAN_LIMIT",
        "instruction scan bound exceeded; nothing was truncated or accepted",
        details,
    )


@dataclass
class _Scan:
    entries: int = 0
    total_bytes: int = 0
    files: dict[str, bytes] = field(default_factory=dict)


def _record(descriptor: int, name: str, relative: str, info: os.stat_result, scan: _Scan) -> None:
    if not _recordable(relative):
        _refuse_path(relative, "path-grammar")
    if info.st_nlink != 1:
        _refuse_path(relative, "hardlink")
    if info.st_size > MAX_INSTRUCTION_FILE_BYTES:
        _refuse_limit("file-bytes", MAX_INSTRUCTION_FILE_BYTES, relative)
    if len(scan.files) >= MAX_INSTRUCTION_FILES:
        _refuse_limit("files", MAX_INSTRUCTION_FILES)
    try:
        content = read_regular_at(
            descriptor,
            name,
            display=relative,
            limit=MAX_INSTRUCTION_FILE_BYTES,
        )
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_PATH",
            "instruction file could not be read without following links",
            {"path": relative, "reason": "unreadable"},
        ) from error
    scan.total_bytes += len(content)
    if scan.total_bytes > MAX_INSTRUCTION_TOTAL_BYTES:
        _refuse_limit("total-bytes", MAX_INSTRUCTION_TOTAL_BYTES)
    scan.files[relative] = content


def _scan_directory(
    descriptor: int,
    parts: tuple[str, ...],
    folded_parts: tuple[str, ...],
    scan: _Scan,
) -> None:
    depth = len(parts)
    try:
        with os.scandir(descriptor) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not list a directory",
            {"path": _display("/".join(parts) or ".")},
        ) from error
    for entry in entries:
        scan.entries += 1
        if scan.entries > MAX_SCAN_ENTRIES:
            _refuse_limit("entries", MAX_SCAN_ENTRIES)
        if entry.name in EXCLUDED_NAMES:
            continue
        child = (*parts, entry.name)
        folded = (*folded_parts, fold(entry.name))
        relative = "/".join(child)
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise Refusal(
                "REFUSE_INSTRUCTION_SCAN",
                "instruction scan could not inspect an entry",
                {"path": _display(relative)},
            ) from error
        if stat.S_ISDIR(info.st_mode):
            if _matches_folded(folded):
                _refuse_path(relative, "not-regular")
            if depth + 1 > MAX_SCAN_DEPTH:
                _refuse_limit("depth", MAX_SCAN_DEPTH, relative)
            try:
                child_descriptor = os.open(
                    entry.name,
                    _nofollow_flags(directory=True),
                    dir_fd=descriptor,
                )
            except OSError as error:
                raise Refusal(
                    "REFUSE_INSTRUCTION_SCAN",
                    "instruction scan could not open a directory without following links",
                    {"path": _display(relative)},
                ) from error
            try:
                opened = os.fstat(child_descriptor)
                require(
                    stat.S_ISDIR(opened.st_mode)
                    and (opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino),
                    "REFUSE_FILE_RACE",
                    "directory changed during the instruction scan",
                    path=_display(relative),
                )
                _scan_directory(child_descriptor, child, folded, scan)
            finally:
                os.close(child_descriptor)
        elif stat.S_ISREG(info.st_mode):
            if _matches_folded(folded):
                _record(descriptor, entry.name, relative, info, scan)
        elif _exposes_instructions(folded):
            _refuse_path(relative, "symlink" if stat.S_ISLNK(info.st_mode) else "not-regular")


def scan_instruction_files(root: Path) -> dict[str, bytes]:
    root = assert_no_symlinks(absolute_path(root))
    require(
        os.scandir in os.supports_fd,
        "REFUSE_PLATFORM",
        "descriptor-relative directory listing is unavailable",
    )
    scan = _Scan()
    with directory_fd(root) as descriptor:
        _scan_directory(descriptor, (), (), scan)
    return dict(sorted(scan.files.items()))


def inventory_record(files: Mapping[str, bytes]) -> dict[str, Any]:
    require(
        len(files) <= MAX_INSTRUCTION_FILES
        and sum(len(content) for content in files.values()) <= MAX_INSTRUCTION_TOTAL_BYTES,
        "REFUSE_INSTRUCTION_SCAN_LIMIT",
        "instruction inventory exceeds its fixed bounds",
    )
    entries: list[dict[str, Any]] = []
    for path, content in sorted(files.items()):
        require(
            is_instruction_path(path) and len(content) <= MAX_INSTRUCTION_FILE_BYTES,
            "REFUSE_INSTRUCTION_INVENTORY",
            "only bounded instruction paths can be inventoried",
            path=_display(path),
        )
        entries.append(
            {
                "bytes": len(content),
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "files": entries,
        "instruction_set": INSTRUCTION_SET_ID,
        "profile": WORKSPACE_PROFILE_ID,
        "schema": INSTRUCTION_INVENTORY_SCHEMA,
        "sdk_version": SDK_VERSION,
    }


def parse_inventory(raw: bytes) -> Entries:
    value = strict_json_loads(raw, where="instruction inventory")
    item = closed_object(
        value,
        required={"files", "instruction_set", "profile", "schema", "sdk_version"},
        where="instruction inventory",
    )
    require(
        raw == canonical_bytes(item)
        and item["schema"] == INSTRUCTION_INVENTORY_SCHEMA
        and item["profile"] == WORKSPACE_PROFILE_ID
        and item["instruction_set"] == INSTRUCTION_SET_ID
        and isinstance(item["sdk_version"], str)
        and bool(SEMVER.fullmatch(item["sdk_version"]))
        and isinstance(item["files"], list)
        and len(item["files"]) <= MAX_INSTRUCTION_FILES,
        "REFUSE_INSTRUCTION_INVENTORY",
        "instruction inventory contract mismatch",
    )
    entries: Entries = {}
    paths: list[str] = []
    for raw_entry in item["files"]:
        entry = closed_object(
            raw_entry,
            required={"bytes", "path", "sha256"},
            where="instruction inventory entry",
        )
        path = entry["path"]
        require(
            isinstance(path, str)
            and _recordable(path)
            and _matches_folded(tuple(fold(part) for part in PurePosixPath(path).parts))
            and type(entry["bytes"]) is int
            and 0 <= entry["bytes"] <= MAX_INSTRUCTION_FILE_BYTES
            and isinstance(entry["sha256"], str)
            and bool(HEX64.fullmatch(entry["sha256"])),
            "REFUSE_INSTRUCTION_INVENTORY",
            "invalid instruction inventory entry",
            path=_display(path) if isinstance(path, str) else None,
        )
        entries[path] = (entry["bytes"], entry["sha256"])
        paths.append(path)
    require(
        paths == sorted(set(paths))
        and sum(size for size, _ in entries.values()) <= MAX_INSTRUCTION_TOTAL_BYTES,
        "REFUSE_INSTRUCTION_INVENTORY",
        "instruction inventory entries must be unique, path sorted, and bounded",
    )
    return entries


def observed_entries(files: Mapping[str, bytes]) -> Entries:
    return {
        path: (len(content), hashlib.sha256(content).hexdigest())
        for path, content in files.items()
    }


def drift(recorded: Entries, observed: Entries) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(set(recorded) | set(observed)):
        if path not in observed:
            findings.append({"path": path, "reason": "missing"})
        elif path not in recorded:
            findings.append({"path": path, "reason": "unlisted"})
        elif recorded[path] != observed[path]:
            findings.append({"path": path, "reason": "changed"})
    return findings


def require_no_drift(
    recorded: Entries,
    observed: Entries,
    *,
    code: str,
    message: str,
) -> None:
    findings = drift(recorded, observed)
    if findings:
        raise Refusal(
            code,
            message,
            {
                "findings": findings[:MAX_REPORTED_FINDINGS],
                "path": findings[0]["path"],
                "reason": findings[0]["reason"],
                "total": len(findings),
            },
        )


def review(prior: Entries | None, planned: Entries) -> dict[str, Any]:
    before = prior or {}
    files: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(planned)):
        old = before.get(path)
        new = planned.get(path)
        if old is None:
            change = "added"
        elif new is None:
            change = "removed"
        else:
            change = "unchanged" if old == new else "changed"
        files.append(
            {
                "bytes": None if new is None else new[0],
                "change": change,
                "path": path,
                "prior_bytes": None if old is None else old[0],
                "prior_sha256": None if old is None else old[1],
                "sha256": None if new is None else new[1],
            }
        )
    return {
        "files": files,
        "instruction_set": INSTRUCTION_SET_ID,
        "inventory": INSTRUCTION_INVENTORY_PATH,
        "prior_inventory": "absent" if prior is None else "present",
        "schema": INSTRUCTION_REVIEW_SCHEMA,
    }
