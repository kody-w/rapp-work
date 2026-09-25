from __future__ import annotations

import errno
import hashlib
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from ._json import canonical_bytes, closed_object, strict_json_loads
from ._paths import (
    _nofollow_flags,
    absolute_path,
    assert_no_symlinks,
    directory_fd,
    read_regular_at,
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
MAX_COMPONENT_BYTES = 1_024
MAX_REPORTED_FINDINGS = 64

HEX64 = re.compile(r"^[0-9a-f]{64}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# Refusals meaning "this tree cannot be inventoried as it stands"; races are not among them.
UNINVENTORIABLE = frozenset(
    {"REFUSE_INSTRUCTION_PATH", "REFUSE_INSTRUCTION_SCAN", "REFUSE_INSTRUCTION_SCAN_LIMIT"}
)

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
PARENT_FILES = frozenset(
    {
        (".claude", "settings.json"),
        (".claude", "settings.local.json"),
        (".codex", "config.toml"),
        (".cursor", "bugbot.md"),
        (".gemini", "settings.json"),
        (".gemini", "system.md"),
        (".github", "copilot-instructions.md"),
        (".vscode", "settings.json"),
    }
)
CONTAINERS: tuple[tuple[str, str, str, str], ...] = (
    (".agents", "skills", "name", "skill.md"),
    (".claude", "agents", "suffix", ".md"),
    (".claude", "commands", "suffix", ".md"),
    (".claude", "output-styles", "suffix", ".md"),
    (".claude", "rules", "suffix", ".md"),
    (".claude", "skills", "name", "skill.md"),
    (".codex", "agents", "suffix", ".md"),
    (".codex", "agents", "suffix", ".toml"),
    (".codex", "skills", "name", "skill.md"),
    (".cursor", "agents", "suffix", ".md"),
    (".cursor", "commands", "suffix", ".md"),
    (".cursor", "rules", "suffix", ".mdc"),
    (".cursor", "skills", "name", "skill.md"),
    (".gemini", "commands", "suffix", ".toml"),
    (".gemini", "skills", "name", "skill.md"),
    (".github", "agents", "suffix", ".md"),
    (".github", "chatmodes", "suffix", ".chatmode.md"),
    (".github", "instructions", "suffix", ".instructions.md"),
    (".github", "prompts", "suffix", ".prompt.md"),
    (".github", "skills", "name", "skill.md"),
)


def _container_rules() -> dict[tuple[str, str], tuple[tuple[str, str], ...]]:
    rules: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    for first, second, kind, value in CONTAINERS:
        rules[(first, second)] = (*rules.get((first, second), ()), (kind, value))
    return rules


CONTAINER_RULES = _container_rules()
CONTAINER_ROOTS = frozenset(first for first, _ in CONTAINER_RULES) | frozenset(
    parent for parent, _ in PARENT_FILES
)

# Unicode 16.0.0 Default_Ignorable_Code_Point (DerivedCoreProperties.txt), merged ranges.
DEFAULT_IGNORABLE: tuple[tuple[int, int], ...] = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)

Entries = dict[str, tuple[int, str]]
Parts = tuple[str, ...]
_scandir = os.scandir


def _ignorable(character: str) -> bool:
    code = ord(character)
    return code >= 0x00AD and any(low <= code <= high for low, high in DEFAULT_IGNORABLE)


def _strip_ignorable(value: str) -> str:
    return "".join(character for character in value if not _ignorable(character))


def fold(value: str) -> str:
    folded = unicodedata.normalize("NFKC", _strip_ignorable(value)).casefold()
    return _strip_ignorable(unicodedata.normalize("NFKC", folded))


def _matches_folded(folded: Parts) -> bool:
    name = folded[-1]
    if name in INSTRUCTION_NAMES:
        return True
    if len(folded) >= 2 and (folded[-2], name) in PARENT_FILES:
        return True
    ancestors = folded[:-1]
    for index in range(len(ancestors) - 1):
        for kind, value in CONTAINER_RULES.get((ancestors[index], ancestors[index + 1]), ()):
            if name == value if kind == "name" else name.endswith(value):
                return True
    return False


def _exposes_container(folded: Parts) -> bool:
    """A link here could make a path below it an instruction path its target path is not."""
    return folded[-1] in CONTAINER_ROOTS or any(
        (folded[index], folded[index + 1]) in CONTAINER_RULES for index in range(len(folded) - 1)
    )


def _display(relative: str) -> str:
    try:
        relative.encode("utf-8")
    except UnicodeEncodeError:
        return relative.encode("utf-8", "surrogateescape").decode("ascii", "backslashreplace")
    return relative


def _recordable(relative: Any) -> bool:
    if not isinstance(relative, str) or not relative:
        return False
    try:
        relative.encode("utf-8")
    except UnicodeEncodeError:
        return False
    parts = relative.split("/")
    return len(parts) <= MAX_SCAN_DEPTH + 1 and all(
        part not in {"", ".", ".."}
        and "\x00" not in part
        and len(part.encode("utf-8")) <= MAX_COMPONENT_BYTES
        for part in parts
    )


def _folded_parts(relative: str) -> Parts:
    return tuple(fold(part) for part in relative.split("/"))


def is_instruction_path(relative: str) -> bool:
    require(
        _recordable(relative),
        "REFUSE_INSTRUCTION_PATH",
        "instruction path is outside the recordable path grammar",
        path=_display(relative) if isinstance(relative, str) else None,
        reason="path-grammar",
    )
    return _matches_folded(_folded_parts(relative))


def _refuse_path(relative: str, reason: str) -> NoReturn:
    raise Refusal(
        "REFUSE_INSTRUCTION_PATH",
        "instruction paths must be recordable regular files reached as section 7.2 allows",
        {"path": _display(relative), "reason": reason},
    )


def _refuse_scan(relative: str, reason: str, message: str) -> NoReturn:
    raise Refusal(
        "REFUSE_INSTRUCTION_SCAN",
        message,
        {"path": _display(relative or "."), "reason": reason},
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
    root: int
    entries: int = 0
    total_bytes: int = 0
    files: dict[str, bytes] = field(default_factory=dict)


def _record(parent: int, name: str, relative: str, info: os.stat_result, scan: _Scan) -> None:
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
            parent,
            name,
            display=relative,
            limit=MAX_INSTRUCTION_FILE_BYTES,
            identity=(info.st_dev, info.st_ino),
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


def _list(descriptor: int, relative: str, scan: _Scan) -> list[os.DirEntry[str]]:
    listed: list[os.DirEntry[str]] = []
    try:
        with _scandir(descriptor) as iterator:
            for entry in iterator:
                scan.entries += 1
                if scan.entries > MAX_SCAN_ENTRIES:
                    _refuse_limit("entries", MAX_SCAN_ENTRIES)
                listed.append(entry)
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not list a directory",
            {"path": _display(relative or "."), "reason": "unreadable"},
        ) from error
    listed.sort(key=lambda entry: entry.name)
    return listed


def _open_directory(parent: int, name: str, relative: str, expected: os.stat_result) -> int:
    try:
        descriptor = os.open(name, _nofollow_flags(directory=True), dir_fd=parent)
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not open a directory without following links",
            {"path": _display(relative), "reason": "unreadable"},
        ) from error
    try:
        opened = os.fstat(descriptor)
    except OSError:
        os.close(descriptor)
        raise
    if not (
        stat.S_ISDIR(opened.st_mode)
        and (opened.st_dev, opened.st_ino) == (expected.st_dev, expected.st_ino)
    ):
        os.close(descriptor)
        raise Refusal(
            "REFUSE_FILE_RACE",
            "directory changed during the instruction scan",
            {"path": _display(relative)},
        )
    return descriptor


def _lexical_target(parent: Parts, text: str) -> Parts | None:
    """Resolve a relative link text inside the root, or None outside it or through `.git`."""
    if not text or text.startswith("/"):
        return None
    parts = list(parent)
    for component in text.split("/"):
        if component in {"", "."}:
            continue
        if component == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(component)
    if any(fold(part) == ".git" for part in parts):
        return None
    return tuple(parts)


def _open_in_tree(root: int, parts: Parts) -> int | None:
    """Open a directory below the root by no-follow steps, or None if any step is not one."""
    flags = _nofollow_flags(directory=True)
    try:
        descriptor = os.open(".", flags, dir_fd=root)
    except OSError:
        return None
    for part in parts:
        try:
            child = os.open(part, flags, dir_fd=descriptor)
        except OSError:
            os.close(descriptor)
            return None
        os.close(descriptor)
        descriptor = child
    return descriptor


def _link_target_stat(parent: int, name: str, relative: str) -> os.stat_result | None:
    """Stat what a link resolves to without opening it; None when it resolves to nothing."""
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=True)
    except OSError as error:
        if error.errno in {errno.ENOENT, errno.ENOTDIR, errno.ELOOP}:
            return None
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not inspect a link target",
            {"path": _display(relative), "reason": "uninspectable"},
        ) from error


def _record_link_target(scan: _Scan, parent: int, name: str, relative: str, real: Parts) -> None:
    """A link at an instruction path: record the bytes a tool reads through it."""
    try:
        text = os.readlink(name, dir_fd=parent)
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not read a link",
            {"path": _display(relative), "reason": "uninspectable"},
        ) from error
    target = _lexical_target(real[:-1], text)
    resolved = _link_target_stat(parent, name, relative)
    if not target or resolved is None or not stat.S_ISREG(resolved.st_mode):
        _refuse_path(relative, "symlink")
    directory = _open_in_tree(scan.root, target[:-1])
    if directory is None:
        _refuse_path(relative, "symlink")
    try:
        try:
            final: os.stat_result | None = os.stat(
                target[-1], dir_fd=directory, follow_symlinks=False
            )
        except OSError:
            final = None
        if (
            final is None
            or not stat.S_ISREG(final.st_mode)
            or (final.st_dev, final.st_ino) != (resolved.st_dev, resolved.st_ino)
        ):
            _refuse_path(relative, "symlink")
        _record(directory, target[-1], relative, final, scan)
    finally:
        os.close(directory)


def _follow_directory_link(
    scan: _Scan,
    parent: int,
    name: str,
    real: Parts,
    logical: Parts,
    folded: Parts,
    stack: frozenset[tuple[int, int]],
) -> None:
    relative = "/".join(logical)
    resolved = _link_target_stat(parent, name, relative)
    if resolved is None or not stat.S_ISDIR(resolved.st_mode):
        return
    try:
        text = os.readlink(name, dir_fd=parent)
    except OSError as error:
        raise Refusal(
            "REFUSE_INSTRUCTION_SCAN",
            "instruction scan could not read a link",
            {"path": _display(relative), "reason": "uninspectable"},
        ) from error
    target = _lexical_target(real[:-1], text)
    if target is None:
        _refuse_path(relative, "symlink")
    directory = _open_in_tree(scan.root, target)
    if directory is None:
        _refuse_path(relative, "symlink")
    try:
        opened = os.fstat(directory)
        key = (opened.st_dev, opened.st_ino)
        if key != (resolved.st_dev, resolved.st_ino):
            _refuse_path(relative, "symlink")
        if not _exposes_container(folded):
            return
        if len(logical) > MAX_SCAN_DEPTH:
            _refuse_limit("depth", MAX_SCAN_DEPTH, relative)
        if key in stack:
            _refuse_path(relative, "symlink-loop")
        _walk(scan, directory, target, logical, folded, stack | {key})
    finally:
        os.close(directory)


def _walk(
    scan: _Scan,
    descriptor: int,
    real: Parts,
    logical: Parts,
    folded: Parts,
    stack: frozenset[tuple[int, int]],
) -> None:
    """List one real directory, classifying each entry at its logical (tool-visible) path."""
    for entry in _list(descriptor, "/".join(logical), scan):
        name = entry.name
        if name in EXCLUDED_NAMES:
            continue
        child_real = (*real, name)
        child_logical = (*logical, name)
        child_folded = (*folded, fold(name))
        relative = "/".join(child_logical)
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise Refusal(
                "REFUSE_INSTRUCTION_SCAN",
                "instruction scan could not inspect an entry",
                {"path": _display(relative), "reason": "uninspectable"},
            ) from error
        if stat.S_ISDIR(info.st_mode):
            if _matches_folded(child_folded):
                _refuse_path(relative, "not-regular")
            if len(child_logical) > MAX_SCAN_DEPTH:
                _refuse_limit("depth", MAX_SCAN_DEPTH, relative)
            child = _open_directory(descriptor, name, relative, info)
            try:
                _walk(
                    scan,
                    child,
                    child_real,
                    child_logical,
                    child_folded,
                    stack | {(info.st_dev, info.st_ino)},
                )
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode):
            if _matches_folded(child_folded):
                _record(descriptor, name, relative, info, scan)
        elif stat.S_ISLNK(info.st_mode):
            if _matches_folded(child_folded):
                _record_link_target(scan, descriptor, name, relative, child_real)
            else:
                _follow_directory_link(
                    scan, descriptor, name, child_real, child_logical, child_folded, stack
                )
        elif _matches_folded(child_folded):
            _refuse_path(relative, "not-regular")


def scan_instruction_files(root: Path) -> dict[str, bytes]:
    root = assert_no_symlinks(absolute_path(root))
    require(
        os.scandir in os.supports_fd,
        "REFUSE_PLATFORM",
        "descriptor-relative directory listing is unavailable",
    )
    with directory_fd(root) as descriptor:
        info = os.fstat(descriptor)
        scan = _Scan(root=descriptor)
        _walk(scan, descriptor, (), (), (), frozenset({(info.st_dev, info.st_ino)}))
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
            _recordable(path)
            and _matches_folded(_folded_parts(path))
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


def review(
    prior: Entries | None,
    planned: Entries | None,
    *,
    scan_refusal: Refusal | None = None,
) -> dict[str, Any]:
    before = prior or {}
    after = planned or {}
    files: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
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
        "planned_inventory": "absent" if planned is None else "present",
        "prior_inventory": "absent" if prior is None else "present",
        "scan_refusal": None if scan_refusal is None else scan_refusal.as_dict(),
        "schema": INSTRUCTION_REVIEW_SCHEMA,
    }
