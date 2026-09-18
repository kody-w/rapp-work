from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Any, cast

from .errors import Refusal, require

MAX_JSON_BYTES = 1024 * 1024


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise Refusal("REFUSE_JSON_DUPLICATE", "duplicate JSON object member", {"key": key})
        value[key] = item
    return value


def strict_json_loads(raw: bytes | str, *, where: str = "JSON") -> Any:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    require(
        isinstance(data, bytes) and len(data) <= MAX_JSON_BYTES,
        "REFUSE_JSON_LIMIT",
        f"{where} exceeds the one MiB input limit",
    )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise Refusal("REFUSE_JSON_UTF8", f"{where} is not UTF-8") from error
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicates,
            parse_float=lambda value: (_ for _ in ()).throw(
                Refusal("REFUSE_JSON_FLOAT", f"{where} contains a floating-point number")
            ),
            parse_constant=lambda value: (_ for _ in ()).throw(
                Refusal("REFUSE_JSON_CONSTANT", f"{where} contains {value}")
            ),
        )
    except Refusal:
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise Refusal("REFUSE_JSON_INVALID", f"{where} is invalid JSON") from error


def closed_object(
    value: Any,
    *,
    required: set[str],
    optional: set[str] | None = None,
    where: str,
) -> dict[str, Any]:
    require(isinstance(value, dict), "REFUSE_INPUT_SHAPE", f"{where} must be an object")
    optional = optional or set()
    keys = set(value)
    unknown = sorted(keys - required - optional)
    missing = sorted(required - keys)
    require(
        not unknown and not missing,
        "REFUSE_INPUT_KEYS",
        f"{where} has a non-closed key set",
        missing=missing,
        unknown=unknown,
    )
    return cast(dict[str, Any], value)


def canonical_bytes(value: Any) -> bytes:
    from .rapp1 import canonical

    try:
        return cast(str, canonical(value)).encode("utf-8")
    except ValueError as error:
        raise Refusal("REFUSE_NON_CANONICAL_VALUE", str(error)) from error


def canonical_text(value: Any) -> str:
    return canonical_bytes(value).decode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode_b64(value: Any, *, where: str, limit: int = MAX_JSON_BYTES) -> bytes:
    require(isinstance(value, str), "REFUSE_BASE64", f"{where} must be base64 text")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise Refusal("REFUSE_BASE64", f"{where} is not canonical base64") from error
    require(
        len(result) <= limit and canonical_b64(result) == value,
        "REFUSE_BASE64",
        f"{where} is noncanonical or too large",
    )
    return result


def canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return dict(value)
