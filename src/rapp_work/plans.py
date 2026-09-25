from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal

from ._json import (
    bytes_sha256,
    canonical_b64,
    canonical_bytes,
    canonical_sha256,
    closed_object,
    decode_b64,
)
from ._paths import MAX_FILE_BYTES, absolute_path, safe_relative
from .errors import require
from .rapp1 import rappid_valid, verify_detached_jws

HEX64 = re.compile(r"^[0-9a-f]{64}$")
LABEL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ActionKind = Literal["create", "replace"]

MAX_MOVES = 64
MAX_MOVE_TOTAL_BYTES = 64 * 1024 * 1024
PROTECTED_ROOT_FILES = frozenset({"organization.json", "spec.md", "workspaces.json"})
INSTRUCTION_NAMES = frozenset({"agents.md", "claude.md", "gemini.md", "skill.md", "soul.md"})
INSTRUCTION_SUFFIXES = (".agent.md", ".chatmode.md", ".instructions.md", ".prompt.md")


@dataclass(frozen=True)
class FileAction:
    operation: ActionKind
    path: str
    content: bytes
    mode: int = 0o600
    expected_sha256: str | None = None

    def __post_init__(self) -> None:
        safe_relative(self.path)
        require(
            self.operation in {"create", "replace"},
            "REFUSE_PLAN_ACTION",
            "unsupported plan action",
        )
        require(
            isinstance(self.content, bytes) and len(self.content) <= 16 * 1024 * 1024,
            "REFUSE_PLAN_ACTION",
            "plan action content exceeds the sixteen MiB limit",
            path=self.path,
        )
        require(
            type(self.mode) is int and 0 <= self.mode <= 0o777,
            "REFUSE_PLAN_ACTION",
            "invalid plan action mode",
            path=self.path,
        )
        require(
            (self.operation == "create" and self.expected_sha256 is None)
            or (
                self.operation == "replace"
                and isinstance(self.expected_sha256, str)
                and bool(HEX64.fullmatch(self.expected_sha256))
            ),
            "REFUSE_PLAN_ACTION",
            "plan action precondition does not match its operation",
            path=self.path,
        )

    @property
    def sha256(self) -> str:
        return bytes_sha256(self.content)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bytes": len(self.content),
            "content_base64": canonical_b64(self.content),
            "expected_sha256": self.expected_sha256,
            "mode": self.mode,
            "operation": self.operation,
            "path": self.path,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, value: Any) -> FileAction:
        item = closed_object(
            value,
            required={
                "bytes",
                "content_base64",
                "expected_sha256",
                "mode",
                "operation",
                "path",
                "sha256",
            },
            where="file action",
        )
        content = decode_b64(item["content_base64"], where="file action content", limit=16 * 1024 * 1024)
        require(
            type(item["bytes"]) is int
            and item["bytes"] == len(content)
            and item["sha256"] == bytes_sha256(content),
            "REFUSE_PLAN_ACTION",
            "plan action content commitment mismatch",
            path=item.get("path"),
        )
        return cls(
            operation=item["operation"],
            path=item["path"],
            content=content,
            mode=item["mode"],
            expected_sha256=item["expected_sha256"],
        )


@dataclass(frozen=True)
class ReleasePlan:
    operation: Literal["scaffold", "update"]
    target: str
    subject: dict[str, Any]
    actions: tuple[FileAction, ...]
    preconditions: tuple[dict[str, Any], ...]

    SCHEMA = "rapp-work-release-plan/1"

    def __post_init__(self) -> None:
        require(
            self.operation in {"scaffold", "update"},
            "REFUSE_PLAN",
            "release plan operation must be scaffold or update",
        )
        require(
            str(absolute_path(self.target)) == self.target,
            "REFUSE_PLAN",
            "release plan target must be an absolute lexical path",
        )
        paths = [action.path for action in self.actions]
        require(
            paths == sorted(set(paths))
            and len(paths) <= 512
            and sum(len(action.content) for action in self.actions) <= 64 * 1024 * 1024,
            "REFUSE_PLAN",
            "release plan actions must be unique, sorted, and bounded",
        )
        require(
            len(self.preconditions) <= 128,
            "REFUSE_PLAN",
            "release plan preconditions exceed the fixed bound",
        )
        canonical_bytes(self.subject)
        canonical_bytes(list(self.preconditions))

    def to_dict(self) -> dict[str, Any]:
        return {
            "actions": [action.to_dict() for action in self.actions],
            "network": False,
            "operation": self.operation,
            "preconditions": list(self.preconditions),
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "schema": self.SCHEMA,
            "subject": self.subject,
            "target": self.target,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> ReleasePlan:
        item = closed_object(
            value,
            required={
                "actions",
                "network",
                "operation",
                "preconditions",
                "profile",
                "protocol",
                "schema",
                "subject",
                "target",
            },
            where="release plan",
        )
        require(
            item["schema"] == cls.SCHEMA
            and item["protocol"] == "rapp-work/1"
            and item["profile"] == "rapp-work-sdk/1"
            and item["network"] is False,
            "REFUSE_PLAN",
            "release plan contract mismatch",
        )
        require(
            isinstance(item["actions"], list)
            and isinstance(item["preconditions"], list)
            and isinstance(item["subject"], dict)
            and all(isinstance(value, dict) for value in item["preconditions"]),
            "REFUSE_PLAN",
            "release plan fields have the wrong shape",
        )
        return cls(
            operation=item["operation"],
            target=item["target"],
            subject=dict(item["subject"]),
            actions=tuple(FileAction.from_dict(action) for action in item["actions"]),
            preconditions=tuple(dict(value) for value in item["preconditions"]),
        )


@dataclass(frozen=True)
class SignedRelease:
    plan: ReleasePlan
    signer_rappid: str
    sig: str

    SCHEMA = "rapp-work-signed-release/1"

    def __post_init__(self) -> None:
        require(
            rappid_valid(self.signer_rappid),
            "REFUSE_SIGNED_RELEASE",
            "signed release signer is not a valid keyed RAPPID",
        )
        require(
            isinstance(self.sig, str) and 0 < len(self.sig) <= 8192,
            "REFUSE_SIGNED_RELEASE",
            "signed release requires a detached JWS",
        )

    def unsigned(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "plan_sha256": self.plan.sha256,
            "schema": self.SCHEMA,
            "signer_rappid": self.signer_rappid,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned(), "sig": self.sig}

    @classmethod
    def from_dict(cls, value: Any) -> SignedRelease:
        item = closed_object(
            value,
            required={"plan", "plan_sha256", "schema", "signer_rappid", "sig"},
            where="signed release",
        )
        require(
            item["schema"] == cls.SCHEMA,
            "REFUSE_SIGNED_RELEASE",
            "wrong signed release schema",
        )
        plan = ReleasePlan.from_dict(item["plan"])
        require(
            item["plan_sha256"] == plan.sha256,
            "REFUSE_SIGNED_RELEASE",
            "signed release plan hash mismatch",
        )
        return cls(plan=plan, signer_rappid=item["signer_rappid"], sig=item["sig"])

    def verify(self, spki_der: bytes) -> dict[str, Any]:
        ok, reason = verify_detached_jws(
            self.unsigned(),
            self.sig,
            spki_der,
            expected_kid=self.signer_rappid,
        )
        require(
            ok,
            "REFUSE_SIGNED_RELEASE",
            "signed release detached JWS verification failed",
            reason=reason,
        )
        return {
            "plan_sha256": self.plan.sha256,
            "signer_rappid": self.signer_rappid,
            "status": "verified",
        }


def fold_path(value: str) -> str:
    """Caseless, normalization-insensitive key used to detect aliases and protected names."""
    return unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", value).casefold())


def canonical_move_path(value: Any) -> str:
    path = safe_relative(value)
    pure = PurePosixPath(path)
    require(
        bool(pure.parts) and pure.as_posix() == path,
        "REFUSE_PATH",
        "move path must be a canonical relative path",
        path=path,
    )
    return path


def move_path_protection(path: str) -> str | None:
    """Return why a move may not name ``path``, or ``None`` when it is ordinary content."""
    parts = [fold_path(part) for part in PurePosixPath(path).parts]
    if any(part.startswith(".") for part in parts):
        return "hidden-path"
    if "rappid.json" in parts:
        return "identity-file"
    if len(parts) == 1 and parts[0] in PROTECTED_ROOT_FILES:
        return "authority-file"
    if parts[-1] in INSTRUCTION_NAMES or parts[-1].endswith(INSTRUCTION_SUFFIXES):
        return "instruction-file"
    return None


def require_movable_path(value: Any) -> str:
    path = canonical_move_path(value)
    reason = move_path_protection(path)
    require(
        reason is None,
        "REFUSE_MOVE_PROTECTED",
        "move path names SDK authority, instruction, or hidden state",
        path=path,
        reason=reason,
    )
    return path


def require_disjoint_moves(pairs: list[tuple[str, str]]) -> None:
    sources = [fold_path(source) for source, _ in pairs]
    destinations = [fold_path(destination) for _, destination in pairs]
    require(
        len(set(sources)) == len(sources)
        and len(set(destinations)) == len(destinations)
        and not set(sources) & set(destinations),
        "REFUSE_MOVE_PLAN",
        "move sources and destinations must be distinct and never chain, swap, or alias",
    )


@dataclass(frozen=True)
class FileMove:
    source: str
    destination: str
    sha256: str
    size: int
    mode: int

    def __post_init__(self) -> None:
        require_movable_path(self.source)
        require_movable_path(self.destination)
        require_disjoint_moves([(self.source, self.destination)])
        require(
            isinstance(self.sha256, str) and bool(HEX64.fullmatch(self.sha256)),
            "REFUSE_MOVE_PLAN",
            "move content hash must be 64 lowercase hexadecimal characters",
            path=self.source,
        )
        require(
            type(self.size) is int and 0 <= self.size <= MAX_FILE_BYTES,
            "REFUSE_MOVE_PLAN",
            "move byte length exceeds the sixteen MiB limit",
            path=self.source,
        )
        require(
            type(self.mode) is int and 0 <= self.mode <= 0o777,
            "REFUSE_MOVE_PLAN",
            "move mode must be permission bits without setuid, setgid, or sticky bits",
            path=self.source,
        )

    def inverse(self) -> FileMove:
        return FileMove(
            source=self.destination,
            destination=self.source,
            sha256=self.sha256,
            size=self.size,
            mode=self.mode,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bytes": self.size,
            "destination": self.destination,
            "mode": self.mode,
            "operation": "move",
            "sha256": self.sha256,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Any) -> FileMove:
        item = closed_object(
            value,
            required={"bytes", "destination", "mode", "operation", "sha256", "source"},
            where="move action",
        )
        require(item["operation"] == "move", "REFUSE_MOVE_PLAN", "move action must be a move")
        return cls(
            source=item["source"],
            destination=item["destination"],
            sha256=item["sha256"],
            size=item["bytes"],
            mode=item["mode"],
        )


def _move_preconditions(value: Any) -> dict[str, Any]:
    item = closed_object(
        value,
        required={"identity_sha256", "managed_sha256", "root_identity"},
        where="move plan preconditions",
    )
    root = closed_object(
        item["root_identity"],
        required={"device", "inode", "mode"},
        where="move plan root identity",
    )
    require(
        all(
            isinstance(item[key], str) and bool(HEX64.fullmatch(item[key]))
            for key in ("identity_sha256", "managed_sha256")
        )
        and all(type(root[key]) is int and root[key] >= 0 for key in ("device", "inode", "mode")),
        "REFUSE_MOVE_PLAN",
        "move plan preconditions are invalid",
    )
    return {
        "identity_sha256": item["identity_sha256"],
        "managed_sha256": item["managed_sha256"],
        "root_identity": {key: root[key] for key in ("device", "inode", "mode")},
    }


def _move_subject(value: Any) -> dict[str, Any]:
    item = closed_object(value, required={"kind", "rappid", "world_id"}, where="move plan subject")
    require(
        item["kind"] in {"workspace", "organization"}
        and rappid_valid(item["rappid"])
        and isinstance(item["world_id"], str)
        and bool(LABEL.fullmatch(item["world_id"])),
        "REFUSE_MOVE_PLAN",
        "move plan subject is invalid",
    )
    return {key: item[key] for key in ("kind", "rappid", "world_id")}


@dataclass(frozen=True)
class MovePlan:
    """``rapp-work-move-plan/1``: relocate existing files; bytes stay where they are."""

    target: str
    subject: dict[str, Any]
    preconditions: dict[str, Any]
    moves: tuple[FileMove, ...]

    SCHEMA = "rapp-work-move-plan/1"

    def __post_init__(self) -> None:
        require(
            isinstance(self.target, str) and str(absolute_path(self.target)) == self.target,
            "REFUSE_MOVE_PLAN",
            "move plan target must be an absolute lexical path",
        )
        object.__setattr__(self, "subject", _move_subject(self.subject))
        object.__setattr__(self, "preconditions", _move_preconditions(self.preconditions))
        require(
            isinstance(self.moves, tuple)
            and 1 <= len(self.moves) <= MAX_MOVES
            and all(isinstance(move, FileMove) for move in self.moves),
            "REFUSE_MOVE_PLAN",
            "move plan requires one to sixty-four moves",
        )
        sources = [move.source for move in self.moves]
        require(
            sources == sorted(sources),
            "REFUSE_MOVE_PLAN",
            "move plan moves must be sorted by source",
        )
        require_disjoint_moves([(move.source, move.destination) for move in self.moves])
        require(
            sum(move.size for move in self.moves) <= MAX_MOVE_TOTAL_BYTES,
            "REFUSE_MOVE_PLAN",
            "move plan exceeds the sixty-four MiB total bound",
        )
        canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "moves": [move.to_dict() for move in self.moves],
            "network": False,
            "operation": "update",
            "preconditions": {
                "identity_sha256": self.preconditions["identity_sha256"],
                "managed_sha256": self.preconditions["managed_sha256"],
                "root_identity": dict(self.preconditions["root_identity"]),
            },
            "profile": "rapp-work-sdk/1",
            "protocol": "rapp-work/1",
            "schema": self.SCHEMA,
            "subject": dict(self.subject),
            "target": self.target,
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def inverse(self) -> MovePlan:
        """The exact undo: every move reversed, same bytes; the inverse of the inverse is self."""
        return MovePlan(
            target=self.target,
            subject=dict(self.subject),
            preconditions=self.to_dict()["preconditions"],
            moves=tuple(
                sorted((move.inverse() for move in self.moves), key=lambda move: move.source)
            ),
        )

    @classmethod
    def from_dict(cls, value: Any) -> MovePlan:
        item = closed_object(
            value,
            required={
                "moves",
                "network",
                "operation",
                "preconditions",
                "profile",
                "protocol",
                "schema",
                "subject",
                "target",
            },
            where="move plan",
        )
        require(
            item["schema"] == cls.SCHEMA
            and item["protocol"] == "rapp-work/1"
            and item["profile"] == "rapp-work-sdk/1"
            and item["network"] is False
            and item["operation"] == "update",
            "REFUSE_MOVE_PLAN",
            "move plan contract mismatch",
        )
        require(
            isinstance(item["moves"], list) and 1 <= len(item["moves"]) <= MAX_MOVES,
            "REFUSE_MOVE_PLAN",
            "move plan requires one to sixty-four moves",
        )
        return cls(
            target=item["target"],
            subject=item["subject"],
            preconditions=item["preconditions"],
            moves=tuple(FileMove.from_dict(move) for move in item["moves"]),
        )
