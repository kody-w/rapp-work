"""Shared validation helpers for RAPP operational profiles."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import rapp as R


HEX64 = re.compile(r"^[0-9a-f]{64}$")
LOWER_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact_keys(value: object, keys: set[str], where: str) -> dict:
    require(isinstance(value, dict), f"{where}: expected object")
    actual = set(value)
    require(actual == keys, f"{where}: expected keys {sorted(keys)}, got {sorted(actual)}")
    return value


def canonical_object(value: object, where: str) -> dict:
    require(isinstance(value, dict), f"{where}: expected object")
    stack = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        require(depth <= 64, f"{where}: I-JSON nesting depth exceeds 64")
        if isinstance(current, dict):
            require(all(isinstance(key, str) for key in current), f"{where}: object keys must be strings")
            stack.extend((item, depth + 1) for item in current.values())
            stack.extend((key, depth + 1) for key in current)
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            require(unicodedata.normalize("NFC", current) == current, f"{where}: strings must be NFC")
    require(len(R.canonical(value).encode("utf-8")) <= R.MAX_CANONICAL_BYTES,
            f"{where}: canonical object exceeds 1 MiB")
    return value


def text(value: object, where: str, *, maximum: int = 256) -> str:
    require(isinstance(value, str), f"{where}: expected string")
    require(0 < len(value) <= maximum, f"{where}: length must be 1..{maximum}")
    require(unicodedata.normalize("NFC", value) == value, f"{where}: must be NFC")
    return value


def label(value: object, where: str) -> str:
    value = text(value, where, maximum=64)
    require(bool(LOWER_LABEL.fullmatch(value)), f"{where}: expected lowercase label")
    return value


def hex64(value: object, where: str) -> str:
    require(isinstance(value, str) and bool(HEX64.fullmatch(value)), f"{where}: expected 64 lowercase hex")
    return value


def grail_id(value: object, where: str) -> str:
    require(
        isinstance(value, str)
        and value.startswith("grail:")
        and bool(HEX64.fullmatch(value[len("grail:"):])),
        f"{where}: expected grail:<64 lowercase hex>",
    )
    return value


def positive_int(value: object, where: str, *, allow_zero: bool = False) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{where}: expected integer")
    minimum = 0 if allow_zero else 1
    require(value >= minimum, f"{where}: expected integer >= {minimum}")
    return value


def bounded_int(value: object, where: str, minimum: int, maximum: int) -> int:
    positive_int(value, where, allow_zero=minimum == 0)
    require(minimum <= value <= maximum, f"{where}: expected {minimum}..{maximum}")
    return value


def boolean(value: object, where: str) -> bool:
    require(isinstance(value, bool), f"{where}: expected boolean")
    return value


def utc(value: object, where: str) -> datetime:
    require(isinstance(value, str) and bool(UTC.fullmatch(value)), f"{where}: expected RAPP UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"{where}: invalid calendar timestamp") from error
    return parsed


def https_uri(value: object, where: str) -> str:
    value = text(value, where, maximum=2048)
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and bool(parsed.netloc), f"{where}: expected absolute HTTPS URI")
    require(not parsed.username and not parsed.password, f"{where}: credentials are forbidden")
    return value


def relative_path(value: object, where: str) -> str:
    value = text(value, where, maximum=1024)
    require("\\" not in value, f"{where}: expected POSIX path")
    require(all(part not in ("", ".", "..") for part in value.split("/")), f"{where}: unsafe path component")
    require(R._path_valid(value) and "\x7f" not in value, f"{where}: unsafe portable path")
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"{where}: absolute path forbidden")
    require(all(part not in ("", ".", "..") for part in path.parts), f"{where}: unsafe path component")
    require(str(path) == value, f"{where}: path must already be canonical")
    return value


def object_id(value: object, object_format: str, where: str) -> str:
    length = {"sha1": 40, "sha256": 64}.get(object_format)
    require(length is not None, f"{where}: unsupported object format")
    require(
        isinstance(value, str)
        and len(value) == length
        and all(ch in "0123456789abcdef" for ch in value),
        f"{where}: expected {length} lowercase hex",
    )
    return value


def unique_strings(values: object, where: str, *, labels: bool = False) -> list[str]:
    require(isinstance(values, list), f"{where}: expected array")
    checked = []
    for index, value in enumerate(values):
        checked.append(label(value, f"{where}[{index}]") if labels else text(value, f"{where}[{index}]"))
    require(len(checked) == len(set(checked)), f"{where}: duplicate values are forbidden")
    return checked


def particle_hash(payload: dict) -> str:
    return R.H("rapp/1:particle", payload)


def authoritative_frame_payload(
    frame: dict,
    *,
    expected_schema: str,
    purpose: str,
    head: dict | None,
    stream_id: str,
    registered_kinds: set[str],
    signature_verifier,
    authorization_verifier,
) -> dict:
    require(signature_verifier is not None, f"{purpose}: signature verifier is required")
    require(authorization_verifier is not None, f"{purpose}: authorization verifier is required")
    require(frame.get("kind") in registered_kinds, f"{purpose}: frame kind is not registered")
    require(frame.get("sig") is not None, f"{purpose}: authoritative frame must be signed")
    ok, step, why = R.verify_frame(
        frame,
        head=head,
        stream_id_of_record=stream_id,
        signature_verifier=signature_verifier,
    )
    require(ok, f"{purpose}: RAPP frame refusal at step {step}: {why}")
    payload = canonical_object(frame["payload"], f"{purpose}.payload")
    require(payload.get("schema") == expected_schema, f"{purpose}: unexpected payload schema")
    require(authorization_verifier(frame, purpose) is True, f"{purpose}: signer is not authorized")
    return payload


def load_json(path: str) -> dict:
    with open(path, "rb") as stream:
        value = R._strict_json(stream.read())
    return canonical_object(value, path)
