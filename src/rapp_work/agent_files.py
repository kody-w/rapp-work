from __future__ import annotations

import ast
import codecs
import hashlib
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

from ._paths import read_regular
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

# PEP 263 declaration, checked on the first two physical lines.
_ENCODING_DECLARATION = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")
_FIRST_TWO_LINES = re.compile(rb"([^\r\n]*)(?:\r\n|\r|\n)?([^\r\n]*)")
_SIGNED_NUMBER_TYPES = (int, float, complex)

ManifestFields: TypeAlias = tuple[tuple[str, str | None], ...]


def is_agent_file_name(name: str) -> bool:
    return name.endswith(AGENT_SUFFIX)


def live_directory(root: Path) -> Path:
    return root if root.name == LIVE_DIRECTORY else root / LIVE_DIRECTORY


def display_path(path: Path) -> str:
    return str(path).encode("utf-8", "backslashreplace").decode("utf-8")


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


def _parse(text: str) -> ast.Module | None:
    if "\x00" in text:
        return None
    try:
        # Parser warnings would otherwise follow the host's warning filters.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ast.parse(text, filename="<rapp-work-agent>", mode="exec")
    except Exception:
        return None


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
        elif isinstance(
            node,
            (
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.ExceptHandler,
                ast.FunctionDef,
                ast.MatchAs,
                ast.MatchStar,
            ),
        ):
            sites += node.name == MANIFEST_NAME
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
    def inspect(cls, path: Path, *, root: Path) -> DiscoveredAgent:
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
        tree = _parse(text) if text is not None else None
        if text is None:
            syntax = "unsupported-encoding"
        elif tree is None:
            syntax = "invalid"
        else:
            syntax = "parsed"
            classes = _agent_classes(tree)
            manifest_status, manifest = _manifest(tree)
        return cls(
            path=path,
            root=root,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            role="base-class" if path.name == BASE_CLASS_FILE else "agent",
            live=not path.name.startswith(".") and path.parent == live_directory(root),
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


def inspect_agent_entry(path: Path, *, root: Path) -> DiscoveredAgent | dict[str, Any]:
    shown = display_path(path)
    try:
        require(shown == str(path), "REFUSE_AGENT_NAME", "agent path is not valid UTF-8")
        return DiscoveredAgent.inspect(path, root=root)
    except (Refusal, ValueError, OSError) as error:
        code = error.code if isinstance(error, Refusal) else "REFUSE_DISCOVERY_METADATA"
        return {"code": code, "message": str(error), "path": shown}
