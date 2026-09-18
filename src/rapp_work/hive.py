from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ._json import canonical_sha256, closed_object, decode_b64, strict_json_loads
from .errors import require
from .rapp1 import hash_json, rappid_valid, verify_detached_jws

HEX64 = re.compile(r"^[0-9a-f]{64}$")
REGISTRY_HISTORY_PATH = re.compile(r"^registry-history/([1-9][0-9]*)-([0-9a-f]{64})\.json$")
MAX_VECTOR_STREAMS = 256
MAX_STREAM_HISTORY = 4096
MAX_REGISTRY_HISTORY = 4096


@dataclass(frozen=True)
class HiveStreamPosition:
    stream_id: str
    seq: int
    frame_hash: str
    history: tuple[str, ...]

    def __post_init__(self) -> None:
        require(
            rappid_valid(self.stream_id),
            "REFUSE_HIVE_VECTOR",
            "Hive vector stream is not a RAPPID",
            stream_id=self.stream_id,
        )
        require(
            type(self.seq) is int and 0 <= self.seq < MAX_STREAM_HISTORY,
            "REFUSE_HIVE_VECTOR",
            "Hive vector stream sequence is out of bounds",
            stream_id=self.stream_id,
        )
        require(
            len(self.history) == self.seq + 1
            and len(self.history) <= MAX_STREAM_HISTORY
            and len(set(self.history)) == len(self.history)
            and all(bool(HEX64.fullmatch(value)) for value in self.history)
            and self.history[-1] == self.frame_hash,
            "REFUSE_HIVE_VECTOR",
            "Hive vector history is incomplete, duplicated, or inconsistent",
            stream_id=self.stream_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_hash": self.frame_hash,
            "history": list(self.history),
            "seq": self.seq,
            "stream_id": self.stream_id,
        }

    @classmethod
    def from_dict(cls, value: Any) -> HiveStreamPosition:
        item = closed_object(
            value,
            required={"frame_hash", "history", "seq", "stream_id"},
            where="Hive stream vector",
        )
        require(
            isinstance(item["history"], list),
            "REFUSE_HIVE_VECTOR",
            "Hive stream history must be an array",
        )
        return cls(
            stream_id=item["stream_id"],
            seq=item["seq"],
            frame_hash=item["frame_hash"],
            history=tuple(item["history"]),
        )


@dataclass(frozen=True)
class HiveVector:
    hive_rappid: str
    registry_seq: int
    registry_hash: str
    streams: tuple[HiveStreamPosition, ...]
    registry_history: tuple[tuple[int, str], ...] = ()

    SCHEMA = "rapp-work-hive-vector/1"

    def __post_init__(self) -> None:
        require(
            rappid_valid(self.hive_rappid),
            "REFUSE_HIVE_VECTOR",
            "Hive vector identity is not a RAPPID",
        )
        require(
            type(self.registry_seq) is int and 0 <= self.registry_seq <= 2**53 - 1,
            "REFUSE_HIVE_VECTOR",
            "Hive registry sequence is not uint53",
        )
        require(
            bool(HEX64.fullmatch(self.registry_hash)),
            "REFUSE_HIVE_VECTOR",
            "Hive registry hash is invalid",
        )
        history = self.registry_history or ((self.registry_seq, self.registry_hash),)
        require(
            all(
                type(seq) is int and 0 <= seq <= 2**53 - 1 and bool(HEX64.fullmatch(value))
                for seq, value in history
            )
            and [seq for seq, _ in history]
            == list(range(history[0][0], history[-1][0] + 1))
            and history[-1] == (self.registry_seq, self.registry_hash),
            "REFUSE_HIVE_VECTOR",
            "Hive registry history is incomplete or inconsistent",
        )
        object.__setattr__(self, "registry_history", history)
        require(
            1 <= len(self.streams) <= MAX_VECTOR_STREAMS
            and [value.stream_id for value in self.streams]
            == sorted({value.stream_id for value in self.streams}),
            "REFUSE_HIVE_VECTOR",
            "Hive vector streams must be nonempty, unique, bounded, and sorted",
        )
        require(
            any(value.stream_id == self.hive_rappid for value in self.streams),
            "REFUSE_HIVE_VECTOR",
            "Hive vector omits the Mother Hive stream",
        )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "hive_rappid": self.hive_rappid,
            "registry": {
                "hash": self.registry_hash,
                "history": [
                    {"hash": value, "seq": seq}
                    for seq, value in self.registry_history
                ],
                "seq": self.registry_seq,
            },
            "schema": self.SCHEMA,
            "streams": [stream.to_dict() for stream in self.streams],
        }

    @classmethod
    def from_dict(cls, value: Any) -> HiveVector:
        item = closed_object(
            value,
            required={"hive_rappid", "registry", "schema", "streams"},
            where="Hive vector",
        )
        require(
            item["schema"] == cls.SCHEMA and isinstance(item["streams"], list),
            "REFUSE_HIVE_VECTOR",
            "wrong Hive vector schema",
        )
        registry = closed_object(
            item["registry"],
            required={"hash", "history", "seq"},
            where="Hive vector registry",
        )
        require(
            isinstance(registry["history"], list),
            "REFUSE_HIVE_VECTOR",
            "Hive registry history must be an array",
        )
        registry_history = []
        for raw in registry["history"]:
            entry = closed_object(
                raw,
                required={"hash", "seq"},
                where="Hive registry history entry",
            )
            registry_history.append((entry["seq"], entry["hash"]))
        streams = tuple(HiveStreamPosition.from_dict(value) for value in item["streams"])
        return cls(
            hive_rappid=item["hive_rappid"],
            registry_seq=registry["seq"],
            registry_hash=registry["hash"],
            streams=streams,
            registry_history=tuple(registry_history),
        )

    @classmethod
    def from_verified_bundle(cls, bundle: Any) -> HiveVector:
        pointer = bundle.pointer
        require(
            isinstance(bundle.files, dict) and isinstance(bundle.anchor, dict),
            "REFUSE_HIVE_VECTOR",
            "verified bundle does not expose authenticated registry artifacts",
        )
        owner_rappid = bundle.anchor.get("owner_rappid")
        require(
            rappid_valid(owner_rappid),
            "REFUSE_HIVE_VECTOR",
            "verified bundle owner identity is invalid",
        )
        owner_spki = decode_b64(
            bundle.anchor.get("spki_der_b64"),
            where="verified Hive owner SPKI",
            limit=16 * 1024,
        )
        registry_history: list[tuple[int, str]] = []
        for path, raw in bundle.files.items():
            match = REGISTRY_HISTORY_PATH.fullmatch(path)
            if match is None:
                continue
            require(
                isinstance(raw, bytes),
                "REFUSE_HIVE_VECTOR",
                "verified registry history artifact must be bytes",
                path=path,
            )
            document = closed_object(
                strict_json_loads(raw, where="verified Hive registry history"),
                required={"canonical_source", "entries", "registry_seq", "schema", "sig"},
                where="verified Hive registry history",
            )
            sequence = document["registry_seq"]
            require(
                document["schema"] == "rapp/1-registry"
                and type(sequence) is int
                and 1 <= sequence <= 2**53 - 1
                and sequence == int(match.group(1)),
                "REFUSE_HIVE_VECTOR",
                "verified registry history sequence is invalid",
                path=path,
            )
            unsigned = {key: value for key, value in document.items() if key != "sig"}
            ok, reason = verify_detached_jws(
                unsigned,
                document["sig"],
                owner_spki,
                expected_kid=owner_rappid,
            )
            require(
                ok,
                "REFUSE_HIVE_VECTOR",
                "verified registry lineage signature refused",
                path=path,
                reason=reason,
            )
            require(
                hash_json("rapp/1:particle", document) == match.group(2),
                "REFUSE_HIVE_VECTOR",
                "verified registry history address mismatch",
                path=path,
            )
            registry_history.append(
                (sequence, hash_json("rapp/1:particle", unsigned))
            )
        registry_history.sort()
        require(
            1 <= len(registry_history) <= MAX_REGISTRY_HISTORY
            and [sequence for sequence, _ in registry_history]
            == list(range(registry_history[0][0], registry_history[-1][0] + 1))
            and registry_history[-1]
            == (pointer["registry"]["seq"], pointer["registry"]["hash"]),
            "REFUSE_HIVE_VECTOR",
            "verified bundle registry lineage is incomplete or inconsistent",
        )
        by_stream: dict[str, list[dict[str, Any]]] = {}
        for frame in bundle.gate._retained.values():
            by_stream.setdefault(frame["stream_id"], []).append(frame)
        for projection in pointer["projections"]:
            for raw in bundle.resolver.chain(projection["frame_hash"]):
                frame = strict_json_loads(raw, where="verified Hive frame")
                require(
                    isinstance(frame, dict),
                    "REFUSE_HIVE_VECTOR",
                    "verified Hive frame must be an object",
                )
                by_stream.setdefault(frame["stream_id"], []).append(frame)
        positions: list[HiveStreamPosition] = []
        for stream_id, frames in by_stream.items():
            unique = {frame["frame_hash"]: frame for frame in frames}
            ordered = sorted(unique.values(), key=lambda frame: frame["seq"])
            require(
                [frame["seq"] for frame in ordered] == list(range(len(ordered))),
                "REFUSE_HIVE_VECTOR",
                "verified bundle retained an incomplete stream",
                stream_id=stream_id,
            )
            positions.append(
                HiveStreamPosition(
                    stream_id=stream_id,
                    seq=ordered[-1]["seq"],
                    frame_hash=ordered[-1]["frame_hash"],
                    history=tuple(frame["frame_hash"] for frame in ordered),
                )
            )
        positions.sort(key=lambda value: value.stream_id)
        return cls(
            hive_rappid=pointer["hive_rappid"],
            registry_seq=pointer["registry"]["seq"],
            registry_hash=pointer["registry"]["hash"],
            streams=tuple(positions),
            registry_history=tuple(registry_history),
        )


def verify_hive_high_water(current: HiveVector, retained: HiveVector) -> dict[str, Any]:
    require(
        current.hive_rappid == retained.hive_rappid,
        "REFUSE_HIVE_IDENTITY",
        "Hive high-water comparison crossed identities",
    )
    require(
        current.registry_seq >= retained.registry_seq,
        "REFUSE_HIVE_ROLLBACK",
        "Hive registry sequence rolled back",
    )
    current_registry = dict(current.registry_history)
    require(
        current_registry.get(retained.registry_seq) == retained.registry_hash,
        "REFUSE_HIVE_FORK",
        "Hive registry lineage does not retain the accepted authority",
    )
    retained_streams = {value.stream_id: value for value in retained.streams}
    current_streams = {value.stream_id: value for value in current.streams}
    require(
        set(retained_streams) <= set(current_streams),
        "REFUSE_HIVE_ROLLBACK",
        "Hive vector dropped a retained stream",
        missing=sorted(set(retained_streams) - set(current_streams)),
    )
    for stream_id, previous in retained_streams.items():
        latest = current_streams[stream_id]
        require(
            latest.seq >= previous.seq,
            "REFUSE_HIVE_ROLLBACK",
            "Hive stream sequence rolled back",
            stream_id=stream_id,
        )
        require(
            latest.history[: previous.seq + 1] == previous.history,
            "REFUSE_HIVE_FORK",
            "Hive stream lineage does not retain the accepted head",
            stream_id=stream_id,
        )
    return {
        "current_sha256": current.sha256,
        "hive_rappid": current.hive_rappid,
        "retained_sha256": retained.sha256,
        "status": "verified-high-water",
        "streams": len(current.streams),
    }


@dataclass(frozen=True)
class HiveHighWater:
    vector: HiveVector

    def accept(self, candidate: HiveVector) -> HiveHighWater:
        verify_hive_high_water(candidate, self.vector)
        return HiveHighWater(candidate)
