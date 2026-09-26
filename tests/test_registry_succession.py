from __future__ import annotations

import base64
import hashlib
import re
import shutil
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import rapp_work.registry as succession
from rapp_work import (
    HiveStreamPosition,
    HiveVector,
    build_frame,
    execute,
    pinned_parent,
    validate_chain,
    verify_hive_high_water,
)
from rapp_work._resources import vendor_root
from rapp_work.compat import run_private_hive_cli
from rapp_work.errors import Refusal
from rapp_work.rapp1 import canonical, hash_json, mint_rappid
from rapp_work.registry import (
    VerifiedRegistry,
    pinned_registry_reference,
    verify_registry,
    verify_registry_lineage,
)

NAMES = ("alice", "heir", "bob", "bob-next", "carol", "outsider")
BOUNDARY = 150


def stamp(seconds: int) -> str:
    value = datetime(2026, 9, 11, 17, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Estate:
    """Public Ed25519 fixture identities; no key here protects anything real."""

    def __init__(self, *, device: bool = False) -> None:
        self.private: dict[str, Ed25519PrivateKey] = {}
        self.spki: dict[str, bytes] = {}
        self.ids: dict[str, str] = {}
        for name in NAMES:
            seed = hashlib.sha256(f"PUBLIC TEST VECTOR ONLY: sdk succession {name}".encode()).digest()
            key = Ed25519PrivateKey.from_private_bytes(seed)
            self.private[name] = key
            self.spki[name] = key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            self.ids[name] = mint_rappid(name, "member", self.spki[name])
        if device:
            self.private["device"], self.spki["device"] = self.private["alice"], self.spki["alice"]
            self.ids["device"] = mint_rappid("alice", "device", self.spki["alice"])
        self.issuance: dict[str, str] = {}
        self.stream = mint_rappid("example", "notes")

    def sign(self, value: dict[str, Any], signer: str) -> str:
        header = {"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": self.ids[signer]}
        protected = b64url(canonical(header).encode())
        signature = self.private[signer].sign(protected.encode() + b"." + canonical(value).encode())
        return protected + ".." + b64url(signature)

    def reanchor(
        self,
        old: str,
        new: str,
        *,
        case: str = "rotation",
        seconds: int = BOUNDARY,
        signer: str | None = None,
        continuity: str | None = None,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "case": case,
            "new_rappid": self.ids[new],
            "old_rappid": self.ids[old],
            "type": "re-anchor",
            "utc": stamp(seconds),
        }
        if case == "rotation" or continuity is not None:
            entry["old_key_sig"] = self.sign(dict(entry), continuity or old)
        entry["sig"] = self.sign(dict(entry), signer or old)
        return entry

    def tombstone(self, target: str, *, revoked: int, issued: int, signer: str) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "revoked_utc": stamp(revoked),
            "rappid": self.ids[target],
            "type": "tombstone",
        }
        entry["sig"] = self.sign(dict(entry), signer)
        self.issuance[hash_json("rapp/1:particle", entry)] = stamp(issued)
        return entry

    def registry(
        self,
        sequence: int = 1,
        *,
        owner: str = "alice",
        lifecycle: Iterable[dict[str, Any]] = (),
        signer: str | None = None,
        unregistered: Iterable[str] = (),
    ) -> bytes:
        skip = set(unregistered)
        entries: list[dict[str, Any]] = [
            {"rappid": self.ids[owner], "type": "estate_owner"},
            {"deprecated": False, "family": "body", "kind": "example.note", "type": "kind"},
        ]
        entries.extend(
            {
                "deprecated": False,
                "rappid": self.ids[name],
                "spki_der_b64": base64.b64encode(key).decode("ascii"),
                "type": "spki",
            }
            for name, key in self.spki.items()
            if name not in skip
        )
        entries.extend(lifecycle)
        document: dict[str, Any] = {
            "canonical_source": "https://example.invalid/registry",
            "entries": entries,
            "registry_seq": sequence,
            "schema": "rapp/1-registry",
        }
        document["sig"] = self.sign(document, signer or owner)
        return canonical(document).encode()

    def succeeded(self, *lifecycle: dict[str, Any], sequence: int = 2) -> bytes:
        return self.registry(
            sequence, owner="heir", lifecycle=[self.reanchor("alice", "heir"), *lifecycle]
        )

    def verify(
        self, document: bytes, *, anchor: str = "alice", **options: Any
    ) -> VerifiedRegistry:
        options.setdefault("tombstone_issued_at", self.issuance.__getitem__)
        return verify_registry(
            document,
            entries_member="entries",
            anchor_rappid=self.ids[anchor],
            anchor_spki_der=self.spki[anchor],
            **options,
        )

    def walk(self, document: bytes, **options: Any) -> VerifiedRegistry:
        """Verify `document` after first accepting the direct-owner registry (seq 1) as retained state."""
        return self.verify(document, retained=self.verify(self.registry(1)), **options)

    def lineage(
        self, documents: list[bytes], *, anchor: str = "alice", **options: Any
    ) -> tuple[VerifiedRegistry, ...]:
        return verify_registry_lineage(
            documents,
            entries_member="entries",
            anchor_rappid=self.ids[anchor],
            anchor_spki_der=self.spki[anchor],
            tombstone_issued_at=self.issuance.__getitem__,
            **options,
        )

    def note(
        self, seq: int, seconds: int, signer: str, head: dict[str, Any] | None
    ) -> dict[str, Any]:
        unsigned = build_frame(
            kind="example.note",
            stream_id=self.stream,
            seq=seq,
            utc=stamp(seconds),
            payload={"note": seq},
            prev=None if head is None else head["payload_hash"],
            head=head,
        ).to_dict()
        unsigned["sig"] = self.sign(
            {key: value for key, value in unsigned.items() if key != "sig"}, signer
        )
        return unsigned


def refused(code: str, message: str | None = None) -> Any:
    pattern = re.escape(code) + (": .*" + re.escape(message) if message else "")
    return pytest.raises(Refusal, match=pattern)


def refusal_reason(error: pytest.ExceptionInfo[Refusal]) -> str:
    return str((error.value.details or {}).get("reason"))


def test_registry_reference_is_the_exact_canonical_parent_revision() -> None:
    pin = pinned_registry_reference()
    assert pin["commit"] == pinned_parent()["commit"]
    assert pin["repository"] == pinned_parent()["repository"]
    raw = (vendor_root() / "rapp_registry.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pin["reference_sha256"]
    assert succession._REG.R is succession.rapp1._R


def test_tampered_registry_reference_or_pin_is_refused_before_use(
    sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = sandbox / "rapp_registry.py"
    shutil.copyfile(vendor_root() / "rapp_registry.py", tampered)
    tampered.chmod(0o600)
    tampered.write_bytes(tampered.read_bytes() + b"\n# tampered\n")
    monkeypatch.setattr(succession, "vendor_root", lambda: sandbox)
    with pytest.raises(RuntimeError, match="registry reference hash mismatch"):
        succession._load_registry_reference()
    pin = pinned_registry_reference()
    monkeypatch.setattr(succession, "_registry_pin", lambda: {**pin, "reference_sha256": "0" * 64})
    monkeypatch.setattr(succession, "vendor_root", vendor_root)
    with pytest.raises(RuntimeError, match="registry reference hash mismatch"):
        succession._load_registry_reference()


def test_planned_rotation_extends_the_original_out_of_band_anchor() -> None:
    estate = Estate()
    with refused("REFUSE_REGISTRY_ANCHOR", "requires the retained registry state"):
        estate.verify(estate.succeeded())
    first = estate.verify(estate.registry(1))
    verified = estate.verify(estate.succeeded(), retained=first)
    assert (verified.anchor, verified.estate_owner) == (estate.ids["alice"], estate.ids["heir"])
    assert verified.owner_lineage == (estate.ids["alice"], estate.ids["heir"])
    assert verified.owner_at(stamp(BOUNDARY - 1)) == estate.ids["alice"]
    assert verified.owner_at(stamp(BOUNDARY)) == estate.ids["heir"]
    assert estate.verify(estate.succeeded(), retained=first.to_dict()) == verified
    assert estate.verify(estate.succeeded(), anchor="heir").estate_owner == estate.ids["heir"]
    with refused("REFUSE_REGISTRY_TIME"):
        verified.owner_at("2026-13-01T00:00:00.000Z")
    result = verified.to_dict()
    assert canonical(result) == canonical(dict(sorted(result.items())))
    assert result["status"] == "verified" and result["registry_seq"] == 2
    assert result["lifecycle"] == [hash_json("rapp/1:particle", estate.reanchor("alice", "heir"))]


def test_frames_across_the_boundary_follow_the_owner_key_history() -> None:
    estate = Estate()
    verifier = estate.walk(estate.succeeded()).signature_verifier()
    genesis = estate.note(0, BOUNDARY - 50, "alice", None)
    before = estate.note(1, BOUNDARY - 10, "alice", genesis)
    assert len(validate_chain([genesis, before], signature_verifier=verifier)) == 2
    stale = estate.note(2, BOUNDARY + 10, "alice", before)
    with refused("REFUSE_RAPP_FRAME") as error:
        validate_chain([genesis, before, stale], signature_verifier=verifier)
    assert "superseded" in str(error.value.details)
    current = estate.note(2, BOUNDARY + 10, "heir", before)
    assert validate_chain([genesis, before, current], signature_verifier=verifier)[-1].seq == 2
    assert verifier({"utc": stamp(0)}, current["sig"], estate.ids["alice"]) == (
        False,
        "kid is not the required signer",
    )


def test_succession_record_must_be_signed_by_the_outgoing_owner() -> None:
    estate = Estate()
    for options, reason in (
        ({"signer": "heir"}, "re-anchor owner signature refused"),
        ({"continuity": "heir"}, "re-anchor old-key signature refused"),
    ):
        document = estate.registry(2, owner="heir", lifecycle=[estate.reanchor("alice", "heir", **options)])
        for anchor in ("alice", "heir"):
            with refused("REFUSE_REGISTRY_AUTHORITY") as error:
                estate.verify(document, anchor=anchor)
            assert reason in refusal_reason(error)


def test_empty_or_backwards_owner_tenure_is_refused() -> None:
    estate = Estate()
    for seconds in (BOUNDARY - 10, BOUNDARY):
        onward = estate.reanchor("heir", "outsider", seconds=seconds)
        document = estate.registry(
            2, owner="outsider", lifecycle=[estate.reanchor("alice", "heir"), onward]
        )
        with refused("REFUSE_REGISTRY_AUTHORITY") as error:
            estate.verify(document)
        assert "nonempty, forward tenure" in refusal_reason(error)


def test_owner_compromise_needs_a_new_anchor_and_trusted_issuance() -> None:
    estate = Estate()
    compromise = estate.reanchor("alice", "heir", case="compromise")
    burned = estate.tombstone("alice", revoked=120, issued=BOUNDARY, signer="heir")
    document = estate.registry(2, owner="heir", lifecycle=[compromise, burned])
    with refused("REFUSE_REGISTRY_ANCHOR", "new out-of-band anchor"):
        estate.verify(document)
    with refused("REFUSE_REGISTRY_ISSUANCE"):
        estate.verify(document, anchor="heir", tombstone_issued_at=None)
    with refused("REFUSE_REGISTRY_AUTHORITY") as error:
        estate.verify(document, anchor="heir", tombstone_issued_at={}.__getitem__)
    assert "issuance" in refusal_reason(error)
    with refused("REFUSE_REGISTRY_AUTHORITY") as error:
        estate.verify(estate.registry(2, owner="heir", lifecycle=[compromise]), anchor="heir")
    assert "registered tombstone" in refusal_reason(error)
    verified = estate.verify(document, anchor="heir")
    assert verified.owner_lineage == (estate.ids["alice"], estate.ids["heir"])
    assert verified.signer_acceptable(estate.ids["alice"], stamp(119)) == (True, "ok")
    ok, why = verified.signer_acceptable(estate.ids["alice"], stamp(120))
    assert not ok and "tombstoned" in why
    assert verified.owner_at(stamp(130)) == estate.ids["alice"]


def test_member_compromise_revokes_only_after_its_cutoff() -> None:
    estate = Estate()
    compromise = estate.reanchor("bob", "bob-next", case="compromise", seconds=60, signer="alice")
    burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
    verified = estate.verify(estate.registry(2, lifecycle=[compromise, burned]))
    assert verified.signer_acceptable(estate.ids["bob"], stamp(39))[0] is True
    assert verified.signer_acceptable(estate.ids["bob"], stamp(40))[0] is False
    assert verified.signer_acceptable(estate.ids["bob-next"], stamp(70)) == (True, "ok")
    stale = estate.tombstone("bob", revoked=45, issued=BOUNDARY + 10, signer="alice")
    with refused("REFUSE_REGISTRY_AUTHORITY") as error:
        estate.verify(estate.succeeded(stale))
    assert "tombstone owner signature refused" in refusal_reason(error)


def test_ambiguous_predecessor_is_refused() -> None:
    estate = Estate()
    second = estate.reanchor("outsider", "heir", seconds=BOUNDARY + 10, signer="heir")
    with refused("REFUSE_REGISTRY_ENTRY") as error:
        estate.verify(estate.succeeded(second))
    assert "more than one predecessor" in refusal_reason(error)


@pytest.mark.parametrize("entry_type", [["estate_owner"], {"estate_owner": True}], ids=["array", "object"])
def test_malformed_registry_entry_is_a_refusal_not_a_raw_error(entry_type: Any) -> None:
    estate = Estate()
    with refused("REFUSE_REGISTRY_ENTRY", "section 13.3 entry refused"):
        estate.verify(estate.registry(1, lifecycle=[{"type": entry_type}]))


def test_renamed_alias_cannot_revive_a_retired_key() -> None:
    estate = Estate(device=True)
    with refused("REFUSE_REGISTRY_ENTRY") as error:
        estate.verify(
            estate.registry(2, owner="device", lifecycle=[estate.reanchor("alice", "device")])
        )
    assert "fresh identity tail" in refusal_reason(error)
    verified = estate.walk(estate.succeeded())
    assert verified.signer_acceptable(estate.ids["device"], stamp(BOUNDARY - 1)) == (True, "ok")
    ok, why = verified.signer_acceptable(estate.ids["device"], stamp(BOUNDARY))
    assert not ok and "superseded" in why
    frame = {"utc": stamp(BOUNDARY + 1)}
    assert verified.signature_verifier()(frame, estate.sign(frame, "device"))[0] is False


def test_current_owner_key_must_be_live() -> None:
    estate = Estate()
    burned = estate.tombstone("heir", revoked=BOUNDARY + 20, issued=BOUNDARY + 20, signer="heir")
    with refused("REFUSE_REGISTRY_OWNER") as error:
        estate.verify(estate.succeeded(burned))
    assert "tombstoned" in refusal_reason(error)


def test_anchor_must_descend_and_bind_its_key() -> None:
    estate = Estate()
    document = estate.succeeded()
    for anchor in ("outsider", "bob"):
        with refused("REFUSE_REGISTRY_ANCHOR", "does not descend"):
            estate.verify(document, anchor=anchor)
    with refused("REFUSE_REGISTRY_ANCHOR", "does not bind"):
        verify_registry(
            document,
            entries_member="entries",
            anchor_rappid=estate.ids["alice"],
            anchor_spki_der=estate.spki["heir"],
            tombstone_issued_at=estate.issuance.__getitem__,
        )
    with refused("REFUSE_REGISTRY_ANCHOR", "not the registered anchor key"):
        estate.verify(estate.registry(2, unregistered=("alice",)))


def test_registry_high_water_and_same_sequence_fork() -> None:
    estate = Estate()
    document = estate.succeeded()
    verified = estate.walk(document)
    later = estate.verify(estate.succeeded(sequence=3), retained=verified)
    with refused("REFUSE_REGISTRY_ROLLBACK"):
        estate.verify(document, retained=later)
    with refused("REFUSE_REGISTRY_FORK"):
        estate.verify(document, retained={**verified.to_dict(), "commitment": "e" * 64})
    again = estate.verify(document, retained=verified)
    assert again.commitment == verified.commitment


def test_retained_state_is_required_for_a_predecessor_anchor_and_is_closed() -> None:
    estate = Estate()
    good = estate.verify(estate.registry(1)).to_dict()
    assert estate.verify(estate.succeeded(), retained=good).owner_lineage[-1] == estate.ids["heir"]
    with refused("REFUSE_INPUT_SHAPE"):
        estate.verify(estate.succeeded(), retained=["not", "a", "record"])


RETAINED_BREAKS: dict[str, Any] = {
    "missing": lambda good, ids: {key: value for key, value in good.items() if key != "lifecycle"},
    "extra": lambda good, ids: {**good, "registry_hash": good["commitment"]},
    "status": lambda good, ids: {**good, "status": "draft"},
    "profile": lambda good, ids: {**good, "profile": "rapp1-13.3"},
    "boolean-seq": lambda good, ids: {**good, "registry_seq": True},
    "bad-commitment": lambda good, ids: {**good, "commitment": "E" * 64},
    "empty-lineage": lambda good, ids: {**good, "owner_lineage": [], "estate_owner": good["anchor"]},
    "repeated-owner": lambda good, ids: {**good, "owner_lineage": [good["anchor"]] * 2},
    "owner-not-last": lambda good, ids: {**good, "estate_owner": ids["heir"]},
    "anchor-outside": lambda good, ids: {**good, "anchor": ids["outsider"]},
    "unsorted": lambda good, ids: {**good, "lifecycle": ["f" * 64, "0" * 64]},
}


@pytest.mark.parametrize("variant", sorted(RETAINED_BREAKS))
def test_malformed_retained_state_is_refused(variant: str) -> None:
    estate = Estate()
    good = estate.verify(estate.registry(1)).to_dict()
    with refused("REFUSE_INPUT_SHAPE"):
        estate.verify(estate.succeeded(), retained=RETAINED_BREAKS[variant](good, estate.ids))


def test_retained_state_refuses_rollback_by_a_retired_anchor_key_or_a_moved_boundary() -> None:
    estate = Estate()
    accepted = estate.walk(estate.succeeded())
    rollback = estate.registry(3, owner="alice")
    for retained in (accepted, accepted.to_dict()):
        with refused("REFUSE_REGISTRY_LINEAGE", "rewrote accepted owner succession"):
            estate.verify(rollback, retained=retained)
    moved = estate.registry(
        3, owner="heir", lifecycle=[estate.reanchor("alice", "heir", seconds=BOUNDARY + 300)]
    )
    with refused("REFUSE_REGISTRY_LINEAGE", "dropped or rewrote"):
        estate.verify(moved, retained=accepted)
    with refused("REFUSE_REGISTRY_LINEAGE", "dropped or rewrote"):
        estate.lineage([moved], retained=accepted)
    # Without retained state the consumer is fresh: its out-of-band anchor alone decides (RAPP/1 13.1).
    assert estate.verify(rollback).estate_owner == estate.ids["alice"]


def test_compromise_re_anchor_and_its_tombstone_share_one_append() -> None:
    estate = Estate()
    burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
    compromise = estate.reanchor("bob", "bob-next", case="compromise", seconds=60, signer="alice")
    with refused("REFUSE_REGISTRY_LINEAGE", "same append"):
        estate.lineage(
            [estate.registry(1, lifecycle=[burned]), estate.registry(2, lifecycle=[burned, compromise])]
        )
    first = estate.verify(estate.registry(1))
    together = estate.lineage([estate.registry(2, lifecycle=[compromise, burned])], retained=first)
    assert together[-1].signer_acceptable(estate.ids["bob"], stamp(40))[0] is False
    with refused("REFUSE_REGISTRY_LINEAGE", "verify each intermediate registry"):
        estate.verify(estate.registry(3, lifecycle=[compromise, burned]), retained=first)


def test_unverifiable_owner_succession_cases_are_refused() -> None:
    estate = Estate()
    for case in ("upgrade", "tag-migrate"):
        document = estate.registry(
            2, owner="heir", lifecycle=[estate.reanchor("alice", "heir", case=case)]
        )
        with refused("REFUSE_REGISTRY_SUCCESSION", "not verifiable"):
            estate.verify(document, anchor="heir")


def test_lineage_across_the_boundary_feeds_hive_high_water() -> None:
    estate = Estate()
    first, second = estate.lineage([estate.registry(1), estate.succeeded()])
    assert (first.estate_owner, second.estate_owner) == (estate.ids["alice"], estate.ids["heir"])
    mother = mint_rappid("example", "succession-hive")
    history = tuple((item.sequence, item.commitment) for item in (first, second))

    def vector(depth: int) -> HiveVector:
        heads = tuple(hashlib.sha256(f"mother-{index}".encode()).hexdigest() for index in range(depth))
        position = HiveStreamPosition(mother, depth - 1, heads[-1], heads)
        return HiveVector(mother, history[depth - 1][0], history[depth - 1][1], (position,),
                          history[:depth])

    assert verify_hive_high_water(vector(2), vector(1))["status"] == "verified-high-water"


def test_lineage_refuses_gaps_dropped_revocations_and_rewritten_owner_history() -> None:
    estate = Estate()
    burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
    first = estate.registry(1, lifecycle=[burned])
    with refused("REFUSE_REGISTRY_LINEAGE", "not contiguous"):
        estate.lineage([first, estate.succeeded(burned, sequence=3)])
    with refused("REFUSE_REGISTRY_LINEAGE", "dropped or rewrote"):
        estate.lineage([first, estate.succeeded()])
    accepted = estate.lineage([first, estate.succeeded(burned)])
    invented = estate.succeeded(burned, estate.reanchor("carol", "alice", seconds=30), sequence=3)
    assert estate.verify(invented, anchor="heir").owner_lineage[0] == estate.ids["carol"]
    with refused("REFUSE_REGISTRY_LINEAGE", "rewrote accepted owner succession"):
        estate.lineage([invented], retained=accepted[-1])
    extended = estate.registry(
        3,
        owner="outsider",
        lifecycle=[
            burned,
            estate.reanchor("alice", "heir"),
            estate.reanchor("heir", "outsider", seconds=BOUNDARY + 50),
        ],
    )
    assert estate.lineage([extended], retained=accepted[-1])[0].owner_lineage[-1] == estate.ids[
        "outsider"
    ]


def test_lineage_continues_under_a_new_anchor_after_owner_compromise() -> None:
    estate = Estate()
    (before,) = estate.lineage([estate.registry(1)])
    compromise = estate.reanchor("alice", "heir", case="compromise")
    burned = estate.tombstone("alice", revoked=120, issued=BOUNDARY, signer="heir")
    recovered = estate.registry(2, owner="heir", lifecycle=[compromise, burned])
    with refused("REFUSE_REGISTRY_ANCHOR"):
        estate.lineage([recovered], retained=before)
    (after,) = estate.lineage([recovered], anchor="heir", retained=before)
    assert after.owner_lineage == (estate.ids["alice"], estate.ids["heir"])


def test_performing_owner_rotation_remains_refused() -> None:
    assert execute("rotate-owner", {})["refusal"]["code"] == "REFUSE_OPERATION"
    with pytest.deprecated_call(), pytest.raises(ValueError, match="rotate-owner"):
        run_private_hive_cli(["rotate-owner", "activate"])
