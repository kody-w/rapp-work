from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn


@dataclass
class Refusal(Exception):
    """A fail-closed, machine-readable refusal with no implied effects."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "details": self.details,
            "message": self.message,
        }


def refuse(code: str, message: str, **details: Any) -> NoReturn:
    raise Refusal(code, message, details or None)


def require(condition: bool, code: str, message: str, **details: Any) -> None:
    if not condition:
        refuse(code, message, **details)
