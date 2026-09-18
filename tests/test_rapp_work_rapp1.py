from __future__ import annotations

import copy
import hashlib

import pytest

from rapp_work import FRAME_KEYS, build_frame, pinned_parent, validate_chain, validate_frame
from rapp_work.errors import Refusal
from rapp_work.rapp1 import canonical_reference_path, canonical_reference_sha256, mint_rappid


def frame(stream: str, seq: int, previous=None):
    return build_frame(
        kind="work.event",
        stream_id=stream,
        seq=seq,
        utc=f"2026-09-18T12:00:0{seq}.000Z",
        payload={"seq": seq},
        prev=None if previous is None else previous.payload_hash,
        head=previous,
    )


def test_wrapper_loads_exact_pinned_reference() -> None:
    pin = pinned_parent()
    assert canonical_reference_sha256() == pin["reference_sha256"]
    assert hashlib.sha256(canonical_reference_path().read_bytes()).hexdigest() == pin["reference_sha256"]


def test_build_and_validate_exact_eleven_keys() -> None:
    built = frame(mint_rappid("example", "stream"), 0)
    assert set(built.to_dict()) == FRAME_KEYS
    assert validate_frame(built.to_dict()).frame_hash == built.frame_hash
    exposed = built.value
    exposed["payload"]["seq"] = 999
    assert built.value["payload"]["seq"] == 0


@pytest.mark.parametrize("mutation", ["extra", "missing", "boolean-seq", "particle", "wave"])
def test_frame_mutations_refuse(mutation: str) -> None:
    value = frame(mint_rappid("example", "stream"), 0).to_dict()
    if mutation == "extra":
        value["extension"] = {}
    elif mutation == "missing":
        value.pop("sig")
    elif mutation == "boolean-seq":
        value["seq"] = False
    elif mutation == "particle":
        value["payload"]["seq"] = 2
    else:
        value["frame_hash"] = "0" * 64
    with pytest.raises(Refusal):
        validate_frame(value)


def test_chain_uses_canonical_parent_semantics() -> None:
    stream = mint_rappid("example", "chain")
    genesis = frame(stream, 0)
    successor = frame(stream, 1, genesis)
    checked = validate_chain([genesis.to_dict(), successor.to_dict()], stream_id=stream)
    assert [value.seq for value in checked] == [0, 1]
    fork = copy.deepcopy(successor.to_dict())
    fork["prev"] = "0" * 64
    with pytest.raises(Refusal):
        validate_chain([genesis.to_dict(), fork], stream_id=stream)
