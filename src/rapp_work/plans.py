from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from ._json import (
    bytes_sha256,
    canonical_b64,
    canonical_bytes,
    canonical_sha256,
    closed_object,
    decode_b64,
)
from ._paths import absolute_path, safe_relative
from .errors import require
from .rapp1 import rappid_valid, verify_detached_jws

HEX64 = re.compile(r"^[0-9a-f]{64}$")
ActionKind = Literal["create", "replace"]


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
