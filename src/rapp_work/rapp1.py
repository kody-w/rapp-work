from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from ._paths import read_regular
from ._resources import data_file, source_root, vendor_root
from .errors import Refusal, require

FRAME_KEYS = frozenset(
    {
        "spec",
        "kind",
        "stream_id",
        "seq",
        "utc",
        "payload",
        "payload_hash",
        "frame_hash",
        "prev",
        "prev_wave",
        "sig",
    }
)

SignatureVerifier = Callable[..., bool | tuple[bool, str]]


def _pin() -> dict[str, Any]:
    checkout = source_root()
    path = checkout / "RAPP1_PIN.json" if checkout is not None else data_file("RAPP1_PIN.json")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RuntimeError(f"duplicate RAPP/1 pin member: {key}")
            result[key] = item
        return result

    value = json.loads(read_regular(path), object_pairs_hook=reject_duplicates)
    if not isinstance(value, dict) or value.get("schema") != "rapp-work-parent-pin/1":
        raise RuntimeError("invalid packaged RAPP/1 pin")
    return value


def _load_reference() -> ModuleType:
    root = vendor_root()
    pin = _pin()
    implementation = root / "rapp.py"
    specification = root / "SPEC.md"
    implementation_bytes = read_regular(implementation)
    specification_bytes = read_regular(specification)
    if hashlib.sha256(implementation_bytes).hexdigest() != pin["reference_sha256"]:
        raise RuntimeError("pinned RAPP/1 implementation hash mismatch")
    if hashlib.sha256(specification_bytes).hexdigest() != pin["spec_sha256"]:
        raise RuntimeError("pinned RAPP/1 specification hash mismatch")
    module = ModuleType("rapp_work._pinned_rapp1")
    module.__file__ = str(implementation)
    exec(compile(implementation_bytes, str(implementation), "exec"), module.__dict__)
    return module


_R = _load_reference()

canonical = _R.canonical
hash_json = _R.H
hash_bytes = _R.Hb
mint_rappid = _R.mint_rappid
rappid_valid = _R.rappid_valid
rappid_parts = _R.rappid_parts
utc_valid = _R.utc_valid
verify_detached_jws = _R.verify_detached_jws


@dataclass(frozen=True)
class RappFrame:
    """Typed view over the canonical implementation's frozen eleven-key envelope."""

    _value: dict[str, Any]

    @classmethod
    def parse(
        cls,
        value: Mapping[str, Any],
        *,
        head: RappFrame | Mapping[str, Any] | None = None,
        stream_id_of_record: str | None = None,
        signature_verifier: SignatureVerifier | None = None,
    ) -> RappFrame:
        frame = copy.deepcopy(dict(value))
        require(
            set(frame) == FRAME_KEYS,
            "REFUSE_RAPP_FRAME_KEYS",
            "RAPP/1 frame must have exactly the frozen eleven-key envelope",
            actual=sorted(frame),
            expected=sorted(FRAME_KEYS),
        )
        head_value = head._value if isinstance(head, RappFrame) else head
        ok, step, reason = _R.verify_frame(
            frame,
            head=head_value,
            stream_id_of_record=stream_id_of_record,
            signature_verifier=signature_verifier,
        )
        require(
            bool(ok),
            "REFUSE_RAPP_FRAME",
            "canonical RAPP/1 frame verification failed",
            reason=reason,
            step=step,
        )
        return cls(frame)

    @property
    def frame_hash(self) -> str:
        return str(self._value["frame_hash"])

    @property
    def payload_hash(self) -> str:
        return str(self._value["payload_hash"])

    @property
    def seq(self) -> int:
        return int(self._value["seq"])

    @property
    def stream_id(self) -> str:
        return str(self._value["stream_id"])

    @property
    def value(self) -> dict[str, Any]:
        return copy.deepcopy(self._value)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._value)

    def canonical_bytes(self) -> bytes:
        return str(canonical(self._value)).encode("utf-8")


def build_frame(
    *,
    kind: str,
    stream_id: str,
    seq: int,
    utc: str,
    payload: Mapping[str, Any],
    prev: str | None,
    prev_wave: str | None = None,
    sig: str | None = None,
    head: RappFrame | Mapping[str, Any] | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> RappFrame:
    value = _R.build_frame(
        kind,
        stream_id,
        seq,
        utc,
        dict(payload),
        prev,
        prev_wave=prev_wave,
        sig=sig,
    )
    return RappFrame.parse(
        value,
        head=head,
        stream_id_of_record=stream_id,
        signature_verifier=signature_verifier,
    )


def validate_frame(
    value: Mapping[str, Any],
    *,
    head: RappFrame | Mapping[str, Any] | None = None,
    stream_id_of_record: str | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> RappFrame:
    return RappFrame.parse(
        value,
        head=head,
        stream_id_of_record=stream_id_of_record,
        signature_verifier=signature_verifier,
    )


def validate_chain(
    frames: Sequence[Mapping[str, Any]],
    *,
    stream_id: str | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> tuple[RappFrame, ...]:
    require(bool(frames), "REFUSE_RAPP_CHAIN", "RAPP/1 chain must contain a genesis frame")
    checked: list[RappFrame] = []
    head: RappFrame | None = None
    bound_stream = stream_id
    for value in frames:
        frame = validate_frame(
            value,
            head=head,
            stream_id_of_record=bound_stream,
            signature_verifier=signature_verifier,
        )
        if bound_stream is None:
            bound_stream = frame.stream_id
        checked.append(frame)
        head = frame
    return tuple(checked)


def pinned_parent() -> dict[str, Any]:
    return dict(_pin())


def canonical_reference_path() -> Path:
    return vendor_root() / "rapp.py"


def canonical_reference_sha256() -> str:
    return hashlib.sha256(read_regular(canonical_reference_path())).hexdigest()


def refusal_from_verify(error: ValueError) -> Refusal:
    return Refusal("REFUSE_RAPP_CANONICAL", str(error))
