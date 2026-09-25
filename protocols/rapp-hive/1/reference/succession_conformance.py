"""Real Ed25519 vectors for opt-in RAPP/1 section 13.2 owner succession.

The default RegistryAuthority stays direct-owner and fails closed. These vectors
select succession="rapp1-13.2" explicitly. Every identity is a public fixture.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import rapp as R
import rapp_hive as H
from authenticated_conformance import ROOT, Estate, decision_map, octets, stamp
from hive_acceptance import SUCCESSION, HiveAcceptance, RegistryAuthority
from rapp_profile import particle_hash


NAMES = ("alice", "heir", "bob", "bob-next", "carol", "viewer", "outsider")
BOUNDARY = 150


class SuccessionEstate(Estate):
    """A Hive whose estate owner and member keys change only by signed section-13 records."""

    def __init__(self, *, device=False):
        self.private, self.spki, self.identities = {}, {}, {}
        for name in NAMES:
            seed = hashlib.sha256(("PUBLIC TEST VECTOR ONLY: succession " + name).encode()).digest()
            key = Ed25519PrivateKey.from_private_bytes(seed)
            self.private[name] = key
            self.spki[name] = key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            self.identities[name] = R.mint_rappid(name, "member", self.spki[name])
        if device:
            # One SPKI under a second RAPPID name: an alias of alice's key, not a fresh identity.
            self.private["device"], self.spki["device"] = self.private["alice"], self.spki["alice"]
            self.identities["device"] = R.mint_rappid("alice", "device", self.spki["alice"])
        self.hive = R.mint_rappid("example", "private-hive", self.spki["alice"])
        self.chains, self.genesis, self.artifacts, self.issuance = {}, {}, {}, {}
        roles = [("alice", "owner"), ("bob", "member"), ("viewer", "viewer")]
        if device:
            roles.append(("device", "member"))
        members = [{"rappid": self.identities[name], "role": role, "area": "members/" + name}
                   for name, role in roles]
        self.declaration = {
            "schema": H.DECLARATION_SCHEMA, "hive_rappid": self.hive, "world_id": "example-world",
            "created_utc": stamp(0), "authority_channel_id": "github-main",
            "members": sorted(members, key=lambda item: item["rappid"]),
            "rooms": [{"id": "general", "area": "rooms/general",
                       "members": sorted(item["rappid"] for item in members), "access": "repository"}],
            "channels": [{"id": "github-main", "kind": "github", "role": "authority",
                          "locator": "https://example.invalid/private-hive", "writeback": True}],
            "policy": {"godd_sharing": "explicit", "default_godd_scope": "local-only",
                       "external_publication": "disabled", "conflict_mode": "explicit", "default_transfer": "copy"},
        }
        self.mother = self.frame("hive.declaration", self.hive, self.declaration)
        self.receipt_genesis = self.frame("hive.projection", self.stream("alice", "receipts"), {
            "schema": H.PROJECTION_SCHEMA, "hive_rappid": self.hive, "convergence_payload_hash": "0" * 64,
            "channel_id": "github-main", "projected_utc": stamp(1), "registry_seq": 0,
            "catalog_hash": particle_hash(H.catalog_payload(self.declaration, {})),
            "frame_head": self.mother["frame_hash"], "artifact_manifest_hash": "0" * 64, "status": "stale",
        })

    def registry(self, sequence=8, *, owner="alice", lifecycle=(), deprecated=(), signer=None):
        entries = [
            {"type": "estate_owner", "rappid": self.identities[owner]},
            {"type": "protocol", "name": "rapp-hive/1", "spec_repo": "https://example.invalid/profile",
             "spec_path": "protocols/rapp-hive/1/SPEC.md",
             "spec_hash": hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(), "deprecated": False},
        ]
        entries.extend({"type": "kind", "kind": kind, "family": "body", "deprecated": False} for kind in H.KIND_SCHEMAS)
        entries.extend({"type": "spki", "rappid": self.identities[name],
                        "spki_der_b64": base64.b64encode(key).decode("ascii"), "deprecated": name in deprecated}
                       for name, key in self.spki.items())
        entries.extend({"type": "genesis", "stream_id": stream, "frame_hash": value, "deprecated": False}
                       for stream, value in sorted(self.genesis.items()))
        entries.extend(copy.deepcopy(list(lifecycle)))
        document = {"schema": "rapp/1-registry", "registry_seq": sequence,
                    "canonical_source": "https://example.invalid/registry", "entries": entries}
        document["sig"] = self.sign(document, signer or owner)
        return document

    def authority(self, document=None, *, anchor="alice", **kwargs):
        kwargs.setdefault("succession", SUCCESSION)
        if kwargs["succession"] is not None:
            kwargs.setdefault("tombstone_issued_at", lambda entry_hash: self.issuance[entry_hash])
        return RegistryAuthority(octets(document or self.registry()), owner_rappid=self.identities[anchor],
                                 owner_spki_der=self.spki[anchor], **kwargs)

    def gate(self, document=None, **kwargs):
        return HiveAcceptance(self.authority(document, **kwargs), self.hive, lambda address: self.chains[address])

    def commit(self, gate, payload, signer="alice"):
        frame = self.convergence(gate, payload, signer=signer)
        gate.accept_convergence(frame["frame_hash"])
        return frame

    def receipt(self, gate, *, signer="alice", seconds=250):
        manifest = gate.artifact_manifest()
        payload = {
            "schema": H.PROJECTION_SCHEMA, "hive_rappid": self.hive,
            "convergence_payload_hash": gate.head["payload_hash"], "channel_id": "github-main",
            "projected_utc": stamp(seconds), "registry_seq": gate.registry.sequence,
            "catalog_hash": particle_hash(gate.catalog), "frame_head": gate.head["frame_hash"],
            "artifact_manifest_hash": particle_hash(manifest), "status": "current",
        }
        frame = self.frame("hive.projection", self.receipt_genesis["stream_id"], payload,
                           previous=self.receipt_genesis, signer=signer)
        return frame, manifest

    def reanchor(self, old, new, *, case="rotation", seconds=BOUNDARY, signer=None, continuity=None):
        """A section-13.3 re-anchor; an owner transition is signed by the outgoing owner by default."""
        entry = {"type": "re-anchor", "old_rappid": self.identities[old], "new_rappid": self.identities[new],
                 "case": case, "utc": stamp(seconds)}
        if case == "rotation" or continuity is not None:
            entry["old_key_sig"] = self.sign(dict(entry), continuity or old)
        entry["sig"] = self.sign(dict(entry), signer or old)
        return entry

    def tombstone(self, target, *, revoked, issued, signer):
        entry = {"type": "tombstone", "rappid": self.identities[target], "revoked_utc": stamp(revoked)}
        entry["sig"] = self.sign(dict(entry), signer)
        # Trusted issuance context, keyed by the exact signed entry; never the revocation cutoff.
        self.issuance[R.H("rapp/1:particle", entry)] = stamp(issued)
        return entry

    def declare(self, slug, *, owner, signer, seconds):
        """Another Hive declared at `seconds`, naming `owner`; returns its Mother stream."""
        hive = R.mint_rappid("example", slug, self.spki[signer])
        member = {"rappid": self.identities[owner], "role": "owner", "area": "members/" + owner}
        declaration = {**copy.deepcopy(self.declaration), "hive_rappid": hive, "created_utc": stamp(seconds),
                       "members": [member],
                       "rooms": [{"id": "general", "area": "rooms/general", "members": [member["rappid"]],
                                  "access": "repository"}]}
        self.frame("hive.declaration", hive, declaration, signer=signer)
        return hive

    def succeeded(self, *lifecycle, sequence=9, **kwargs):
        """alice hands the estate to heir at the boundary by a signed, continuous rotation."""
        return self.registry(sequence, owner="heir", lifecycle=[self.reanchor("alice", "heir"), *lifecycle], **kwargs)


def unsigned(frame):
    return {key: value for key, value in frame.items() if key != "sig"}


class OwnerSuccessionVectors(unittest.TestCase):
    def test_default_authority_still_fails_closed_on_reanchor(self):
        estate = SuccessionEstate()
        member_rotation = estate.reanchor("bob", "bob-next", seconds=60, signer="alice", continuity="bob")
        owned = estate.registry(9, lifecycle=[member_rotation])
        with self.assertRaisesRegex(ValueError, "succession requires a full section-13 tenure verifier"):
            estate.authority(owned, succession=None)
        with self.assertRaisesRegex(ValueError, "succession requires a full section-13 tenure verifier"):
            estate.authority(estate.succeeded(), anchor="heir", succession=None)
        with self.assertRaisesRegex(ValueError, "signature refused"):
            estate.authority(estate.succeeded(), succession=None)
        self.assertEqual(estate.authority(owned).owner, estate.identities["alice"])
        self.assertEqual(estate.authority(estate.registry(), succession=None).owner_at(stamp(10**6)),
                         estate.identities["alice"])

    def test_succession_mode_is_explicit_closed_and_needs_trusted_issuance(self):
        estate = SuccessionEstate()
        with self.assertRaisesRegex(ValueError, "unsupported succession mode"):
            estate.authority(succession="rapp1-13.3")
        for option in ({"tombstone_issued_at": lambda entry_hash: stamp(0)},
                       {"retained_owner_lineage": (estate.identities["alice"],)}):
            with self.subTest(option=sorted(option)), \
                    self.assertRaisesRegex(ValueError, "require explicit succession verification"):
                estate.authority(succession=None, **option)
        for resolver in (None, "2026-09-11T17:00:00.000Z"):
            with self.subTest(resolver=resolver), self.assertRaisesRegex(ValueError, "issuance resolver"):
                estate.authority(estate.succeeded(), tombstone_issued_at=resolver)

    def test_planned_rotation_extends_the_original_out_of_band_anchor(self):
        estate = SuccessionEstate()
        authority = estate.authority(estate.succeeded())
        self.assertEqual((authority.anchor, authority.owner), (estate.identities["alice"], estate.identities["heir"]))
        self.assertEqual(authority.owner_at(stamp(BOUNDARY - 1)), estate.identities["alice"])
        self.assertEqual(authority.owner_at(stamp(BOUNDARY)), estate.identities["heir"])
        self.assertEqual(estate.authority(estate.succeeded(), anchor="heir").owner, estate.identities["heir"])
        with self.assertRaisesRegex(ValueError, "owner tenure time"):
            authority.owner_at("2026-13-01T00:00:00.000Z")

    def test_pre_boundary_history_stays_valid_and_only_the_heir_signs_after_it(self):
        estate = SuccessionEstate()
        a, b = estate.object("alice", 10, ["alice/key"]), estate.object("bob", 11, ["bob/key"])
        direct = estate.gate(estate.registry(), succession=None)
        first = estate.commit(direct, estate.proposal(direct, a, b, seconds=100))
        late_bob = estate.object("bob", 160, ["bob/late"], previous=b)
        late_alice = estate.object("alice", 170, ["alice/late"], previous=a)
        gate = estate.gate(estate.succeeded(), minimum_registry_seq=8)
        self.assertEqual(gate.restore(first["frame_hash"])["mother_head_frame_hash"], first["frame_hash"])
        proposal = estate.proposal(gate, late_bob, late_alice, seconds=200)
        self.assertEqual(decision_map(proposal)[late_bob["frame_hash"]], "accepted")
        self.assertEqual(decision_map(proposal)[late_alice["frame_hash"]], "quarantined")
        stale = estate.convergence(gate, proposal, signer="alice")
        checkpoint = gate.checkpoint()
        with self.assertRaisesRegex(ValueError, "superseded"):
            gate.accept_convergence(stale["frame_hash"])
        self.assertEqual(gate.checkpoint(), checkpoint)
        current = estate.commit(gate, proposal, signer="heir")
        self.assertEqual(gate.head["frame_hash"], current["frame_hash"])
        fresh = estate.gate(estate.succeeded(), minimum_registry_seq=8)
        self.assertEqual(fresh.restore(current["frame_hash"]), gate.checkpoint())
        self.assertEqual(fresh.catalog, gate.catalog)

    def test_declaration_is_authorized_by_the_owner_in_tenure_at_its_genesis(self):
        estate = SuccessionEstate()
        cases = {estate.declare(f"later-{owner}-by-{signer}", owner=owner, signer=signer, seconds=200): reason
                 for owner, signer, reason in (("heir", "heir", None), ("alice", "alice", "superseded"),
                                               ("alice", "heir", "owner authorization mismatch"),
                                               ("heir", "alice", "superseded"))}
        document = estate.succeeded()
        for hive, reason in cases.items():
            with self.subTest(hive=hive):
                if reason is None:
                    gate = HiveAcceptance(estate.authority(document), hive, lambda address: estate.chains[address])
                    self.assertEqual(gate.head["stream_id"], hive)
                else:
                    with self.assertRaisesRegex(ValueError, reason):
                        HiveAcceptance(estate.authority(document), hive, lambda address: estate.chains[address])
        self.assertEqual(estate.gate(document).head, estate.mother)

    def test_reconciliation_and_projection_after_the_boundary_belong_to_the_heir(self):
        estate = SuccessionEstate()
        x = estate.object("alice", 10, ["shared/key"])
        y = estate.object("bob", 11, ["shared/key"])
        heir_resolver = estate.reconcile([x, y], signer="heir", seconds=160)
        alice_resolver = estate.reconcile([x, y], signer="alice", seconds=161)
        gate = estate.gate(estate.succeeded())
        proposal = estate.proposal(gate, x, y, heir_resolver, alice_resolver, seconds=200)
        decisions = decision_map(proposal)
        self.assertEqual(decisions[heir_resolver["frame_hash"]], "accepted")
        self.assertEqual(decisions[alice_resolver["frame_hash"]], "quarantined")
        self.assertEqual({decisions[x["frame_hash"]], decisions[y["frame_hash"]]}, {"superseded"})
        estate.commit(gate, proposal, signer="heir")
        artifacts = estate.projection_artifacts(gate)
        resolve = {"artifact_resolver": lambda space, value: artifacts[(space, value)]}
        stale, manifest = estate.receipt(gate, signer="alice")
        with self.assertRaises(ValueError):
            gate.accept_projection(stale["frame_hash"], manifest_bytes=octets(manifest), **resolve)
        receipt, manifest = estate.receipt(gate, signer="heir")
        result = gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest), **resolve)
        self.assertEqual((result["status"], result["registry_seq"]), ("current", 9))

    def test_succession_record_must_be_signed_by_the_outgoing_owner(self):
        estate = SuccessionEstate()
        for variant, reason in (("heir-signs", "re-anchor owner signature refused"),
                                ("heir-continuity", "re-anchor old-key signature refused"),
                                ("outsider-registry", "section-13 refusal: JWS kid does not match")):
            with self.subTest(variant=variant):
                record = estate.reanchor("alice", "heir",
                                         signer="heir" if variant == "heir-signs" else None,
                                         continuity="heir" if variant == "heir-continuity" else None)
                document = estate.registry(9, owner="heir", lifecycle=[record],
                                           signer="outsider" if variant == "outsider-registry" else None)
                for anchor in ("alice", "heir"):
                    with self.assertRaisesRegex(ValueError, reason):
                        estate.authority(document, anchor=anchor)

    def test_empty_or_backwards_owner_tenure_is_refused(self):
        estate = SuccessionEstate()
        for seconds, accepted in ((BOUNDARY - 10, False), (BOUNDARY, False), (BOUNDARY + 10, True)):
            with self.subTest(seconds=seconds):
                onward = estate.reanchor("heir", "outsider", seconds=seconds)
                document = estate.registry(9, owner="outsider",
                                           lifecycle=[estate.reanchor("alice", "heir"), onward])
                if accepted:
                    authority = estate.authority(document)
                    self.assertEqual([authority.owner_at(stamp(value)) for value in (0, BOUNDARY, seconds)],
                                     [estate.identities[name] for name in ("alice", "heir", "outsider")])
                else:
                    with self.assertRaisesRegex(ValueError, "nonempty, forward tenure"):
                        estate.authority(document)

    def test_retained_owner_lineage_refuses_rewritten_succession_history(self):
        estate = SuccessionEstate()
        accepted = estate.authority(estate.succeeded())
        self.assertEqual(accepted.owner_lineage, (estate.identities["alice"], estate.identities["heir"]))
        rewritten = estate.succeeded(estate.reanchor("carol", "alice", seconds=100), sequence=10)
        self.assertEqual(estate.authority(rewritten).owner_lineage[0], estate.identities["carol"])
        with self.assertRaisesRegex(ValueError, "rewrites retained history"):
            estate.authority(rewritten, minimum_registry_seq=9, retained_owner_lineage=accepted.owner_lineage)
        extended = estate.registry(10, owner="outsider", lifecycle=[
            estate.reanchor("alice", "heir"), estate.reanchor("heir", "outsider", seconds=BOUNDARY + 50)])
        self.assertEqual(estate.authority(extended, minimum_registry_seq=9,
                                          retained_owner_lineage=accepted.owner_lineage).owner_lineage,
                         tuple(estate.identities[name] for name in ("alice", "heir", "outsider")))

    def test_anchor_must_be_in_the_owner_lineage_and_bind_its_key(self):
        estate = SuccessionEstate()
        document = estate.succeeded()
        for anchor in ("outsider", "bob"):
            with self.subTest(anchor=anchor), self.assertRaisesRegex(ValueError, "does not descend"):
                estate.authority(document, anchor=anchor)
        with self.assertRaisesRegex(ValueError, "does not bind"):
            RegistryAuthority(octets(document), owner_rappid=estate.identities["alice"],
                              owner_spki_der=estate.spki["heir"], succession=SUCCESSION,
                              tombstone_issued_at=estate.issuance.__getitem__)

    def test_owner_compromise_recovers_only_through_a_new_anchor(self):
        estate = SuccessionEstate()
        a = estate.object("alice", 10, ["alice/key"])
        direct = estate.gate(estate.registry(), succession=None)
        first = estate.commit(direct, estate.proposal(direct, a, seconds=100))
        compromised = estate.object("alice", 125, ["alice/after-cutoff"], previous=a)
        compromise = estate.reanchor("alice", "heir", case="compromise")
        burned = estate.tombstone("alice", revoked=120, issued=BOUNDARY, signer="heir")
        document = estate.registry(9, owner="heir", lifecycle=[compromise, burned])
        with self.assertRaisesRegex(ValueError, "new out-of-band anchor"):
            estate.authority(document)
        without_tombstone = estate.registry(9, owner="heir", lifecycle=[compromise])
        with self.assertRaisesRegex(ValueError, "registered tombstone"):
            estate.authority(without_tombstone, anchor="heir")
        gate = estate.gate(document, anchor="heir", minimum_registry_seq=8)
        gate.restore(first["frame_hash"])
        self.assertEqual(gate.catalog, direct.catalog)
        proposal = estate.proposal(gate, compromised, seconds=130)
        self.assertEqual(decision_map(proposal)[compromised["frame_hash"]], "quarantined")
        with self.assertRaisesRegex(ValueError, "tombstoned"):
            gate.accept_convergence(estate.convergence(gate, proposal, signer="alice")["frame_hash"])
        with self.assertRaisesRegex(ValueError, "authorization mismatch"):
            gate.accept_convergence(estate.convergence(gate, proposal, signer="heir")["frame_hash"])
        final = estate.commit(gate, estate.proposal(gate, compromised, seconds=200), signer="heir")
        self.assertEqual(gate.catalog, direct.catalog)
        fresh = estate.gate(document, anchor="heir", minimum_registry_seq=8)
        self.assertEqual(fresh.restore(final["frame_hash"]), gate.checkpoint())

    def test_missing_or_untrusted_issuance_is_refused_never_guessed(self):
        estate = SuccessionEstate()
        burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
        document = estate.registry(9, lifecycle=[burned])
        self.assertEqual(estate.authority(document).owner, estate.identities["alice"])
        for resolver, reason in ((lambda entry_hash: {}[entry_hash], "issuance context refused"),
                                 (lambda entry_hash: "not-a-time", "did not supply a valid UTC"),
                                 (lambda entry_hash: None, "did not supply a valid UTC"),
                                 (lambda entry_hash: stamp(BOUNDARY + 10), "tombstone owner signature refused")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                estate.authority(estate.succeeded(burned), tombstone_issued_at=resolver)
        with self.assertRaisesRegex(ValueError, "issuance"):
            estate.authority(document, tombstone_issued_at=lambda entry_hash: {}[entry_hash])

    def test_issuance_time_not_the_cutoff_selects_the_tombstone_issuer(self):
        estate = SuccessionEstate()
        stale = estate.tombstone("bob", revoked=40, issued=BOUNDARY + 10, signer="alice")
        with self.assertRaisesRegex(ValueError, "tombstone owner signature refused"):
            estate.authority(estate.succeeded(stale))
        current = estate.tombstone("bob", revoked=40, issued=BOUNDARY + 10, signer="heir")
        self.assertEqual(estate.authority(estate.succeeded(current)).owner, estate.identities["heir"])

    def test_compromise_before_a_rotation_invalidates_that_rotation(self):
        estate = SuccessionEstate()
        discovered = estate.tombstone("alice", revoked=100, issued=BOUNDARY + 50, signer="heir")
        with self.assertRaisesRegex(ValueError, "rotation old-key authority refused"):
            estate.authority(estate.succeeded(discovered), anchor="heir")

    def test_member_compromise_revokes_only_after_its_cutoff(self):
        estate = SuccessionEstate()
        early = estate.object("bob", 20, ["bob/early"])
        late = estate.object("bob", 50, ["bob/late"], previous=early)
        successor = estate.object("bob-next", 70, ["bob-next/data"])
        compromise = estate.reanchor("bob", "bob-next", case="compromise", seconds=60, signer="alice")
        burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
        with self.assertRaisesRegex(ValueError, "registered tombstone"):
            estate.authority(estate.registry(9, lifecycle=[compromise]))
        forged = estate.reanchor("bob", "bob-next", case="compromise", seconds=60, signer="outsider")
        with self.assertRaisesRegex(ValueError, "re-anchor owner signature refused"):
            estate.authority(estate.registry(9, lifecycle=[forged, burned]))
        gate = estate.gate(estate.registry(9, lifecycle=[compromise, burned]))
        decisions = decision_map(estate.proposal(gate, early, late, successor, seconds=100))
        self.assertEqual(decisions[early["frame_hash"]], "accepted")
        self.assertEqual(decisions[late["frame_hash"]], "quarantined")
        self.assertEqual(decisions[successor["frame_hash"]], "quarantined")

    def test_ambiguous_predecessor_is_refused(self):
        estate = SuccessionEstate()
        second = estate.reanchor("outsider", "heir", seconds=BOUNDARY + 10, signer="heir")
        with self.assertRaisesRegex(ValueError, "more than one predecessor"):
            estate.authority(estate.succeeded(second))

    def test_renamed_alias_cannot_become_a_fresh_owner_or_revive_a_retired_key(self):
        estate = SuccessionEstate(device=True)
        with self.assertRaisesRegex(ValueError, "fresh identity tail"):
            estate.authority(estate.registry(9, owner="device", lifecycle=[estate.reanchor("alice", "device")]))
        back = estate.reanchor("heir", "device", seconds=BOUNDARY + 10)
        with self.assertRaisesRegex(ValueError, "ancestral identity tail"):
            estate.authority(estate.registry(9, owner="device", lifecycle=[estate.reanchor("alice", "heir"), back]))
        early = estate.object("device", 20, ["device/early"])
        late = estate.object("device", 160, ["device/late"], previous=early)
        gate = estate.gate(estate.succeeded())
        decisions = decision_map(estate.proposal(gate, early, late, seconds=200))
        self.assertEqual(decisions[early["frame_hash"]], "accepted")
        self.assertEqual(decisions[late["frame_hash"]], "quarantined")
        ok, why = gate.registry.verify_signature(unsigned(late), late["sig"])
        self.assertFalse(ok)
        self.assertIn("superseded", why)
        self.assertEqual(gate.registry.verify_signature(unsigned(early), early["sig"]), (True, "ok"))

    def test_unverifiable_owner_succession_cases_fail_closed(self):
        estate = SuccessionEstate()
        for case in ("upgrade", "tag-migrate"):
            with self.subTest(case=case):
                record = estate.reanchor("alice", "heir", case=case)
                with self.assertRaisesRegex(ValueError, "not verifiable"):
                    estate.authority(estate.registry(9, owner="heir", lifecycle=[record]), anchor="heir")

    def test_current_owner_key_must_be_live(self):
        estate = SuccessionEstate()
        burned = estate.tombstone("heir", revoked=BOUNDARY + 20, issued=BOUNDARY + 20, signer="heir")
        with self.assertRaisesRegex(ValueError, "current estate owner key is not live"):
            estate.authority(estate.succeeded(burned))

    def test_deprecated_predecessor_key_still_verifies_its_own_history(self):
        estate = SuccessionEstate()
        a = estate.object("alice", 10, ["alice/key"])
        direct = estate.gate(estate.registry(), succession=None)
        first = estate.commit(direct, estate.proposal(direct, a, seconds=100))
        gate = estate.gate(estate.succeeded(deprecated=("alice",)), minimum_registry_seq=8)
        self.assertEqual(gate.restore(first["frame_hash"])["catalog_hash"], particle_hash(direct.catalog))

    def test_registry_high_water_and_fork_rules_are_unchanged(self):
        estate = SuccessionEstate()
        document = estate.succeeded()
        authority = estate.authority(document)
        with self.assertRaisesRegex(ValueError, "rollback"):
            estate.authority(document, minimum_registry_seq=10)
        with self.assertRaisesRegex(ValueError, "same-sequence fork"):
            estate.authority(document, minimum_registry_seq=9, same_sequence_hash="e" * 64)
        with self.assertRaisesRegex(ValueError, "same-sequence hash is required"):
            estate.authority(document, minimum_registry_seq=9)
        self.assertEqual(estate.authority(document, minimum_registry_seq=9,
                                          same_sequence_hash=authority.commitment).commitment, authority.commitment)
        tampered = copy.deepcopy(document)
        tampered["registry_seq"] = 10
        with self.assertRaisesRegex(ValueError, "section-13 refusal"):
            estate.authority(tampered)


def run():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OwnerSuccessionVectors)
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    raise SystemExit(0 if run().wasSuccessful() else 1)
