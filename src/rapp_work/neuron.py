from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._json import canonical_sha256
from ._paths import absolute_path, read_regular, write_new
from ._python_source import MAX_SOURCE_COST, WITHIN, measure_source
from .errors import require

MAX_NEURON_BYTES = 1024 * 1024


def _within_parse_bounds(raw: bytes) -> bool:
    # Measure the text the parser will read: PEP 263 decoding, exactly as the parser decodes.
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        text = raw.decode(encoding)
    except (SyntaxError, UnicodeDecodeError, LookupError):
        return False
    return measure_source(text, MAX_SOURCE_COST).verdict == WITHIN


def _literal_metadata(tree: ast.AST) -> dict[str, Any] | None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        for target in targets:
            name = target.id if isinstance(target, ast.Name) else (
                target.attr if isinstance(target, ast.Attribute) else None
            )
            if name != "metadata" or value is None:
                continue
            try:
                literal = ast.literal_eval(value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                continue
            if isinstance(literal, dict) and all(isinstance(key, str) for key in literal):
                try:
                    canonical_sha256(literal)
                except Exception:
                    continue
                return literal
    return None


@dataclass(frozen=True)
class PortableNeuron:
    path: Path
    sha256: str
    bytes: int
    declared_name: str | None
    metadata_sha256: str | None

    SCHEMA = "rapp-work-portable-neuron/1"

    @classmethod
    def inspect(cls, path: Path) -> PortableNeuron:
        path = absolute_path(path)
        raw = read_regular(path, limit=MAX_NEURON_BYTES)
        require(
            path.suffix == ".py",
            "REFUSE_NEURON",
            "Portable Neuron compatibility accepts inert Python source only",
        )
        if not _within_parse_bounds(raw):
            raise ValueError("Portable Neuron source is not valid bounded Python syntax")
        try:
            tree = ast.parse(raw, filename=str(path), mode="exec")
        except (SyntaxError, ValueError, MemoryError, RecursionError) as error:
            raise ValueError("Portable Neuron source is not valid bounded Python syntax") from error
        metadata = _literal_metadata(tree)
        declared = metadata.get("name") if metadata and isinstance(metadata.get("name"), str) else None
        return cls(
            path=path,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            declared_name=declared,
            metadata_sha256=canonical_sha256(metadata) if metadata is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bytes": self.bytes,
            "declared_name": self.declared_name,
            "executed": False,
            "language": "python",
            "metadata_sha256": self.metadata_sha256,
            "path": str(self.path),
            "schema": self.SCHEMA,
            "sha256": self.sha256,
            "treatment": "inert-data",
        }

    def copy_as_data(
        self,
        destination: Path,
        *,
        apply: bool,
        expected_sha256: str,
    ) -> dict[str, Any]:
        require(
            apply,
            "REFUSE_APPLY_REQUIRED",
            "copying a Portable Neuron requires an explicit apply request",
        )
        require(
            expected_sha256 == self.sha256,
            "REFUSE_PLAN_HASH",
            "Portable Neuron exact source SHA-256 is required",
        )
        raw = read_regular(self.path, limit=MAX_NEURON_BYTES)
        require(
            hashlib.sha256(raw).hexdigest() == self.sha256,
            "REFUSE_NEURON_CHANGED",
            "Portable Neuron changed after inspection",
        )
        destination = absolute_path(destination)
        require(
            not destination.exists() and not destination.is_symlink(),
            "REFUSE_CREATE_COLLISION",
            "Portable Neuron data destination must be absent",
        )
        write_new(destination, raw, mode=0o600)
        return {
            "destination": str(destination),
            "executed": False,
            "sha256": self.sha256,
            "status": "copied-as-data",
        }
