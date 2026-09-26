from __future__ import annotations

import ast
import codecs
import hashlib
import os
import re
import stat
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from ._paths import read_regular
from ._python_source import INVALID, MAX_SOURCE_COST, OVER_COST, WITHIN, measure_source
from .errors import Refusal, require

AGENT_SCHEMA = "rapp-work-discovered-agent/1"
AGENT_SUFFIX = "_agent.py"
BASE_CLASS_FILE = "basic_agent.py"
BASE_CLASS_NAME = "BasicAgent"
LIVE_DIRECTORY = "agents"
MANIFEST_NAME = "__manifest__"
MANIFEST_FIELDS = ("description", "display_name", "name", "schema", "version")
MAX_AGENT_BYTES = 1024 * 1024
MAX_AGENT_CLASSES = 256
MAX_CLASS_NAME_CHARS = 256
MAX_MANIFEST_DEPTH = 16
MAX_MANIFEST_NODES = 4096
MAX_MANIFEST_FIELD_CHARS = 1024
MAX_CALL_PARSE_COST = 8_388_608

# PEP 263 declaration, checked on the first two physical lines.
_ENCODING_DECLARATION = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")
_FIRST_TWO_LINES = re.compile(rb"([^\r\n]*)(?:\r\n|\r|\n)?([^\r\n]*)")
_SIGNED_NUMBER_TYPES = (int, float, complex)
# Warning filters are process-wide; one lock keeps concurrent discover calls from interleaving them.
_PARSE_LOCK = threading.Lock()

ManifestFields: TypeAlias = tuple[tuple[str, str | None], ...]
Identity: TypeAlias = tuple[int, int]


class ParseBudget:
    """Cost units one ``discover`` call may spend measuring and parsing agent sources."""

    def __init__(self, units: int | None = None) -> None:
        self.remaining = MAX_CALL_PARSE_COST if units is None else units


def is_agent_file_name(name: str) -> bool:
    return name.endswith(AGENT_SUFFIX)


def display_path(path: Path) -> str:
    return str(path).encode("utf-8", "backslashreplace").decode("utf-8")


def _directory_identity(path: Path) -> Identity | None:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError:
        return None
    return (int(info.st_dev), int(info.st_ino)) if stat.S_ISDIR(info.st_mode) else None


def live_directory(root: Path) -> Identity | None:
    """Identity of the directory the name ``agents`` resolves to for a scanned root.

    Names resolve as the file system resolves them, so a case-insensitive volume
    finds ``Agents`` for ``agents`` exactly as the Brainstem kernel's glob does.
    """

    own = _directory_identity(root)
    if own is not None and _directory_identity(root.parent / LIVE_DIRECTORY) == own:
        return own
    return _directory_identity(root / LIVE_DIRECTORY)


def _utf8_declaration(name: bytes) -> bool:
    normal = name.decode("ascii").lower().replace("_", "-")
    return normal in {"utf-8", "utf8"} or normal.startswith("utf-8-")


def _source_text(raw: bytes) -> str | None:
    body = raw[len(codecs.BOM_UTF8) :] if raw.startswith(codecs.BOM_UTF8) else raw
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return None
    lines = _FIRST_TWO_LINES.match(body)
    assert lines is not None
    for line in lines.groups():
        declaration = _ENCODING_DECLARATION.match(line)
        if declaration is not None and not _utf8_declaration(declaration.group(1)):
            return None
    return text


def _parse(text: str, budget: ParseBudget) -> tuple[str, ast.Module | None]:
    if "\x00" in text:
        return "invalid", None
    allowance = min(MAX_SOURCE_COST, budget.remaining)
    if allowance <= 0:
        return "over-budget", None
    measure = measure_source(text, allowance)
    budget.remaining -= min(measure.cost, allowance)
    if measure.verdict == OVER_COST:
        return ("over-limit" if allowance == MAX_SOURCE_COST else "over-budget"), None
    if measure.verdict == INVALID:
        return "invalid", None
    if measure.verdict != WITHIN:
        return "over-limit", None
    try:
        with _PARSE_LOCK, warnings.catch_warnings():
            # Parser warnings would otherwise follow the host's warning filters.
            warnings.simplefilter("ignore")
            return "parsed", ast.parse(text, filename="<rapp-work-agent>", mode="exec")
    except Exception:
        return "invalid", None


def _names_base_class(base: ast.expr) -> bool:
    return (isinstance(base, ast.Name) and base.id == BASE_CLASS_NAME) or (
        isinstance(base, ast.Attribute) and base.attr == BASE_CLASS_NAME
    )


def _agent_classes(tree: ast.Module) -> tuple[str, ...]:
    names = sorted(
        {
            statement.name
            for statement in tree.body
            if isinstance(statement, ast.ClassDef)
            and any(_names_base_class(base) for base in statement.bases)
        }
    )
    require(
        len(names) <= MAX_AGENT_CLASSES
        and all(len(name) <= MAX_CLASS_NAME_CHARS for name in names),
        "REFUSE_AGENT_METADATA",
        "agent class names exceed the fixed bound",
    )
    return tuple(names)


_NAMED_BINDINGS: tuple[type[ast.AST], ...] = (
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.ExceptHandler,
    ast.FunctionDef,
    ast.MatchAs,
    ast.MatchStar,
    *(
        getattr(ast, name)
        for name in ("ParamSpec", "TypeVar", "TypeVarTuple")
        if hasattr(ast, name)
    ),
)


def _manifest_binding_sites(tree: ast.Module) -> int:
    declarations: set[int] = set()
    sites = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and node.value is None:
            declarations.add(id(node.target))
        elif isinstance(node, ast.Name):
            sites += (
                node.id == MANIFEST_NAME
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and id(node) not in declarations
            )
        elif isinstance(node, (ast.Attribute, ast.Subscript)):
            sites += (
                isinstance(node.ctx, (ast.Store, ast.Del))
                and isinstance(node.value, ast.Name)
                and node.value.id == MANIFEST_NAME
            )
        elif isinstance(node, ast.arg):
            sites += node.arg == MANIFEST_NAME
        elif isinstance(node, _NAMED_BINDINGS):
            sites += getattr(node, "name", None) == MANIFEST_NAME
        elif isinstance(node, ast.MatchMapping):
            sites += node.rest == MANIFEST_NAME
        elif isinstance(node, ast.alias):
            sites += (node.asname or node.name.partition(".")[0]) == MANIFEST_NAME
    return sites


def _manifest_value(statement: ast.stmt) -> ast.expr | None:
    if isinstance(statement, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == MANIFEST_NAME
        for target in statement.targets
    ):
        return statement.value
    if (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.target.id == MANIFEST_NAME
    ):
        return statement.value
    return None


def _repeats_constant_key(value: ast.expr) -> bool:
    if not isinstance(value, ast.Dict):
        return False
    keys = [key.value for key in value.keys if isinstance(key, ast.Constant)]
    return len(set(keys)) != len(keys)


def _literal_verdict(value: ast.expr) -> str:
    """Classify a manifest value; nodes are displays, constants, and signed constants."""

    if not isinstance(value, ast.Dict):
        return "not-literal"
    stack: list[tuple[ast.expr, int]] = [(value, 1)]
    nodes = 0
    deepest = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        deepest = max(deepest, depth)
        children: list[ast.expr]
        if isinstance(node, ast.Constant):
            continue
        if isinstance(node, ast.UnaryOp):
            if (
                isinstance(node.op, (ast.UAdd, ast.USub))
                and isinstance(node.operand, ast.Constant)
                and type(node.operand.value) in _SIGNED_NUMBER_TYPES
            ):
                continue
            return "not-literal"
        if isinstance(node, ast.Dict):
            keys = [key for key in node.keys if isinstance(key, ast.Constant)]
            if len(keys) != len(node.keys):
                return "not-literal"
            children = [*keys, *node.values]
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            children = list(node.elts)
        else:
            return "not-literal"
        stack.extend((child, depth + 1) for child in children)
    if nodes > MAX_MANIFEST_NODES or deepest > MAX_MANIFEST_DEPTH:
        return "over-limit"
    return "literal"


def _interoperable_text(text: str) -> bool:
    for character in text:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF or 0xFDD0 <= point <= 0xFDEF or point & 0xFFFE == 0xFFFE:
            return False
    return True


def _field(value: object) -> str | None:
    if (
        isinstance(value, str)
        and len(value) <= MAX_MANIFEST_FIELD_CHARS
        and _interoperable_text(value)
    ):
        return value
    return None


def _manifest(tree: ast.Module) -> tuple[str, ManifestFields | None]:
    sites = _manifest_binding_sites(tree)
    if sites == 0:
        return "absent", None
    values = [value for value in map(_manifest_value, tree.body) if value is not None]
    if sites != 1 or len(values) != 1 or _repeats_constant_key(values[0]):
        return "ambiguous", None
    verdict = _literal_verdict(values[0])
    if verdict != "literal":
        return verdict, None
    try:
        literal = ast.literal_eval(values[0])
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return "not-literal", None
    if not isinstance(literal, dict):
        return "not-literal", None
    return "literal", tuple((key, _field(literal.get(key))) for key in MANIFEST_FIELDS)


@dataclass(frozen=True)
class DiscoveredAgent:
    path: Path
    root: Path
    sha256: str
    bytes: int
    role: str
    live: bool
    syntax: str
    classes: tuple[str, ...] | None
    manifest_status: str | None
    manifest: ManifestFields | None

    SCHEMA = AGENT_SCHEMA

    @classmethod
    def inspect(
        cls,
        path: Path,
        *,
        root: Path,
        live: Identity | None,
        budget: ParseBudget,
    ) -> DiscoveredAgent:
        require(
            is_agent_file_name(path.name),
            "REFUSE_AGENT",
            "single-file agent names end with _agent.py",
        )
        raw = read_regular(path, limit=MAX_AGENT_BYTES)
        classes: tuple[str, ...] | None = None
        manifest_status: str | None = None
        manifest: ManifestFields | None = None
        text = _source_text(raw)
        if text is None:
            syntax = "unsupported-encoding"
        else:
            syntax, tree = _parse(text, budget)
            if tree is not None:
                classes = _agent_classes(tree)
                manifest_status, manifest = _manifest(tree)
        return cls(
            path=path,
            root=root,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            role="base-class" if path.name == BASE_CLASS_FILE else "agent",
            live=(
                live is not None
                and not path.name.startswith(".")
                and _directory_identity(path.parent) == live
            ),
            syntax=syntax,
            classes=classes,
            manifest_status=manifest_status,
            manifest=manifest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": "discovery-only",
            "bytes": self.bytes,
            "classes": list(self.classes) if self.classes is not None else None,
            "executed": False,
            "language": "python",
            "live": self.live,
            "manifest": dict(self.manifest) if self.manifest is not None else None,
            "manifest_status": self.manifest_status,
            "path": str(self.path),
            "role": self.role,
            "root": str(self.root),
            "schema": self.SCHEMA,
            "sha256": self.sha256,
            "syntax": self.syntax,
            "treatment": "inert-data",
        }


def inspect_agent_entry(
    path: Path,
    *,
    root: Path,
    live: Identity | None,
    budget: ParseBudget,
) -> DiscoveredAgent | dict[str, Any]:
    shown = display_path(path)
    try:
        require(shown == str(path), "REFUSE_AGENT_NAME", "agent path is not valid UTF-8")
        return DiscoveredAgent.inspect(path, root=root, live=live, budget=budget)
    except (Refusal, ValueError, OSError) as error:
        code = error.code if isinstance(error, Refusal) else "REFUSE_DISCOVERY_METADATA"
        return {"code": code, "message": str(error), "path": shown}
