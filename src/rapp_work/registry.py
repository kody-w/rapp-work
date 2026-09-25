"""Read-only RAPP/1 section 13 registry verification across owner succession.

The SDK never mints, signs, appends, or rewrites a registry. It verifies a
signed ``rapp/1-registry`` document with the pinned RAPP/1 registry reference
named by ``RAPP1_REGISTRY_PIN.json``: exact section 13.3 entries, owner tenure,
lifecycle signatures, and time-scoped key retirement. The caller supplies the
out-of-band anchor, a trusted tombstone issuance resolver, and the registry
state it retained from its last verification; none is read from the untrusted
document.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from . import rapp1
from ._json import strict_json_loads
from ._paths import read_regular
from ._resources import data_file, source_root, vendor_root
from .errors import Refusal, require

SUCCESSION_PROFILE = "rapp1-13.2"
REGISTRY_PIN_SCHEMA = "rapp-work-parent-registry-pin/1"
REGISTRY_PIN_KEYS = frozenset(
    {"commit", "protocol", "reference_path", "reference_sha256", "repository", "schema"}
)
RETAINED_KEYS = frozenset(
    {
        "anchor",
        "commitment",
        "estate_owner",
        "lifecycle",
        "owner_lineage",
        "profile",
        "registry_seq",
        "status",
    }
)
OWNER_SUCCESSION_CASES = frozenset({"rotation", "compromise"})
LIFECYCLE_TYPES = frozenset({"re-anchor", "tombstone"})
LIVE_UNTIL = "9999-12-31T23:59:59.999Z"
UINT53_MAX = 2**53 - 1
MAX_LINEAGE = 4096
MAX_RETAINED = 65536
_HEX64 = re.compile(r"[0-9a-f]{64}")

TombstoneIssuance = Callable[[str], str]
SignatureCheck = Callable[..., tuple[bool, str]]


def _registry_pin() -> dict[str, Any]:
    checkout = source_root()
    path = (
        checkout / "RAPP1_REGISTRY_PIN.json"
        if checkout is not None
        else data_file("RAPP1_REGISTRY_PIN.json")
    )

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise RuntimeError(f"duplicate RAPP/1 registry pin member: {key}")
            result[key] = item
        return result

    value = json.loads(read_regular(path), object_pairs_hook=reject_duplicates)
    parent = rapp1.pinned_parent()
    if not (
        isinstance(value, dict)
        and set(value) == REGISTRY_PIN_KEYS
        and value["schema"] == REGISTRY_PIN_SCHEMA
        and value["protocol"] == "rapp/1"
        and value["repository"] == parent["repository"]
        and value["commit"] == parent["commit"]
        and value["reference_path"] == "rapp_registry.py"
        and isinstance(value["reference_sha256"], str)
    ):
        raise RuntimeError("invalid RAPP/1 registry reference pin")
    return value


def _load_registry_reference() -> ModuleType:
    pin = _registry_pin()
    implementation = vendor_root() / "rapp_registry.py"
    source = read_regular(implementation)
    if hashlib.sha256(source).hexdigest() != pin["reference_sha256"]:
        raise RuntimeError("pinned RAPP/1 registry reference hash mismatch")
    parent = rapp1._R

    def bind_parent(
        name: str,
        namespace: Mapping[str, object] | None = None,
        local_namespace: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> ModuleType:
        # The reference's one non-stdlib import is `import rapp`: bind the verified pinned parent.
        if name == "rapp" and level == 0:
            return parent
        return builtins.__import__(name, namespace, local_namespace, fromlist, level)

    module = ModuleType("rapp_work._pinned_rapp1_registry")
    module.__file__ = str(implementation)
    module.__dict__["__builtins__"] = {**vars(builtins), "__import__": bind_parent}
    exec(compile(source, str(implementation), "exec"), module.__dict__)
    if module.R is not parent:
        raise RuntimeError("pinned RAPP/1 registry reference did not bind the pinned parent")
    return module


_REG = _load_registry_reference()


def pinned_registry_reference() -> dict[str, Any]:
    return dict(_registry_pin())


def _uint53(value: Any) -> bool:
    return type(value) is int and 0 <= value <= UINT53_MAX


def _owner_lineage(reference: Any, anchor: str) -> tuple[str, ...]:
    """Walk the registry's owner succession from the current owner back to its root."""
    predecessors = {record["new_rappid"]: record for record in reference.reanchors}
    lineage: list[str] = [reference.estate_owner]
    transitions: list[dict[str, Any]] = []
    while lineage[-1] in predecessors:
        require(
            len(transitions) < len(reference.reanchors),
            "REFUSE_REGISTRY_SUCCESSION",
            "re-anchor succession cycle",
        )
        record = predecessors[lineage[-1]]
        require(
            record["case"] in OWNER_SUCCESSION_CASES,
            "REFUSE_REGISTRY_SUCCESSION",
            "owner succession case is not verifiable by the pinned reference",
            case=record["case"],
        )
        transitions.append(record)
        lineage.append(record["old_rappid"])
    require(
        anchor in lineage,
        "REFUSE_REGISTRY_ANCHOR",
        "estate owner does not descend from the out-of-band anchor",
    )
    # RAPP/1 sections 13.1-13.2: root-key compromise cannot be expressed inside the registry it signs.
    require(
        all(record["case"] == "rotation" for record in transitions[: lineage.index(anchor)]),
        "REFUSE_REGISTRY_ANCHOR",
        "an out-of-band anchor extends only through signed rotation; "
        "compromise recovery requires a new out-of-band anchor",
    )
    return tuple(reversed(lineage))


@dataclass(frozen=True)
class VerifiedRegistry:
    """A signed RAPP/1 registry verified against an out-of-band anchor, never a signer."""

    sequence: int
    commitment: str
    anchor: str
    estate_owner: str
    owner_lineage: tuple[str, ...]
    lifecycle: tuple[str, ...]
    _reference: Any = field(repr=False, compare=False)

    def owner_at(self, utc: str) -> str:
        """The estate owner in effect at an authenticated artifact time (RAPP/1 section 13.2)."""
        require(
            bool(rapp1.utc_valid(utc)),
            "REFUSE_REGISTRY_TIME",
            "owner tenure time is not the fixed RAPP/1 UTC form",
        )
        return str(self._reference.owner_at(utc))

    def signer_acceptable(self, kid: str, utc: str) -> tuple[bool, str]:
        """Section 10 key acceptability at `utc`; retirement matches the key tail, not the name."""
        if not (rapp1.rappid_valid(kid) and rapp1.utc_valid(utc)):
            return False, "signer must be a RAPPID and time the fixed RAPP/1 UTC form"
        ok, why = self._reference._signer_acceptable(kid, utc, match_key_aliases=True)
        return bool(ok), str(why)

    def signature_verifier(self) -> SignatureCheck:
        """A verifier for `validate_frame`/`validate_chain` using this registry's key history."""

        def verify(
            unsigned: Mapping[str, Any],
            sig: str,
            expected_signer: str | None = None,
        ) -> tuple[bool, str]:
            try:
                kid = rapp1._R.parse_detached_jws(sig)[0]["kid"]
            except ValueError as error:
                return False, str(error)
            if expected_signer is not None and kid != expected_signer:
                return False, "kid is not the required signer"
            stamp = (
                unsigned.get("utc") or unsigned.get("created_utc") or unsigned.get("activated_utc")
            )
            if not isinstance(stamp, str):
                return False, "artifact carries no utc to scope the signer's authority"
            ok, why = self.signer_acceptable(kid, stamp)
            if not ok:
                return False, why
            accepted, reason = rapp1.verify_detached_jws(
                dict(unsigned), sig, self._reference.spki_der(kid), expected_kid=kid
            )
            return bool(accepted), str(reason)

        return verify

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor": self.anchor,
            "commitment": self.commitment,
            "estate_owner": self.estate_owner,
            "lifecycle": list(self.lifecycle),
            "owner_lineage": list(self.owner_lineage),
            "profile": SUCCESSION_PROFILE,
            "registry_seq": self.sequence,
            "status": "verified",
        }


@dataclass(frozen=True)
class _Retained:
    sequence: int
    commitment: str
    owner_lineage: tuple[str, ...]
    lifecycle: frozenset[str]


def _retained_state(retained: Any) -> _Retained | None:
    """The caller's retained registry state: a `VerifiedRegistry` or its persisted `to_dict()` record."""
    if retained is None:
        return None
    if isinstance(retained, VerifiedRegistry):
        return _Retained(
            retained.sequence,
            retained.commitment,
            retained.owner_lineage,
            frozenset(retained.lifecycle),
        )
    require(
        isinstance(retained, Mapping) and set(retained) == RETAINED_KEYS,
        "REFUSE_INPUT_SHAPE",
        "retained registry state must be a verified registry or its to_dict() record",
    )
    lineage, lifecycle = retained["owner_lineage"], retained["lifecycle"]
    require(
        retained["status"] == "verified"
        and retained["profile"] == SUCCESSION_PROFILE
        and _uint53(retained["registry_seq"])
        and isinstance(retained["commitment"], str)
        and bool(_HEX64.fullmatch(retained["commitment"]))
        and isinstance(lineage, (list, tuple))
        and 1 <= len(lineage) <= MAX_RETAINED
        and all(bool(rapp1.rappid_valid(owner)) for owner in lineage)
        and len(set(lineage)) == len(lineage)
        and retained["estate_owner"] == lineage[-1]
        and retained["anchor"] in lineage
        and isinstance(lifecycle, (list, tuple))
        and len(lifecycle) <= MAX_RETAINED
        and all(isinstance(value, str) and bool(_HEX64.fullmatch(value)) for value in lifecycle)
        and list(lifecycle) == sorted(set(lifecycle)),
        "REFUSE_INPUT_SHAPE",
        "retained registry state is not a verified registry record",
    )
    return _Retained(
        retained["registry_seq"], retained["commitment"], tuple(lineage), frozenset(lifecycle)
    )


def verify_registry(
    document: bytes,
    *,
    entries_member: str,
    anchor_rappid: str,
    anchor_spki_der: bytes,
    tombstone_issued_at: TombstoneIssuance,
    retained: VerifiedRegistry | Mapping[str, Any] | None = None,
) -> VerifiedRegistry:
    """Verify one signed registry against the out-of-band anchor and the retained registry state.

    `retained` is the caller's last verified registry (or its `to_dict()` record). It
    is required when the anchor is not the current estate owner; it carries the
    persisted high-water, and a later registry must keep every retained `re-anchor`
    and `tombstone` entry and extend the retained owner lineage.
    """
    require(isinstance(document, bytes), "REFUSE_REGISTRY", "registry document must be bytes")
    require(
        isinstance(entries_member, str) and bool(entries_member),
        "REFUSE_REGISTRY",
        "the registry entries member must be named explicitly",
    )
    require(
        callable(tombstone_issued_at),
        "REFUSE_REGISTRY_ISSUANCE",
        "owner succession verification requires a trusted tombstone issuance resolver",
    )
    require(
        bool(rapp1.rappid_valid(anchor_rappid))
        and isinstance(anchor_spki_der, bytes)
        and rapp1.hash_bytes("rapp/1:rappid", anchor_spki_der)
        == rapp1.rappid_parts(anchor_rappid)["hash"],
        "REFUSE_REGISTRY_ANCHOR",
        "out-of-band anchor SPKI does not bind the anchor RAPPID",
    )
    state = _retained_state(retained)
    persisted_seq = None if state is None else state.sequence
    value = strict_json_loads(document, where="RAPP/1 registry")
    require(isinstance(value, dict), "REFUSE_REGISTRY", "registry document must be an object")
    sequence = value.get("registry_seq")
    require(_uint53(sequence), "REFUSE_REGISTRY", "registry_seq must be uint53")
    require(
        persisted_seq is None or sequence >= persisted_seq,
        "REFUSE_REGISTRY_ROLLBACK",
        "registry sequence rolled back",
        registry_seq=sequence,
        persisted_seq=persisted_seq,
    )
    try:
        reference = _REG.Registry(value.get(entries_member))
    except ValueError as error:
        raise Refusal(
            "REFUSE_REGISTRY_ENTRY",
            "RAPP/1 section 13.3 entry refused",
            {"reason": str(error)},
        ) from error
    lineage = _owner_lineage(reference, anchor_rappid)
    require(
        reference.spki_der(anchor_rappid) == anchor_spki_der,
        "REFUSE_REGISTRY_ANCHOR",
        "out-of-band anchor SPKI is not the registered anchor key",
    )

    def issued_at(entry_hash: str) -> str:
        try:
            return tombstone_issued_at(entry_hash)
        except (LookupError, OSError, TypeError, ValueError) as error:
            raise ValueError(f"trusted issuance resolver refused: {error}") from error

    status, loaded, reason = _REG.load_document(
        value,
        entries_member=entries_member,
        trust_anchor=reference.estate_owner,
        persisted_seq=persisted_seq,
        tombstone_issued_at=issued_at,
    )
    require(
        status == "verified" and loaded is not None,
        "REFUSE_REGISTRY_AUTHORITY",
        "RAPP/1 section 13 verification refused",
        reason=str(reason),
    )
    live, why = loaded._signer_acceptable(loaded.estate_owner, LIVE_UNTIL, match_key_aliases=True)
    require(bool(live), "REFUSE_REGISTRY_OWNER", "current estate owner key is not live", reason=why)
    unsigned = {key: item for key, item in value.items() if key != "sig"}
    commitment = str(rapp1.hash_json("rapp/1:particle", unsigned))
    lifecycle = frozenset(
        str(rapp1.hash_json("rapp/1:particle", entry))
        for entry in loaded.entries
        if entry["type"] in LIFECYCLE_TYPES
    )
    if state is None:
        # A predecessor anchor is exactly what a leaked retired key could replay.
        require(
            loaded.estate_owner == anchor_rappid,
            "REFUSE_REGISTRY_ANCHOR",
            "an out-of-band anchor that is not the current estate owner "
            "requires the retained registry state",
        )
    else:
        require(
            sequence != state.sequence or commitment == state.commitment,
            "REFUSE_REGISTRY_FORK",
            "same-sequence registry differs from the retained commitment",
        )
        require(
            lineage[: len(state.owner_lineage)] == state.owner_lineage,
            "REFUSE_REGISTRY_LINEAGE",
            "a later registry rewrote accepted owner succession",
            registry_seq=sequence,
        )
        require(
            state.lifecycle <= lifecycle,
            "REFUSE_REGISTRY_LINEAGE",
            "a later registry dropped or rewrote a succession or revocation record",
            registry_seq=sequence,
        )
        appended = lifecycle - state.lifecycle
        compromises = [
            record
            for record in loaded.reanchors
            if record["case"] == "compromise"
            and str(rapp1.hash_json("rapp/1:particle", record)) in appended
        ]
        if compromises:
            # RAPP/1 section 6.3: only a one-step successor of retained state proves one append.
            require(
                sequence == state.sequence + 1,
                "REFUSE_REGISTRY_LINEAGE",
                "a new compromise re-anchor needs same-append evidence; "
                "verify each intermediate registry in sequence",
                registry_seq=sequence,
            )
        for record in compromises:
            require(
                any(
                    entry["type"] == "tombstone"
                    and entry["rappid"] == record["old_rappid"]
                    and str(rapp1.hash_json("rapp/1:particle", entry)) in appended
                    for entry in loaded.entries
                ),
                "REFUSE_REGISTRY_LINEAGE",
                "a compromise re-anchor and its tombstone must be registered in the same append",
                registry_seq=sequence,
            )
    return VerifiedRegistry(
        sequence=sequence,
        commitment=commitment,
        anchor=anchor_rappid,
        estate_owner=str(loaded.estate_owner),
        owner_lineage=lineage,
        lifecycle=tuple(sorted(lifecycle)),
        _reference=loaded,
    )


def verify_registry_lineage(
    documents: Sequence[bytes],
    *,
    entries_member: str,
    anchor_rappid: str,
    anchor_spki_der: bytes,
    tombstone_issued_at: TombstoneIssuance,
    retained: VerifiedRegistry | Mapping[str, Any] | None = None,
) -> tuple[VerifiedRegistry, ...]:
    """Verify contiguous registry snapshots after `retained`; accepted succession only grows.

    A segment after an owner-compromise re-anchor is verified under the newly
    distributed anchor with the last snapshot of the old segment as `retained`.
    """
    require(
        isinstance(documents, (list, tuple)) and 1 <= len(documents) <= MAX_LINEAGE,
        "REFUSE_REGISTRY_LINEAGE",
        "registry lineage must be a bounded nonempty sequence",
    )
    state = _retained_state(retained)
    verified: list[VerifiedRegistry] = []
    previous: VerifiedRegistry | Mapping[str, Any] | None = retained
    for document in documents:
        current = verify_registry(
            document,
            entries_member=entries_member,
            anchor_rappid=anchor_rappid,
            anchor_spki_der=anchor_spki_der,
            tombstone_issued_at=tombstone_issued_at,
            retained=previous,
        )
        if state is not None:
            require(
                current.sequence == state.sequence + 1,
                "REFUSE_REGISTRY_LINEAGE",
                "registry lineage is not contiguous",
                previous=state.sequence,
                current=current.sequence,
            )
        verified.append(current)
        previous, state = current, _retained_state(current)
    return tuple(verified)
