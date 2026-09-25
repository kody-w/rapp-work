"""Real Ed25519 vectors for opt-in RAPP/1 section 13.2 owner succession.

The default RegistryAuthority stays direct-owner and fails closed. These vectors
select succession="rapp1-13.2" explicitly. Every identity is a public fixture.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import sys
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import hive_acceptance
import rapp as R
import rapp_hive as H
from authenticated_conformance import ROOT, Estate, decision_map, octets, stamp
from hive_acceptance import RETAINED_REGISTRY_KEYS, SUCCESSION, HiveAcceptance, RegistryAuthority
from rapp_profile import particle_hash


NAMES = ("alice", "heir", "bob", "bob-next", "carol", "viewer", "outsider")
BOUNDARY = 150
DEFAULT_CHECKPOINT_KEYS = {"registry_seq", "registry_hash", "hive_rappid", "mother_head_frame_hash", "catalog_hash"}


def retained_from(checkpoint):
    """The retained registry state inside a persisted succession checkpoint()."""
    return {key: checkpoint[key] for key in RETAINED_REGISTRY_KEYS}


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

    def registry(self, sequence=8, *, owner="alice", lifecycle=(), deprecated=(), signer=None, spec_hash=None,
                 deprecated_kinds=(), unregistered=()):
        entries = [
            {"type": "estate_owner", "rappid": self.identities[owner]},
            {"type": "protocol", "name": "rapp-hive/1", "spec_repo": "https://example.invalid/profile",
             "spec_path": "protocols/rapp-hive/1/SPEC.md",
             "spec_hash": spec_hash or hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(),
             "deprecated": False},
        ]
        entries.extend({"type": "kind", "kind": kind, "family": "body", "deprecated": kind in deprecated_kinds}
                       for kind in H.KIND_SCHEMAS)
        entries.extend({"type": "spki", "rappid": self.identities[name],
                        "spki_der_b64": base64.b64encode(key).decode("ascii"), "deprecated": name in deprecated}
                       for name, key in self.spki.items() if name not in unregistered)
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

    def retained(self, document=None, **kwargs):
        """The state a consumer retained after accepting `document` (by default the direct-owner registry)."""
        return self.authority(document or self.registry(), **kwargs).retained_registry

    def invite_object(self, producer, seconds, *, egg_signer, egg_seconds):
        """A member object carrying a RAPP/1 invite egg, which only the estate owner may sign (RAPP/1 section 9.2)."""
        rappid = R.mint_rappid("example", "hive-invite", self.spki[egg_signer])
        manifest = {"schema": "rapp/1-egg", "variant": "invite", "rappid": rappid, "created_utc": stamp(egg_seconds),
                    "contents": [], "payload": {"target_rappid": self.hive, "target_kind": "estate",
                                                "target_url": "https://example.invalid/private-hive/chat"}}
        egg = R.pack_egg("invite", rappid, manifest["created_utc"], payload=manifest["payload"],
                         sig=self.sign(manifest, egg_signer))
        address = R.egg_address(manifest)
        self.artifacts[("rapp/1:egg-manifest", address)] = egg
        payload = {
            "schema": H.OBJECT_SCHEMA, "hive_rappid": self.hive,
            "object_rappid": self.stream(producer, "invite-object"), "producer_rappid": self.identities[producer],
            "world_id": "example-world", "created_utc": stamp(seconds), "room_id": "general",
            "audience": next(item["members"] for item in self.declaration["rooms"] if item["id"] == "general"),
            "object": {"space": "rapp/1:egg-manifest", "hash": address, "kind": "example-invite",
                       "data_class": "neutral", "pii_status": "not-applicable", "pii_evidence_hash": None,
                       "protection": "member-visible", "target_path": f"members/{producer}/invite.egg"},
            "source_frames": [], "mutation_keys": [f"{producer}/invite/{egg_signer}/{egg_seconds}"],
        }
        return self.frame("hive.object", self.stream(producer, f"invites-{egg_signer}-{egg_seconds}"), payload,
                          signer=producer)

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
                       {"retained_registry": estate.retained()}):
            with self.subTest(option=sorted(option)), \
                    self.assertRaisesRegex(ValueError, "require explicit succession verification"):
                estate.authority(succession=None, **option)
        for resolver in (None, "2026-09-11T17:00:00.000Z"):
            with self.subTest(resolver=resolver), self.assertRaisesRegex(ValueError, "issuance resolver"):
                estate.authority(estate.succeeded(), tombstone_issued_at=resolver)

    def test_planned_rotation_extends_the_original_out_of_band_anchor(self):
        estate = SuccessionEstate()
        authority = estate.authority(estate.succeeded(), retained_registry=estate.retained())
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
        gate = estate.gate(estate.succeeded(), retained_registry=direct.registry.retained_registry)
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
        fresh = estate.gate(estate.succeeded(), retained_registry=retained_from(gate.checkpoint()))
        self.assertEqual(fresh.restore(current["frame_hash"]), gate.checkpoint())
        self.assertEqual(fresh.catalog, gate.catalog)

    def test_declaration_is_authorized_by_the_owner_in_tenure_at_its_genesis(self):
        estate = SuccessionEstate()
        cases = {estate.declare(f"later-{owner}-by-{signer}", owner=owner, signer=signer, seconds=200): reason
                 for owner, signer, reason in (("heir", "heir", None), ("alice", "alice", "superseded"),
                                               ("alice", "heir", "owner authorization mismatch"),
                                               ("heir", "alice", "superseded"))}
        document, retained = estate.succeeded(), estate.retained()
        for hive, reason in cases.items():
            with self.subTest(hive=hive):
                if reason is None:
                    gate = HiveAcceptance(estate.authority(document, retained_registry=retained), hive,
                                          lambda address: estate.chains[address])
                    self.assertEqual(gate.head["stream_id"], hive)
                else:
                    with self.assertRaisesRegex(ValueError, reason):
                        HiveAcceptance(estate.authority(document, retained_registry=retained), hive,
                                       lambda address: estate.chains[address])
        self.assertEqual(estate.gate(document, retained_registry=retained).head, estate.mother)

    def test_reconciliation_and_projection_after_the_boundary_belong_to_the_heir(self):
        estate = SuccessionEstate()
        x = estate.object("alice", 10, ["shared/key"])
        y = estate.object("bob", 11, ["shared/key"])
        heir_resolver = estate.reconcile([x, y], signer="heir", seconds=160)
        alice_resolver = estate.reconcile([x, y], signer="alice", seconds=161)
        gate = estate.gate(estate.succeeded(), retained_registry=estate.retained())
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
                    authority = estate.authority(document, retained_registry=estate.retained())
                    self.assertEqual([authority.owner_at(stamp(value)) for value in (0, BOUNDARY, seconds)],
                                     [estate.identities[name] for name in ("alice", "heir", "outsider")])
                else:
                    with self.assertRaisesRegex(ValueError, "nonempty, forward tenure"):
                        estate.authority(document)

    def test_retained_registry_state_refuses_rewritten_succession_history(self):
        estate = SuccessionEstate()
        accepted = estate.authority(estate.succeeded(), retained_registry=estate.retained())
        self.assertEqual(accepted.owner_lineage, (estate.identities["alice"], estate.identities["heir"]))
        rewritten = estate.succeeded(estate.reanchor("carol", "alice", seconds=100), sequence=10)
        self.assertEqual(estate.authority(rewritten, anchor="heir").owner_lineage[0], estate.identities["carol"])
        with self.assertRaisesRegex(ValueError, "rewrites retained history"):
            estate.authority(rewritten, retained_registry=accepted.retained_registry)
        extended = estate.registry(10, owner="outsider", lifecycle=[
            estate.reanchor("alice", "heir"), estate.reanchor("heir", "outsider", seconds=BOUNDARY + 50)])
        self.assertEqual(estate.authority(extended, retained_registry=accepted.retained_registry).owner_lineage,
                         tuple(estate.identities[name] for name in ("alice", "heir", "outsider")))

    def test_retained_registry_state_refuses_rollback_of_succession_and_revocation(self):
        estate = SuccessionEstate()
        member_rotation = estate.reanchor("bob", "bob-next", seconds=60, signer="alice", continuity="bob")
        burned = estate.tombstone("carol", revoked=40, issued=60, signer="alice")
        accepted = estate.authority(estate.succeeded(member_rotation, burned), retained_registry=estate.retained())
        retained = accepted.retained_registry
        late_alice, late_bob, late_carol = (estate.object(name, 400, [name + "/after"]) for name in ("alice", "bob", "carol"))
        for frame in (late_alice, late_bob, late_carol):
            self.assertFalse(accepted.verify_signature(unsigned(frame), frame["sig"])[0])
        # A leaked retired anchor key re-signs a higher registry that omits the rotation (review E3).
        rollback = estate.registry(10, owner="alice", lifecycle=[member_rotation, burned])
        with self.assertRaisesRegex(ValueError, "rewrites retained history"):
            estate.authority(rollback, retained_registry=retained)
        with self.assertRaisesRegex(ValueError, "travel only in retained_registry"):
            estate.authority(rollback, minimum_registry_seq=9)
        # Only a consumer that kept no state accepts it: its out-of-band anchor alone decides (RAPP/1 13.1).
        forgetful = estate.authority(rollback)
        self.assertEqual(forgetful.owner_at(stamp(10**6)), estate.identities["alice"])
        self.assertTrue(forgetful.verify_signature(unsigned(late_alice), late_alice["sig"])[0])
        # The current owner cannot drop a revocation, a member re-anchor, or move a boundary (review E4-E6).
        for variant, document in (
                ("drop-tombstone", estate.succeeded(member_rotation, sequence=10)),
                ("drop-member-re-anchor", estate.succeeded(burned, sequence=10)),
                ("move-owner-boundary", estate.registry(10, owner="heir", lifecycle=[
                    estate.reanchor("alice", "heir", seconds=500), member_rotation, burned]))):
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, "dropped or rewritten"):
                estate.authority(document, retained_registry=retained)
        onward = estate.authority(estate.succeeded(member_rotation, burned, sequence=10), retained_registry=retained)
        self.assertEqual(onward.lifecycle, accepted.lifecycle)

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
        with self.assertRaisesRegex(ValueError, "not the registered anchor key"):
            estate.authority(estate.registry(9, unregistered=("alice",)))

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
        gate = estate.gate(document, anchor="heir", retained_registry=direct.registry.retained_registry)
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
        fresh = estate.gate(document, anchor="heir", retained_registry=retained_from(gate.checkpoint()))
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
        self.assertEqual(estate.authority(estate.succeeded(current), retained_registry=estate.retained()).owner,
                         estate.identities["heir"])

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
        gate = estate.gate(estate.succeeded(), retained_registry=estate.retained())
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
        gate = estate.gate(estate.succeeded(deprecated=("alice",)), retained_registry=direct.registry.retained_registry)
        self.assertEqual(gate.restore(first["frame_hash"])["catalog_hash"], particle_hash(direct.catalog))

    def test_registry_high_water_and_fork_rules_are_unchanged(self):
        estate = SuccessionEstate()
        document = estate.succeeded()
        authority = estate.authority(document, retained_registry=estate.retained())
        later = estate.authority(estate.succeeded(sequence=10), retained_registry=authority.retained_registry)
        with self.assertRaisesRegex(ValueError, "rollback"):
            estate.authority(document, retained_registry=later.retained_registry)
        with self.assertRaisesRegex(ValueError, "same-sequence fork"):
            estate.authority(document, retained_registry={**authority.retained_registry, "registry_hash": "e" * 64})
        self.assertEqual(estate.authority(document, retained_registry=authority.retained_registry).commitment,
                         authority.commitment)
        tampered = copy.deepcopy(document)
        tampered["registry_seq"] = 10
        with self.assertRaisesRegex(ValueError, "section-13 refusal"):
            estate.authority(tampered, anchor="heir")

    def test_retained_registry_state_is_required_closed_and_checkpointed(self):
        estate = SuccessionEstate()
        with self.assertRaisesRegex(ValueError, "requires the retained registry state"):
            estate.authority(estate.succeeded())
        for option in ({"minimum_registry_seq": 8}, {"same_sequence_hash": "e" * 64},
                       {"minimum_registry_seq": 8, "retained_registry": estate.retained()}):
            with self.subTest(option=sorted(option)), \
                    self.assertRaisesRegex(ValueError, "travel only in retained_registry"):
                estate.authority(estate.succeeded(), **option)
        good = estate.retained()
        self.assertEqual(good, {"registry_seq": 8, "registry_hash": estate.authority().commitment,
                                "owner_lineage": [estate.identities["alice"]], "registry_lifecycle": []})
        for variant, broken in (
                ("missing", {key: value for key, value in good.items() if key != "registry_lifecycle"}),
                ("extra", {**good, "anchor": estate.identities["alice"]}),
                ("empty-lineage", {**good, "owner_lineage": []}),
                ("repeated-owner", {**good, "owner_lineage": [estate.identities["alice"]] * 2}),
                ("unsorted", {**good, "registry_lifecycle": ["f" * 64, "0" * 64]}),
                ("not-hex", {**good, "registry_lifecycle": ["F" * 64]}),
                ("boolean-seq", {**good, "registry_seq": True}),
                ("bad-hash", {**good, "registry_hash": "0"})):
            with self.subTest(variant=variant), self.assertRaisesRegex(ValueError, "retained registry state"):
                estate.authority(estate.succeeded(), retained_registry=broken)
        direct = estate.gate(estate.registry(), succession=None)
        self.assertEqual(set(direct.checkpoint()), DEFAULT_CHECKPOINT_KEYS)
        gate = estate.gate(estate.succeeded(), retained_registry=direct.registry.retained_registry)
        checkpoint = gate.checkpoint()
        self.assertEqual(set(checkpoint), DEFAULT_CHECKPOINT_KEYS | RETAINED_REGISTRY_KEYS)
        self.assertEqual(retained_from(checkpoint), gate.registry.retained_registry)
        self.assertEqual(checkpoint["owner_lineage"], [estate.identities["alice"], estate.identities["heir"]])
        self.assertEqual(checkpoint["registry_lifecycle"], [particle_hash(estate.reanchor("alice", "heir"))])

    def test_backdated_owner_acts_cannot_reach_state_after_the_boundary(self):
        estate = SuccessionEstate()
        a, b = estate.object("alice", 10, ["alice/key"]), estate.object("bob", 11, ["bob/key"])
        direct = estate.gate(estate.registry(), succession=None)
        first = estate.commit(direct, estate.proposal(direct, a, b, seconds=100))
        late_bob = estate.object("bob", 160, ["bob/late"], previous=b)
        early_bob = estate.object("bob", 140, ["bob/early"], stream=estate.stream("bob", "early"))
        retained = direct.registry.retained_registry
        gate = estate.gate(estate.succeeded(), retained_registry=retained)
        gate.restore(first["frame_hash"])
        before = gate.checkpoint()
        # The retired owner dates a convergence inside its tenure but converges a later frame (review E1).
        backdated = estate.convergence(gate, estate.proposal(gate, late_bob, seconds=BOUNDARY - 1), signer="alice")
        with self.assertRaisesRegex(ValueError, "candidate is later than its convergence"):
            gate.accept_convergence(backdated["frame_hash"])
        self.assertEqual(gate.checkpoint(), before)
        fresh = estate.gate(estate.succeeded(), retained_registry=retained)
        with self.assertRaisesRegex(ValueError, "candidate is later than its convergence"):
            fresh.restore(backdated["frame_hash"])
        # A false candidate summary cannot hide the later frame: its authenticated bytes bound it too.
        disguised = estate.candidates(late_bob)
        disguised[0]["utc"] = stamp(BOUNDARY - 10)
        masked_payload = gate.preview_convergence(disguised, stamp(BOUNDARY - 1))
        self.assertEqual(decision_map(masked_payload)[late_bob["frame_hash"]], "quarantined")
        masked = estate.convergence(gate, masked_payload, signer="alice")
        with self.assertRaisesRegex(ValueError, "candidate frame is later than its convergence"):
            gate.accept_convergence(masked["frame_hash"])
        self.assertEqual(gate.checkpoint(), before)
        # Inside its own tenure a predecessor can still date an act over earlier state (RAPP/1 section 14) ...
        residual = estate.convergence(gate, estate.proposal(gate, early_bob, seconds=BOUNDARY - 1), signer="alice")
        probe = estate.gate(estate.succeeded(), retained_registry=retained)
        probe.restore(first["frame_hash"])
        self.assertEqual(probe.accept_convergence(residual["frame_hash"])["mother_head_frame_hash"],
                         residual["frame_hash"])
        # ... until the successor advances the Mother head past the boundary (here by re-offering a settled frame).
        advanced = estate.commit(gate, estate.proposal(gate, a, seconds=BOUNDARY), signer="heir")
        for seconds, reason in ((BOUNDARY - 1, "utc < head utc"), (BOUNDARY, "superseded")):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(ValueError, reason):
                gate.accept_convergence(estate.convergence(
                    gate, estate.proposal(gate, early_bob, seconds=seconds), signer="alice")["frame_hash"])
        self.assertEqual(gate.head["frame_hash"], advanced["frame_hash"])
        # A compromised key back-dated below its cutoff cannot converge a frame from after it.
        compromise = estate.reanchor("alice", "heir", case="compromise")
        burned = estate.tombstone("alice", revoked=120, issued=BOUNDARY, signer="heir")
        recovered = estate.gate(estate.registry(9, owner="heir", lifecycle=[compromise, burned]), anchor="heir",
                                retained_registry=retained)
        recovered.restore(first["frame_hash"])
        after_cutoff = estate.object("bob", 130, ["bob/after-cutoff"], previous=b)
        with self.assertRaisesRegex(ValueError, "candidate is later than its convergence"):
            recovered.accept_convergence(estate.convergence(
                recovered, estate.proposal(recovered, after_cutoff, seconds=119), signer="alice")["frame_hash"])

    def test_convergence_is_strictly_later_than_the_head_it_extends(self):
        estate = SuccessionEstate()
        a, b = estate.object("alice", 10, ["alice/key"]), estate.object("bob", 20, ["bob/key"])
        direct = estate.gate(estate.registry(), succession=None)
        last = estate.commit(direct, estate.proposal(direct, a, seconds=BOUNDARY - 1))
        same_instant = estate.convergence(direct, estate.proposal(direct, b, seconds=BOUNDARY - 1))
        retained = direct.registry.retained_registry
        # The direct-owner default is unchanged: RAPP/1 section 7.5 step 4 admits an equal utc.
        self.assertEqual(direct.accept_convergence(same_instant["frame_hash"])["mother_head_frame_hash"],
                         same_instant["frame_hash"])
        gate = estate.gate(estate.succeeded(), retained_registry=retained)
        gate.restore(last["frame_hash"])
        with self.assertRaisesRegex(ValueError, "not later than the Mother head it extends"):
            gate.accept_convergence(same_instant["frame_hash"])
        heir = estate.commit(gate, estate.proposal(gate, b, seconds=BOUNDARY), signer="heir")
        self.assertEqual(gate.head["frame_hash"], heir["frame_hash"])

    def test_backdated_reconciliation_cannot_resolve_a_later_mother_head(self):
        estate = SuccessionEstate()
        x = estate.object("alice", 10, ["shared/key"])
        y = estate.object("bob", 11, ["shared/key"])
        gate = estate.gate(estate.succeeded(), retained_registry=estate.retained())
        conflicted = estate.commit(gate, estate.proposal(gate, x, y, seconds=200), signer="heir")
        self.assertEqual(gate.catalog["frames"], [])
        backdated = estate.reconcile([x, y], signer="alice", seconds=BOUNDARY - 1, base=conflicted)
        current = estate.reconcile([x, y], signer="heir", seconds=210, base=conflicted)
        later = estate.gate(estate.succeeded(sequence=10), retained_registry=retained_from(gate.checkpoint()))
        later.restore(conflicted["frame_hash"])
        refused = decision_map(estate.proposal(later, x, y, backdated, seconds=220))
        self.assertEqual(refused[backdated["frame_hash"]], "quarantined")
        self.assertEqual({refused[x["frame_hash"]], refused[y["frame_hash"]]}, {"conflict"})
        accepted = decision_map(estate.proposal(later, x, y, current, seconds=220))
        self.assertEqual(accepted[current["frame_hash"]], "accepted")
        self.assertEqual({accepted[x["frame_hash"]], accepted[y["frame_hash"]]}, {"superseded"})

    def test_current_receipt_cannot_predate_its_convergence_or_registry(self):
        estate = SuccessionEstate()
        a = estate.object("alice", 10, ["alice/key"])
        direct = estate.gate(estate.registry(), succession=None)
        first = estate.commit(direct, estate.proposal(direct, a, seconds=100))
        gate = estate.gate(estate.succeeded(), retained_registry=direct.registry.retained_registry)
        gate.restore(first["frame_hash"])
        artifacts = estate.projection_artifacts(gate)
        resolve = {"artifact_resolver": lambda space, value: artifacts[(space, value)]}
        # alice's own head, alice's tenure, but the named registry records her retirement at the boundary.
        stale, manifest = estate.receipt(gate, signer="alice", seconds=BOUNDARY - 1)
        with self.assertRaisesRegex(ValueError, "receipt predates the latest succession"):
            gate.accept_projection(stale["frame_hash"], manifest_bytes=octets(manifest), **resolve)
        receipt, manifest = estate.receipt(gate, signer="heir", seconds=BOUNDARY)
        self.assertEqual(gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                                **resolve)["status"], "current")
        # A receipt dated before the heir's convergence it attests (review E2).
        other = SuccessionEstate()
        object_a = other.object("alice", 10, ["alice/key"])
        converged = other.gate(other.succeeded(), retained_registry=other.retained())
        other.commit(converged, other.proposal(converged, object_a, seconds=200), signer="heir")
        artifacts = other.projection_artifacts(converged)
        for signer, seconds in (("alice", BOUNDARY - 1), ("heir", BOUNDARY + 10)):
            receipt, manifest = other.receipt(converged, signer=signer, seconds=seconds)
            with self.subTest(signer=signer), self.assertRaisesRegex(ValueError, "earlier than its convergence"):
                converged.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                            artifact_resolver=lambda space, value: artifacts[(space, value)])

    def test_compromise_and_its_tombstone_share_one_observed_append(self):
        estate = SuccessionEstate()
        base = estate.authority(estate.registry(8))
        burned = estate.tombstone("bob", revoked=40, issued=60, signer="alice")
        compromise = estate.reanchor("bob", "bob-next", case="compromise", seconds=60, signer="alice")
        step = estate.authority(estate.registry(9), retained_registry=base.retained_registry)
        together = estate.registry(10, lifecycle=[compromise, burned])
        with self.assertRaisesRegex(ValueError, "verify each intermediate registry in sequence"):
            estate.authority(together, retained_registry=base.retained_registry)
        self.assertEqual(estate.authority(together, retained_registry=step.retained_registry).sequence, 10)
        earlier = estate.authority(estate.registry(10, lifecycle=[burned]), retained_registry=step.retained_registry)
        with self.assertRaisesRegex(ValueError, "same append"):
            estate.authority(estate.registry(11, lifecycle=[burned, compromise]),
                             retained_registry=earlier.retained_registry)

    def test_succession_index_keeps_the_profile_pin_and_live_kinds(self):
        estate = SuccessionEstate()
        retained = estate.retained()
        with self.assertRaisesRegex(ValueError, "specification hash mismatch"):
            estate.authority(estate.succeeded(spec_hash="0" * 64), retained_registry=retained)
        with self.assertRaisesRegex(ValueError, "exact Hive kinds must be registered"):
            estate.authority(estate.succeeded(deprecated_kinds=("hive.convergence",)), retained_registry=retained)
        self.assertEqual(estate.authority(estate.succeeded(), retained_registry=retained).owner,
                         estate.identities["heir"])

    def test_signed_invite_egg_is_checked_against_the_owner_at_its_creation(self):
        cases = (("alice", "alice", 100, 100, None),
                 ("bob", "heir", 170, 160, None),
                 ("bob", "heir", 140, 140, "signed egg refusal"),
                 ("bob", "alice", 170, 160, "signed egg refusal"))
        for producer, egg_signer, seconds, egg_seconds, reason in cases:
            with self.subTest(egg_signer=egg_signer, egg_seconds=egg_seconds):
                estate = SuccessionEstate()
                carried = estate.invite_object(producer, seconds, egg_signer=egg_signer, egg_seconds=egg_seconds)
                gate = estate.gate(estate.succeeded(), retained_registry=estate.retained())
                estate.commit(gate, estate.proposal(gate, carried, seconds=200), signer="heir")
                self.assertEqual(gate.catalog["frames"][0]["frame_hash"], carried["frame_hash"])
                artifacts = estate.projection_artifacts(gate)
                receipt, manifest = estate.receipt(gate, signer="heir", seconds=250)
                accept = lambda: gate.accept_projection(  # noqa: E731
                    receipt["frame_hash"], manifest_bytes=octets(manifest),
                    artifact_resolver=lambda space, value: artifacts[(space, value)])
                if reason is None:
                    self.assertEqual(accept()["status"], "current")
                else:
                    with self.assertRaisesRegex(ValueError, reason):
                        accept()

    def test_default_path_runs_without_the_registry_reference(self):
        saved = sys.modules.get("rapp_registry")
        sys.modules["rapp_registry"] = None
        try:
            spec = importlib.util.spec_from_file_location("hive_acceptance_without_registry",
                                                          hive_acceptance.__file__)
            probe = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(probe)
            estate = SuccessionEstate()
            a = estate.object("alice", 10, ["alice/key"])
            direct = probe.HiveAcceptance(
                probe.RegistryAuthority(octets(estate.registry()), owner_rappid=estate.identities["alice"],
                                        owner_spki_der=estate.spki["alice"]),
                estate.hive, lambda address: estate.chains[address])
            estate.commit(direct, estate.proposal(direct, a))
            self.assertEqual(direct.catalog["frames"], [{"frame_hash": a["frame_hash"], "payload_hash": a["payload_hash"]}])
            self.assertEqual(set(direct.checkpoint()), DEFAULT_CHECKPOINT_KEYS)
            with self.assertRaises(ImportError):
                probe.RegistryAuthority(octets(estate.registry()), owner_rappid=estate.identities["alice"],
                                        owner_spki_der=estate.spki["alice"], succession=SUCCESSION,
                                        tombstone_issued_at=estate.issuance.__getitem__)
        finally:
            if saved is None:
                del sys.modules["rapp_registry"]
            else:
                sys.modules["rapp_registry"] = saved


def run():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OwnerSuccessionVectors)
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    raise SystemExit(0 if run().wasSuccessful() else 1)
