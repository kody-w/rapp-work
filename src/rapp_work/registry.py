"""Read-only RAPP/1 section 13 registry verification across owner succession.

The SDK never mints, signs, appends, or rewrites a registry. It verifies a
signed ``rapp/1-registry`` document with the pinned RAPP/1 registry reference
named by ``RAPP1_REGISTRY_PIN.json``: exact section 13.3 entries, owner tenure,
lifecycle signatures, and time-scoped key retirement. The caller supplies the
out-of-band anchor and a trusted tombstone issuance resolver; neither is read
from the untrusted document.
"""

from __future__ import annotations

import builtins
import hashlib
import json
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
OWNER_SUCCESSION_CASES = frozenset({"rotation", "compromise"})
LIFECYCLE_TYPES = frozenset({"re-anchor", "tombstone"})
LIVE_UNTIL = "9999-12-31T23:59:59.999Z"
UINT53_MAX = 2**53 - 1
MAX_LINEAGE = 4096

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


def verify_registry(
    document: bytes,
    *,
    entries_member: str,
    anchor_rappid: str,
    anchor_spki_der: bytes,
    tombstone_issued_at: TombstoneIssuance,
    persisted_seq: int | None = None,
    persisted_hash: str | None = None,
) -> VerifiedRegistry:
    """Verify one signed registry; the anchor may be the current owner or a rotated predecessor."""
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
    require(
        (persisted_seq is None and persisted_hash is None)
        or (_uint53(persisted_seq) and (persisted_hash is None or isinstance(persisted_hash, str))),
        "REFUSE_INPUT_SHAPE",
        "persisted registry high-water must be a uint53 sequence and optional hash",
    )
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
    if persisted_seq is not None and sequence == persisted_seq:
        require(
            persisted_hash is not None and commitment == persisted_hash,
            "REFUSE_REGISTRY_FORK",
            "same-sequence registry differs from the persisted commitment",
        )
    return VerifiedRegistry(
        sequence=sequence,
        commitment=commitment,
        anchor=anchor_rappid,
        estate_owner=str(loaded.estate_owner),
        owner_lineage=lineage,
        lifecycle=tuple(
            str(rapp1.hash_json("rapp/1:particle", entry))
            for entry in loaded.entries
            if entry["type"] in LIFECYCLE_TYPES
        ),
        _reference=loaded,
    )


def verify_registry_lineage(
    documents: Sequence[bytes],
    *,
    entries_member: str,
    anchor_rappid: str,
    anchor_spki_der: bytes,
    tombstone_issued_at: TombstoneIssuance,
    retained: VerifiedRegistry | None = None,
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
    require(
        retained is None or isinstance(retained, VerifiedRegistry),
        "REFUSE_REGISTRY_LINEAGE",
        "retained registry must be a verified registry",
    )
    verified: list[VerifiedRegistry] = []
    previous = retained
    for document in documents:
        current = verify_registry(
            document,
            entries_member=entries_member,
            anchor_rappid=anchor_rappid,
            anchor_spki_der=anchor_spki_der,
            tombstone_issued_at=tombstone_issued_at,
            persisted_seq=None if previous is None else previous.sequence,
            persisted_hash=None if previous is None else previous.commitment,
        )
        if previous is not None:
            require(
                current.sequence == previous.sequence + 1,
                "REFUSE_REGISTRY_LINEAGE",
                "registry lineage is not contiguous",
                previous=previous.sequence,
                current=current.sequence,
            )
            require(
                set(previous.lifecycle) <= set(current.lifecycle),
                "REFUSE_REGISTRY_LINEAGE",
                "a later registry dropped or rewrote a succession or revocation record",
                registry_seq=current.sequence,
            )
            require(
                current.owner_lineage[: len(previous.owner_lineage)] == previous.owner_lineage,
                "REFUSE_REGISTRY_LINEAGE",
                "a later registry rewrote accepted owner succession",
                registry_seq=current.sequence,
            )
        verified.append(current)
        previous = current
    return tuple(verified)
