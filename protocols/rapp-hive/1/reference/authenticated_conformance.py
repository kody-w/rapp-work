"""Real Ed25519 acceptance and scalar parity vectors; all identities are fixtures."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator, FormatChecker

import rapp as R
import rapp_hive as H
from hive_acceptance import HiveAcceptance, RegistryAuthority
from rapp_profile import bounded_int, canonical_object, particle_hash, relative_path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema.json").read_text())


def octets(value) -> bytes:
    return R.canonical(value).encode("utf-8")


def stamp(seconds: int) -> str:
    value = datetime(2026, 9, 11, 17, tzinfo=timezone.utc) + timedelta(seconds=seconds)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Estate:
    def __init__(self, *, conflict=False, sealed_room=False):
        self.private, self.spki, self.identities = {}, {}, {}
        for name in ("alice", "bob", "carol", "viewer", "outsider"):
            seed = hashlib.sha256(("PUBLIC TEST VECTOR ONLY: " + name).encode()).digest()
            key = Ed25519PrivateKey.from_private_bytes(seed)
            spki = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
            self.private[name], self.spki[name] = key, spki
            self.identities[name] = R.mint_rappid(name, "member", spki)
        self.hive = R.mint_rappid("example", "private-hive", self.spki["alice"])
        self.chains, self.genesis, self.artifacts = {}, {}, {}
        members = [
            {"rappid": self.identities[name], "role": role, "area": "members/" + name}
            for name, role in (("alice", "owner"), ("bob", "member"), ("carol", "member"), ("viewer", "viewer"))
        ]
        self.declaration = {
            "schema": H.DECLARATION_SCHEMA, "hive_rappid": self.hive, "world_id": "example-world",
            "created_utc": stamp(0), "authority_channel_id": "github-main",
            "members": sorted(members, key=lambda item: item["rappid"]),
            "rooms": [
                {"id": "general", "area": "rooms/general", "members": sorted(item["rappid"] for item in members),
                 "access": "repository"},
                *([{"id": "sealed", "area": "rooms/sealed", "members": sorted(item["rappid"] for item in members),
                    "access": "sealed"}] if sealed_room else []),
            ],
            "channels": [{"id": "github-main", "kind": "github", "role": "authority",
                          "locator": "https://example.invalid/private-hive", "writeback": True}],
            "policy": {"godd_sharing": "explicit", "default_godd_scope": "local-only",
                       "external_publication": "disabled", "conflict_mode": "explicit", "default_transfer": "copy"},
        }
        self.mother = self.frame("hive.declaration", self.hive, self.declaration)
        self.a = self.object("alice", 10, ["shared/key" if conflict else "alice/key"])
        self.b = self.object("bob", 11, ["shared/key" if conflict else "bob/key"])
        self.receipt_genesis = self.frame("hive.projection", self.stream("alice", "receipts"), {
            "schema": H.PROJECTION_SCHEMA, "hive_rappid": self.hive, "convergence_payload_hash": "0" * 64,
            "channel_id": "github-main", "projected_utc": stamp(1), "registry_seq": 0,
            "catalog_hash": particle_hash(H.catalog_payload(self.declaration, {})),
            "frame_head": self.mother["frame_hash"], "artifact_manifest_hash": "0" * 64, "status": "stale",
        })

    def stream(self, owner: str, slug="dimension") -> str:
        return R.mint_rappid(owner, slug, self.spki[owner])

    def sign(self, value: dict, signer="alice") -> str:
        protected = b64(octets({"alg": "EdDSA", "b64": False, "crit": ["b64"], "kid": self.identities[signer]}))
        signature = self.private[signer].sign(protected.encode("ascii") + b"." + octets(value))
        return protected + ".." + b64(signature)

    def frame(self, kind, stream, payload, *, previous=None, signer="alice", signed=True):
        sequence = previous["seq"] + 1 if previous is not None else 0
        frame = R.build_frame(kind, stream, sequence, payload.get("created_utc", payload.get("projected_utc")),
                              payload, previous["payload_hash"] if previous is not None else None)
        if signed:
            frame["sig"] = self.sign({key: value for key, value in frame.items() if key != "sig"}, signer)
        chain = self.chains[previous["frame_hash"]][:] if previous is not None else []
        self.chains[frame["frame_hash"]] = chain + [octets(frame)]
        if previous is None:
            self.genesis[stream] = frame["frame_hash"]
        return frame

    def object(self, producer, seconds, keys, *, previous=None, stream=None, hive=None, world="example-world",
               signer=None, signed=True, sources=(), target=None, room="general",
               protection="member-visible"):
        data = {"fixture": producer, "revision": seconds}
        address = particle_hash(data)
        self.artifacts[("rapp/1:particle", address)] = octets(data)
        payload = {
            "schema": H.OBJECT_SCHEMA, "hive_rappid": hive or self.hive,
            "object_rappid": self.stream(producer, "object"), "producer_rappid": self.identities[producer],
            "world_id": world, "created_utc": stamp(seconds), "room_id": room,
            "audience": next(item["members"] for item in self.declaration["rooms"] if item["id"] == room),
            "object": {"space": "rapp/1:particle", "hash": address, "kind": "example-data", "data_class": "neutral",
                       "pii_status": "not-applicable", "pii_evidence_hash": None, "protection": protection,
                       "target_path": target or f"members/{producer}/data.json"},
            "source_frames": sorted([
                {key: frame[key] for key in ("stream_id", "seq", "utc", "payload_hash", "frame_hash")}
                for frame in sources
            ], key=lambda item: (item["utc"], item["frame_hash"])),
            "mutation_keys": sorted(keys),
        }
        return self.frame("hive.object", stream or self.stream(producer), payload, previous=previous,
                          signer=signer or producer, signed=signed)

    def reconcile(self, parents, *, signer="alice", seconds=40, base=None, previous=None, stream=None, signed=True):
        result = {"fixture": "explicit reconciliation", "revision": seconds}
        address = particle_hash(result)
        self.artifacts[("rapp/1:particle", address)] = octets(result)
        payload = {
            "schema": H.RECONCILIATION_SCHEMA, "hive_rappid": self.hive, "world_id": "example-world",
            "resolver_rappid": self.identities[signer], "created_utc": stamp(seconds),
            "base_head_frame_hash": (base or self.mother)["frame_hash"],
            "parents": sorted(frame["frame_hash"] for frame in parents),
            "mutation_keys": sorted({key for frame in parents for key in frame["payload"]["mutation_keys"]}),
            "result": {"space": "rapp/1:particle", "hash": address},
        }
        return self.frame("hive.reconciliation", stream or self.stream(signer, "resolver"), payload,
                          previous=previous, signer=signer, signed=signed)

    def registry(self, sequence=8):
        entries = [
            {"type": "estate_owner", "rappid": self.identities["alice"]},
            {"type": "protocol", "name": "rapp-hive/1", "spec_repo": "example/profile",
             "spec_path": "protocols/rapp-hive/1/SPEC.md",
             "spec_hash": hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(), "deprecated": False},
        ]
        entries.extend({"type": "kind", "kind": kind, "family": "body", "deprecated": False} for kind in H.KIND_SCHEMAS)
        entries.extend({"type": "spki", "rappid": self.identities[name],
                        "spki_der_b64": base64.b64encode(key).decode("ascii"), "deprecated": False}
                       for name, key in self.spki.items())
        entries.extend({"type": "genesis", "stream_id": stream, "frame_hash": value, "deprecated": False}
                       for stream, value in sorted(self.genesis.items()))
        document = {"schema": "rapp/1-registry", "registry_seq": sequence,
                    "canonical_source": "https://example.invalid/registry", "entries": entries}
        document["sig"] = self.sign(document)
        return document

    def authority(self, document=None, **kwargs):
        return RegistryAuthority(octets(document or self.registry()), owner_rappid=self.identities["alice"],
                                 owner_spki_der=self.spki["alice"], **kwargs)

    def gate(self, document=None):
        return HiveAcceptance(self.authority(document), self.hive, lambda address: self.chains[address])

    def candidates(self, *frames):
        return sorted([
            {"dimension_rappid": frame["stream_id"], "source_channel_ids": ["github-main"],
             **{key: frame[key] for key in ("stream_id", "seq", "utc", "payload_hash", "frame_hash")},
             "mutation_keys": frame["payload"]["mutation_keys"][:]}
            for frame in frames
        ], key=lambda item: (item["utc"], item["frame_hash"]))

    def proposal(self, gate, *frames, seconds=100):
        return gate.preview_convergence(self.candidates(*frames), stamp(seconds))

    def convergence(self, gate, payload, *, signer="alice", signed=True, previous=None):
        return self.frame("hive.convergence", self.hive, payload, previous=previous or gate.head,
                          signer=signer, signed=signed)

    def commit(self, gate, payload):
        frame = self.convergence(gate, payload)
        gate.accept_convergence(frame["frame_hash"])
        return frame

    def receipt(self, gate, *, payload_changes=None, manifest=None, previous=None):
        manifest = manifest or gate.artifact_manifest()
        payload = {
            "schema": H.PROJECTION_SCHEMA, "hive_rappid": self.hive,
            "convergence_payload_hash": gate.head["payload_hash"], "channel_id": "github-main",
            "projected_utc": stamp(200), "registry_seq": gate.registry.sequence,
            "catalog_hash": particle_hash(gate.catalog), "frame_head": gate.head["frame_hash"],
            "artifact_manifest_hash": particle_hash(manifest), "status": "current",
        }
        payload.update(payload_changes or {})
        frame = self.frame("hive.projection", self.receipt_genesis["stream_id"], payload,
                          previous=previous or self.receipt_genesis)
        return frame, manifest

    def projection_artifacts(self, gate):
        artifacts = dict(self.artifacts)
        artifacts.update({("rapp/1:wave", value): octets(frame) for value, frame in gate._retained.items()})
        artifacts.update({("rapp/1:particle", value): octets(catalog) for value, catalog in gate._catalogs.items()})
        registry = gate.registry._document
        artifacts[("rapp/1:particle", particle_hash(registry))] = octets(registry)
        return artifacts


def decision_map(payload):
    return {item["frame_hash"]: item["status"] for item in payload["decisions"]}


class AuthenticatedVectors(unittest.TestCase):
    def test_real_ed25519_signature_and_exact_eleven_keys(self):
        estate = Estate()
        frame = estate.a
        self.assertEqual(set(frame), R.FRAME_KEYS)
        self.assertEqual(len(frame), 11)
        unsigned = {key: value for key, value in frame.items() if key != "sig"}
        self.assertTrue(R.verify_detached_jws(unsigned, frame["sig"], estate.spki["alice"],
                                              estate.identities["alice"])[0])
        self.assertFalse(R.verify_detached_jws(unsigned, frame["sig"], estate.spki["bob"])[0])

    def test_shape_is_not_acceptance(self):
        estate = Estate(conflict=True)
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b)
        for decision in payload["decisions"]:
            decision["status"] = "accepted"
        payload["status"] = "converged"
        payload["resulting_catalog_hash"] = "f" * 64
        self.assertEqual(H.validate_convergence(payload, estate.declaration), particle_hash(payload))
        frame = estate.convergence(gate, payload)
        checkpoint = gate.checkpoint()
        with self.assertRaisesRegex(ValueError, "decisions differ"):
            gate.accept_convergence(frame["frame_hash"])
        self.assertEqual(gate.checkpoint(), checkpoint)

    def test_sealed_room_cannot_accept_member_visible_plaintext(self):
        estate = Estate(sealed_room=True)
        bad = estate.object(
            "alice",
            20,
            ["sealed/secret"],
            room="sealed",
            protection="member-visible",
        )
        gate = estate.gate()
        proposal = estate.proposal(gate, bad)
        self.assertEqual(decision_map(proposal)[bad["frame_hash"]], "quarantined")
        estate.commit(gate, proposal)
        self.assertEqual(gate.catalog["frames"], [])

    def test_independent_signed_frames_derive_catalog(self):
        estate = Estate()
        gate = estate.gate()
        before = gate.checkpoint()
        payload = estate.proposal(gate, estate.a, estate.b)
        self.assertEqual(gate.checkpoint(), before)
        self.assertEqual(set(decision_map(payload).values()), {"accepted"})
        expected = {
            "schema": H.CATALOG_SCHEMA, "hive_rappid": estate.hive, "world_id": "example-world",
            "frames": sorted([{"frame_hash": frame["frame_hash"], "payload_hash": frame["payload_hash"]}
                              for frame in (estate.a, estate.b)], key=lambda item: item["frame_hash"]),
        }
        self.assertEqual(payload["resulting_catalog_hash"], particle_hash(expected))
        self.assertEqual(payload, estate.proposal(gate, estate.a, estate.b))
        result = gate.accept_convergence(estate.convergence(gate, payload)["frame_hash"])
        self.assertIs(result["authenticated"], True)
        self.assertEqual(gate.catalog, expected)

    def test_exact_kind_schema_binding(self):
        estate = Estate()
        wrong = estate.frame("hive.object", estate.hive, estate.declaration)
        with self.assertRaisesRegex(ValueError, "kind-to-schema"):
            H.authorize_hive_frame(
                wrong, expected_schema=H.DECLARATION_SCHEMA, head=None, stream_id=estate.hive,
                registered_kinds=set(H.KIND_SCHEMAS), signature_verifier=estate.authority().verify_signature,
                authorization_verifier=lambda frame, purpose: True,
            )
        unknown = estate.frame("hive.unregistered", estate.hive, {"schema": None, "created_utc": stamp(0)})
        with self.assertRaisesRegex(ValueError, "kind-to-schema"):
            H.authorize_hive_frame(
                unknown, expected_schema=None, head=None, stream_id=estate.hive,
                registered_kinds={"hive.unregistered"}, signature_verifier=estate.authority().verify_signature,
                authorization_verifier=lambda frame, purpose: True,
            )

    def test_authorization_result_must_be_true_not_truthy(self):
        estate = Estate()
        with self.assertRaisesRegex(ValueError, "signer is not authorized"):
            H.authorize_hive_frame(
                estate.mother, expected_schema=H.DECLARATION_SCHEMA, head=None, stream_id=estate.hive,
                registered_kinds=set(H.KIND_SCHEMAS), signature_verifier=estate.authority().verify_signature,
                authorization_verifier=lambda frame, purpose: (False, "denied"),
            )

    def test_missing_ancestor_quarantines_only_dependent_frame(self):
        estate = Estate()
        successor = estate.object("alice", 20, ["bob/key"], previous=estate.a)
        estate.chains[successor["frame_hash"]] = [octets(successor)]
        gate = estate.gate()
        payload = estate.proposal(gate, successor, estate.b)
        self.assertEqual(decision_map(payload), {successor["frame_hash"]: "quarantined", estate.b["frame_hash"]: "accepted"})
        estate.commit(gate, payload)
        self.assertEqual(gate.catalog["frames"], [{"frame_hash": estate.b["frame_hash"], "payload_hash": estate.b["payload_hash"]}])

    def test_unoffered_ancestor_is_not_silently_accepted(self):
        estate = Estate()
        successor = estate.object("alice", 20, ["bob/key"], previous=estate.a)
        gate = estate.gate()
        payload = estate.proposal(gate, successor, estate.b)
        self.assertEqual(decision_map(payload)[successor["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
        estate.commit(gate, payload)

    def test_signed_noncontiguous_sequence_and_wrong_predecessor(self):
        for options in ({"seq": 2}, {"prev": "f" * 64}, {"prev_wave": "f" * 64}):
            with self.subTest(options=options):
                estate = Estate()
                valid = estate.object("alice", 20, ["bob/key"], previous=estate.a)
                fields = {"seq": 1, "prev": estate.a["payload_hash"], "prev_wave": None, **options}
                bad = R.build_frame("hive.object", valid["stream_id"], fields["seq"], valid["utc"],
                                    valid["payload"], fields["prev"], prev_wave=fields["prev_wave"])
                bad["sig"] = estate.sign({key: value for key, value in bad.items() if key != "sig"})
                estate.chains[bad["frame_hash"]] = [octets(estate.a), octets(bad)]
                gate = estate.gate()
                payload = estate.proposal(gate, estate.a, bad, estate.b)
                self.assertEqual(decision_map(payload)[bad["frame_hash"]], "quarantined")
                self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
                estate.commit(gate, payload)

    def test_signature_tamper_cannot_block_valid_mutation(self):
        estate = Estate(conflict=True)
        bad = copy.deepcopy(estate.a)
        protected, _, signature = bad["sig"].split(".")
        signature_bytes = bytearray(R._b64url_decode(signature))
        signature_bytes[-1] ^= 1
        bad["sig"] = protected + ".." + b64(bytes(signature_bytes))
        estate.chains[bad["frame_hash"]] = [octets(bad)]
        gate = estate.gate()
        payload = estate.proposal(gate, bad, estate.b)
        self.assertEqual(decision_map(payload)[bad["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
        estate.commit(gate, payload)

    def test_foreign_hive_and_world_are_quarantined(self):
        for overrides in ({"hive": R.mint_rappid("foreign", "hive", b"fixture")},
                          {"world": "another-world"}):
            with self.subTest(overrides=overrides):
                estate = Estate()
                bad = estate.object("carol", 12, ["bob/key"], **overrides)
                gate = estate.gate()
                payload = estate.proposal(gate, bad, estate.b)
                self.assertEqual(decision_map(payload)[bad["frame_hash"]], "quarantined")
                self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
                estate.commit(gate, payload)

    def test_unauthorized_producer_viewer_and_target_area(self):
        variants = [
            ("carol", {"signer": "bob"}),
            ("viewer", {}),
            ("outsider", {}),
            ("bob", {"target": "members/alice/stolen.json", "stream": None}),
        ]
        for producer, kwargs in variants:
            with self.subTest(producer=producer, kwargs=kwargs):
                estate = Estate()
                kwargs["stream"] = estate.stream(producer, "unauthorized")
                bad = estate.object(producer, 20, ["alice/key"], **kwargs)
                gate = estate.gate()
                payload = estate.proposal(gate, bad, estate.a)
                self.assertEqual(decision_map(payload)[bad["frame_hash"]], "quarantined")
                self.assertEqual(decision_map(payload)[estate.a["frame_hash"]], "accepted")
                estate.commit(gate, payload)

    def test_summary_stream_mutations_and_channels_are_not_trusted(self):
        for field, value in (("stream_id", "unbound"), ("dimension_rappid", R.mint_rappid("other", "dimension", b"fixture")),
                             ("mutation_keys", ["bob/key"]), ("payload_hash", "a" * 64),
                             ("seq", 5), ("source_channel_ids", ["unregistered"])):
            with self.subTest(field=field):
                estate = Estate()
                gate = estate.gate()
                candidates = estate.candidates(estate.a, estate.b)
                next(item for item in candidates if item["frame_hash"] == estate.a["frame_hash"])[field] = value
                payload = gate.preview_convergence(candidates, stamp(100))
                self.assertEqual(decision_map(payload)[estate.a["frame_hash"]], "quarantined")
                self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
                estate.commit(gate, payload)

    def test_payload_and_envelope_time_must_agree(self):
        estate = Estate()
        bad = copy.deepcopy(estate.a)
        bad["utc"] = stamp(12)
        unsigned = R.build_frame(bad["kind"], bad["stream_id"], 0, bad["utc"], bad["payload"], None)
        unsigned["sig"] = estate.sign({key: value for key, value in unsigned.items() if key != "sig"})
        estate.genesis[unsigned["stream_id"]] = unsigned["frame_hash"]
        estate.chains[unsigned["frame_hash"]] = [octets(unsigned)]
        gate = estate.gate()
        payload = estate.proposal(gate, unsigned, estate.b)
        self.assertEqual(decision_map(payload)[unsigned["frame_hash"]], "quarantined")

    def test_unsigned_and_unauthorized_mother_frames(self):
        for options in ({"signed": False}, {"signer": "bob"}):
            with self.subTest(options=options):
                estate = Estate()
                gate = estate.gate()
                frame = estate.convergence(gate, estate.proposal(gate, estate.a), **options)
                before = gate.checkpoint()
                with self.assertRaises(ValueError):
                    gate.accept_convergence(frame["frame_hash"])
                self.assertEqual(gate.checkpoint(), before)

    def test_stale_base_commitments(self):
        for field in ("base_head_frame_hash", "base_convergence_payload_hash", "base_catalog_hash"):
            with self.subTest(field=field):
                estate = Estate()
                gate = estate.gate()
                payload = estate.proposal(gate, estate.a)
                payload[field] = "a" * 64
                frame = estate.convergence(gate, payload)
                with self.assertRaisesRegex(ValueError, "stale base"):
                    gate.accept_convergence(frame["frame_hash"])
                self.assertEqual(gate.head, estate.mother)

    def test_same_base_competing_mother_successor_and_replay(self):
        estate = Estate()
        gate = estate.gate()
        first = estate.convergence(gate, estate.proposal(gate, estate.a))
        second = estate.convergence(gate, estate.proposal(gate, estate.b))
        gate.accept_convergence(first["frame_hash"])
        with self.assertRaisesRegex(ValueError, "competing Mother Hive"):
            gate.accept_convergence(second["frame_hash"])
        with self.assertRaisesRegex(ValueError, "Mother Hive frame replay"):
            gate.accept_convergence(first["frame_hash"])

    def test_simultaneous_mother_successors_use_one_compare_and_swap(self):
        estate = Estate()
        gate = estate.gate()
        frames = [estate.convergence(gate, estate.proposal(gate, candidate)) for candidate in (estate.a, estate.b)]

        def attempt(frame):
            try:
                gate.accept_convergence(frame["frame_hash"])
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, frames)), [False, True])
        self.assertEqual(len(gate.catalog["frames"]), 1)

    def test_required_duplicate_and_no_catalog_replay(self):
        estate = Estate()
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        catalog = gate.catalog
        payload = estate.proposal(gate, estate.a, seconds=101)
        self.assertEqual(decision_map(payload), {estate.a["frame_hash"]: "duplicate"})
        wrong = copy.deepcopy(payload)
        wrong["decisions"][0]["status"] = "accepted"
        with self.assertRaisesRegex(ValueError, "required duplicate"):
            gate.accept_convergence(estate.convergence(gate, wrong)["frame_hash"])
        estate.commit(gate, payload)
        self.assertEqual(gate.catalog, catalog)

    def test_causal_sequential_updates_in_one_batch(self):
        estate = Estate()
        successor = estate.object("alice", 20, ["alice/key"], previous=estate.a)
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, successor)
        self.assertEqual(set(decision_map(payload).values()), {"accepted"})
        estate.commit(gate, payload)
        self.assertEqual(len(gate.catalog["frames"]), 2)
        self.assertEqual(set(gate._active()), {successor["frame_hash"]})

    def test_equal_utc_hash_order_does_not_replace_causal_order(self):
        estate = Estate()
        for number in range(256):
            payload = copy.deepcopy(estate.a["payload"])
            payload["object"]["kind"] = f"equal-time-{number}"
            successor = estate.frame("hive.object", estate.a["stream_id"], payload, previous=estate.a)
            if successor["frame_hash"] < estate.a["frame_hash"]:
                break
        self.assertLess(successor["frame_hash"], estate.a["frame_hash"])
        gate = estate.gate()
        proposal = estate.proposal(gate, estate.a, successor)
        self.assertEqual(proposal["candidates"][0]["frame_hash"], successor["frame_hash"])
        self.assertEqual(set(decision_map(proposal).values()), {"accepted"})
        estate.commit(gate, proposal)

    def test_causal_updates_across_batches_and_signed_source_streams(self):
        estate = Estate()
        successor = estate.object("alice", 20, ["alice/key"], previous=estate.a)
        sourced = estate.object("bob", 30, ["alice/key"], previous=estate.b, sources=[successor])
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
        payload = estate.proposal(gate, successor, sourced, seconds=101)
        self.assertEqual(set(decision_map(payload).values()), {"accepted"})
        estate.commit(gate, payload)
        self.assertEqual(set(gate._active()), {estate.b["frame_hash"], sourced["frame_hash"]})

    def test_signed_source_summary_tamper(self):
        estate = Estate()
        bad = estate.object("bob", 30, ["alice/key"], previous=estate.b, sources=[estate.a])
        payload = copy.deepcopy(bad["payload"])
        payload["source_frames"][0]["payload_hash"] = "e" * 64
        bad = estate.frame("hive.object", bad["stream_id"], payload, previous=estate.b, signer="bob")
        gate = estate.gate()
        proposal = estate.proposal(gate, estate.a, estate.b, bad)
        self.assertEqual(decision_map(proposal)[bad["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(proposal)[estate.a["frame_hash"]], "accepted")

    def test_body_stream_fork_is_not_an_independent_update(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        payload = estate.proposal(gate, left, right, estate.b, seconds=101)
        self.assertEqual(decision_map(payload)[left["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[right["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")
        estate.commit(gate, payload)

    def test_committed_stream_head_rejects_competing_branch(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a, left))
        payload = estate.proposal(gate, right, estate.b, seconds=101)
        self.assertEqual(decision_map(payload)[right["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "accepted")

    def test_known_fork_branches_and_descendants_stay_quarantined_on_retry(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        descendants = [
            estate.object("alice", 30, ["left/child"], previous=left),
            estate.object("alice", 31, ["right/child"], previous=right),
            estate.object("carol", 32, ["sourced/key"], sources=[left]),
        ]
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        estate.commit(gate, estate.proposal(gate, left, right, estate.b, seconds=101))
        catalog = gate.catalog
        for index, candidate in enumerate([left, right, *descendants]):
            with self.subTest(candidate=candidate["frame_hash"]):
                proposal = estate.proposal(gate, candidate, seconds=102 + index)
                self.assertEqual(decision_map(proposal), {candidate["frame_hash"]: "quarantined"})
                self.assertEqual(proposal["decisions"][0]["reason_code"],
                                 "stream-fork" if candidate["stream_id"] == left["stream_id"] else "fork-ancestor")
                estate.commit(gate, proposal)
                self.assertEqual(gate.catalog, catalog)

    def test_later_batch_fork_invalidates_original_branch_and_transitive_dependents(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        sourced = estate.object("bob", 30, ["sourced/key"], previous=estate.b, sources=[left])
        descendant = estate.object("bob", 40, ["later/key"], previous=sourced)
        independent = estate.object("carol", 41, ["independent/key"])
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a, estate.b, left, sourced))
        history = gate.catalog["frames"]
        proposal = estate.proposal(gate, right, independent, seconds=101)
        self.assertEqual(decision_map(proposal), {
            right["frame_hash"]: "quarantined", independent["frame_hash"]: "accepted",
        })
        estate.commit(gate, proposal)
        self.assertTrue(set(item["frame_hash"] for item in history) <=
                        set(item["frame_hash"] for item in gate.catalog["frames"]))
        self.assertNotIn(left["frame_hash"], gate._active())
        self.assertNotIn(sourced["frame_hash"], gate._active())
        restored = estate.gate()
        restored.restore(gate.head["frame_hash"])
        gate = restored
        for index, candidate in enumerate((left, sourced, descendant)):
            proposal = estate.proposal(gate, candidate, seconds=102 + index)
            self.assertEqual(decision_map(proposal)[candidate["frame_hash"]], "quarantined")
            estate.commit(gate, proposal)

    def test_fork_frontier_restores_from_retained_mother_history(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        estate.commit(gate, estate.proposal(gate, left, right, seconds=101))
        head = estate.commit(gate, estate.proposal(gate, estate.b, seconds=102))
        manifest = gate.artifact_manifest()
        addresses = {item["hash"] for item in manifest["artifacts"] if item["space"] == "rapp/1:wave"}
        self.assertTrue({left["frame_hash"], right["frame_hash"]} <= addresses)
        retained = {value: estate.chains[value] for value in addresses}
        restored = HiveAcceptance(estate.authority(), estate.hive, lambda value: retained[value])
        self.assertEqual(restored.restore(head["frame_hash"]), gate.checkpoint())
        self.assertEqual(restored.artifact_manifest(), manifest)
        self.assertEqual(restored._forks, gate._forks)
        for candidate in (left, right):
            proposal = estate.proposal(restored, candidate, seconds=103)
            self.assertEqual(decision_map(proposal)[candidate["frame_hash"]], "quarantined")
        receipt, manifest = estate.receipt(restored)
        retained[receipt["frame_hash"]] = estate.chains[receipt["frame_hash"]]
        artifacts = estate.projection_artifacts(restored)
        self.assertEqual(restored.accept_projection(
            receipt["frame_hash"], manifest_bytes=octets(manifest),
            artifact_resolver=lambda space, value: artifacts[(space, value)],
        )["status"], "current")

    def test_missing_recorded_fork_evidence_cannot_restore_a_clean_frontier(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        head = estate.commit(gate, estate.proposal(gate, left, right, seconds=101))
        del estate.chains[left["frame_hash"]]
        del estate.chains[right["frame_hash"]]
        restored = estate.gate()
        with self.assertRaisesRegex(ValueError, "fork evidence"):
            restored.restore(head["frame_hash"])
        with self.assertRaisesRegex(ValueError, "failed history recovery"):
            estate.proposal(restored, estate.b, seconds=102)
        with self.assertRaisesRegex(ValueError, "failed history recovery"):
            restored.checkpoint()

    def test_preview_and_rejected_convergence_do_not_latch_forks(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        proposal = estate.proposal(gate, left, right, seconds=101)
        self.assertEqual(gate._forks, {})
        wrong = copy.deepcopy(proposal)
        wrong["resulting_catalog_hash"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "catalog hash"):
            gate.accept_convergence(estate.convergence(gate, wrong)["frame_hash"])
        self.assertEqual(gate._forks, {})
        self.assertNotIn(left["frame_hash"], gate._retained)
        self.assertEqual(decision_map(estate.proposal(gate, left, seconds=102))[left["frame_hash"]], "accepted")

    def test_unauthenticated_fork_or_false_summary_cannot_latch(self):
        for forged_summary in (False, True):
            with self.subTest(forged_summary=forged_summary):
                estate = Estate()
                left = estate.object("alice", 20, ["left/key"], previous=estate.a)
                wrong = estate.object("alice", 21, ["right/key"], previous=estate.a, signer="bob")
                successor = estate.object("alice", 30, ["child/key"], previous=left)
                gate = estate.gate()
                estate.commit(gate, estate.proposal(gate, estate.a))
                candidates = estate.candidates(left, estate.b if forged_summary else wrong)
                if forged_summary:
                    summary = next(item for item in candidates if item["frame_hash"] == estate.b["frame_hash"])
                    summary.update(stream_id=left["stream_id"], dimension_rappid=left["stream_id"], seq=left["seq"])
                proposal = gate.preview_convergence(candidates, stamp(101))
                estate.commit(gate, proposal)
                self.assertEqual(gate._forks, {})
                restored = estate.gate()
                restored.restore(gate.head["frame_hash"])
                self.assertEqual(restored._forks, {})
                self.assertEqual(decision_map(estate.proposal(restored, successor, seconds=102)),
                                 {successor["frame_hash"]: "accepted"})

    def test_fork_evidence_diagnostics_cannot_be_erased_or_invented(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        gate = estate.gate()
        proposal = estate.proposal(gate, estate.a)
        proposal["decisions"][0]["reason_code"] = "local-audit-description"
        estate.commit(gate, proposal)
        proposal = estate.proposal(gate, left, right, seconds=101)
        for item in proposal["decisions"]:
            item["reason_code"] = "invalid-candidate"
        with self.assertRaisesRegex(ValueError, "fork evidence"):
            gate.accept_convergence(estate.convergence(gate, proposal)["frame_hash"])
        proposal = estate.proposal(gate, estate.b, seconds=102)
        proposal["decisions"][0]["reason_code"] = "stream-fork"
        with self.assertRaisesRegex(ValueError, "fork evidence"):
            gate.accept_convergence(estate.convergence(gate, proposal)["frame_hash"])
        self.assertEqual(gate._forks, {})

    def test_fork_in_signed_source_ancestry_is_persistent_without_direct_candidates(self):
        estate = Estate()
        left = estate.object("alice", 20, ["left/key"], previous=estate.a)
        right = estate.object("alice", 21, ["right/key"], previous=estate.a)
        first = estate.object("bob", 30, ["first/key"], previous=estate.b, sources=[left])
        second = estate.object("carol", 31, ["second/key"], sources=[right])
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
        proposal = estate.proposal(gate, first, second, seconds=101)
        self.assertEqual(set(decision_map(proposal).values()), {"quarantined"})
        self.assertEqual({item["reason_code"] for item in proposal["decisions"]}, {"fork-ancestor"})
        estate.commit(gate, proposal)
        restored = estate.gate()
        restored.restore(gate.head["frame_hash"])
        for candidate in (left, right):
            self.assertEqual(decision_map(estate.proposal(restored, candidate, seconds=102)),
                             {candidate["frame_hash"]: "quarantined"})

    def test_owner_reconciliation_cannot_clear_a_stream_fork(self):
        estate = Estate()
        left = estate.object("alice", 20, ["shared/key"], previous=estate.a)
        right = estate.object("alice", 21, ["shared/key"], previous=estate.a)
        resolver = estate.reconcile([left, right])
        gate = estate.gate()
        proposal = estate.proposal(gate, estate.a, left, right, resolver)
        self.assertEqual(decision_map(proposal)[resolver["frame_hash"]], "quarantined")
        self.assertEqual(proposal["resolutions"], [])
        estate.commit(gate, proposal)
        self.assertEqual(decision_map(estate.proposal(gate, left, seconds=101)),
                         {left["frame_hash"]: "quarantined"})

    def test_concurrent_conflicts_preserve_every_parent(self):
        estate = Estate(conflict=True)
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b)
        self.assertEqual(set(decision_map(payload).values()), {"conflict"})
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["base_catalog_hash"], payload["resulting_catalog_hash"])
        estate.commit(gate, payload)
        with self.assertRaisesRegex(ValueError, "retain every unresolved"):
            estate.proposal(gate, estate.a, seconds=101)

    def test_signed_complete_reconciliation_and_superseded_replay(self):
        estate = Estate(conflict=True)
        resolver = estate.reconcile([estate.a, estate.b])
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b, resolver)
        self.assertEqual(decision_map(payload), {estate.a["frame_hash"]: "superseded",
                                                estate.b["frame_hash"]: "superseded", resolver["frame_hash"]: "accepted"})
        self.assertEqual(payload["resolutions"][0]["frame_hashes"], sorted([estate.a["frame_hash"], estate.b["frame_hash"]]))
        self.assertNotIn(resolver["frame_hash"], payload["resolutions"][0]["frame_hashes"])
        estate.commit(gate, payload)
        self.assertEqual(len(gate.catalog["frames"]), 1)
        replay = estate.proposal(gate, estate.a, estate.b, resolver, seconds=101)
        self.assertEqual(set(decision_map(replay).values()), {"duplicate"})
        self.assertEqual(replay["base_catalog_hash"], replay["resulting_catalog_hash"])
        estate.commit(gate, replay)

    def test_reconciliation_after_partial_head(self):
        estate = Estate(conflict=True)
        gate = estate.gate()
        partial = estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
        resolver = estate.reconcile([estate.a, estate.b], seconds=120, base=partial)
        # A fresh authenticated registry registers the new resolver stream.
        resumed = estate.gate()
        resumed.restore(partial["frame_hash"])
        payload = estate.proposal(resumed, estate.a, estate.b, resolver, seconds=150)
        self.assertEqual(payload["status"], "converged")
        estate.commit(resumed, payload)

    def test_unsigned_unauthorized_and_stale_resolvers(self):
        for options in ({"signed": False}, {"signer": "bob"}, {"base": {"frame_hash": "d" * 64}}):
            with self.subTest(options=options):
                estate = Estate(conflict=True)
                resolver = estate.reconcile([estate.a, estate.b], **options)
                independent = estate.object("carol", 25, ["independent"])
                gate = estate.gate()
                payload = estate.proposal(gate, estate.a, estate.b, resolver, independent)
                self.assertEqual(decision_map(payload)[resolver["frame_hash"]], "quarantined")
                self.assertEqual(decision_map(payload)[independent["frame_hash"]], "accepted")
                self.assertEqual(decision_map(payload)[estate.a["frame_hash"]], "conflict")
                estate.commit(gate, payload)

    def test_omitted_parent_cannot_resolve_three_way_conflict(self):
        estate = Estate(conflict=True)
        third = estate.object("carol", 12, ["shared/key"])
        resolver = estate.reconcile([estate.a, estate.b])
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b, third, resolver)
        self.assertEqual(decision_map(payload)[resolver["frame_hash"]], "quarantined")
        for frame in (estate.a, estate.b, third):
            self.assertEqual(decision_map(payload)[frame["frame_hash"]], "conflict")
        next(item for item in payload["decisions"] if item["frame_hash"] == resolver["frame_hash"])["status"] = "accepted"
        with self.assertRaisesRegex(ValueError, "decisions differ"):
            gate.accept_convergence(estate.convergence(gate, payload)["frame_hash"])

    def test_reconciliation_summary_cannot_omit_signed_parent(self):
        estate = Estate(conflict=True)
        third = estate.object("carol", 12, ["shared/key"])
        resolver = estate.reconcile([estate.a, estate.b, third])
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b, third, resolver)
        payload["resolutions"][0]["frame_hashes"].pop()
        with self.assertRaisesRegex(ValueError, "complete parent sets"):
            gate.accept_convergence(estate.convergence(gate, payload)["frame_hash"])

    def test_causally_intermediate_conflicting_parent_cannot_be_omitted(self):
        for complete in (False, True):
            with self.subTest(complete=complete):
                estate = Estate(conflict=True)
                successor = estate.object("alice", 20, ["shared/key"], previous=estate.a)
                parents = [estate.a, successor, estate.b] if complete else [successor, estate.b]
                resolver = estate.reconcile(parents)
                gate = estate.gate()
                payload = estate.proposal(gate, estate.a, successor, estate.b, resolver)
                self.assertEqual(decision_map(payload)[resolver["frame_hash"]], "accepted" if complete else "quarantined")
                estate.commit(gate, payload)

    def test_ordinary_object_cannot_implicitly_join_concurrent_parents(self):
        estate = Estate(conflict=True)
        joined = estate.object("carol", 30, ["shared/key"], sources=[estate.a, estate.b])
        gate = estate.gate()
        proposal = estate.proposal(gate, estate.a, estate.b, joined)
        self.assertEqual(set(decision_map(proposal).values()), {"conflict"})
        estate.commit(gate, proposal)

    def test_competing_resolvers_are_not_timestamp_winners(self):
        estate = Estate(conflict=True)
        first = estate.reconcile([estate.a, estate.b])
        second = estate.reconcile([estate.a, estate.b], seconds=41, stream=estate.stream("alice", "resolver-two"))
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b, first, second)
        self.assertEqual(decision_map(payload)[first["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[second["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.a["frame_hash"]], "conflict")
        self.assertEqual(payload["resolutions"], [])
        estate.commit(gate, payload)

    def test_invalid_resolver_descendant_cannot_poison_independent_conflict_set(self):
        estate = Estate(conflict=True)
        third = estate.object("carol", 12, ["shared/key"])
        resolver = estate.reconcile([estate.a, estate.b])
        descendant = estate.object("alice", 45, ["independent"], previous=resolver, stream=resolver["stream_id"])
        independent = estate.object("bob", 50, ["independent"], stream=estate.stream("bob", "independent"))
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b, third, resolver, descendant, independent)
        self.assertEqual(decision_map(payload)[resolver["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[descendant["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[independent["frame_hash"]], "accepted")
        estate.commit(gate, payload)

    def test_atomic_multi_key_reconciliation_covers_all_effects(self):
        for complete in (False, True):
            with self.subTest(complete=complete):
                estate = Estate()
                a = estate.object("alice", 20, ["first", "second"])
                b = estate.object("bob", 21, ["first"])
                resolver = estate.reconcile([a, b], seconds=40)
                if not complete:
                    payload = copy.deepcopy(resolver["payload"])
                    payload["mutation_keys"] = ["first"]
                    resolver = estate.frame("hive.reconciliation", resolver["stream_id"], payload)
                gate = estate.gate()
                payload = estate.proposal(gate, a, b, resolver)
                self.assertEqual(decision_map(payload)[resolver["frame_hash"]], "accepted" if complete else "quarantined")
                estate.commit(gate, payload)
                if complete:
                    self.assertEqual(set(gate._active()), {resolver["frame_hash"]})

    def test_catalog_tamper_is_refused_after_resigning_mother(self):
        estate = Estate()
        gate = estate.gate()
        payload = estate.proposal(gate, estate.a, estate.b)
        payload["resulting_catalog_hash"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "catalog hash differs"):
            gate.accept_convergence(estate.convergence(gate, payload)["frame_hash"])
        self.assertEqual(gate.head, estate.mother)
        self.assertEqual(gate.catalog["frames"], [])

    def test_restore_reverifies_signed_history_and_duplicates(self):
        estate = Estate()
        gate = estate.gate()
        head = estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
        fresh = estate.gate()
        self.assertEqual(fresh.restore(head["frame_hash"]), gate.checkpoint())
        self.assertEqual(fresh.catalog, gate.catalog)
        payload = estate.proposal(fresh, estate.a, estate.b, seconds=101)
        self.assertEqual(set(decision_map(payload).values()), {"duplicate"})

    def test_real_current_projection_checks_every_artifact(self):
        estate = Estate()
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
        receipt, manifest = estate.receipt(gate)
        artifacts = estate.projection_artifacts(gate)
        result = gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                        artifact_resolver=lambda space, value: artifacts[(space, value)])
        self.assertEqual(result["status"], "current")
        self.assertIs(result["authenticated"], True)
        self.assertEqual(result["registry_seq"], 8)

    def test_unsigned_or_unauthorized_projection_is_not_current(self):
        for options in ({"signed": False}, {"signer": "bob"}):
            with self.subTest(options=options):
                estate = Estate()
                gate = estate.gate()
                estate.commit(gate, estate.proposal(gate, estate.a))
                receipt, manifest = estate.receipt(gate)
                bad = estate.frame("hive.projection", receipt["stream_id"], receipt["payload"],
                                   previous=estate.receipt_genesis, **options)
                artifacts = estate.projection_artifacts(gate)
                with self.assertRaises(ValueError):
                    gate.accept_projection(bad["frame_hash"], manifest_bytes=octets(manifest),
                                           artifact_resolver=lambda space, value: artifacts[(space, value)])

    def test_current_projection_registry_head_catalog_and_manifest_binding(self):
        for field, value in (("registry_seq", 7), ("registry_seq", 9), ("frame_head", "e" * 64),
                             ("catalog_hash", "e" * 64), ("artifact_manifest_hash", "e" * 64)):
            with self.subTest(field=field, value=value):
                estate = Estate()
                gate = estate.gate()
                estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
                receipt, manifest = estate.receipt(gate, payload_changes={field: value})
                artifacts = estate.projection_artifacts(gate)
                with self.assertRaises(ValueError):
                    gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                           artifact_resolver=lambda space, value: artifacts[(space, value)])
                self.assertEqual(gate._receipt_heads, {})

    def test_projection_manifest_omission_and_artifact_tamper(self):
        for mutation in ("omitted-address", "artifact-bytes", "missing-bytes", "frame-signature"):
            with self.subTest(mutation=mutation):
                estate = Estate()
                gate = estate.gate()
                estate.commit(gate, estate.proposal(gate, estate.a, estate.b))
                manifest = gate.artifact_manifest()
                artifacts = estate.projection_artifacts(gate)
                if mutation == "omitted-address":
                    manifest["artifacts"].pop()
                elif mutation == "artifact-bytes":
                    artifacts[("rapp/1:particle", estate.a["payload"]["object"]["hash"])] = b'{"tampered":true}'
                elif mutation == "missing-bytes":
                    del artifacts[("rapp/1:particle", estate.a["payload"]["object"]["hash"])]
                else:
                    altered = copy.deepcopy(estate.a)
                    altered["sig"] = None
                    artifacts[("rapp/1:wave", estate.a["frame_hash"])] = octets(altered)
                receipt, manifest = estate.receipt(gate, manifest=manifest)
                with self.assertRaisesRegex(ValueError, "projection"):
                    gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                           artifact_resolver=lambda space, value: artifacts[(space, value)])

    def test_projection_cannot_claim_an_old_accepted_convergence_is_current(self):
        estate = Estate()
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        receipt, manifest = estate.receipt(gate)
        artifacts = estate.projection_artifacts(gate)
        estate.commit(gate, estate.proposal(gate, estate.b, seconds=101))
        with self.assertRaisesRegex(ValueError, "actual Mother Hive head"):
            gate.accept_projection(receipt["frame_hash"], manifest_bytes=octets(manifest),
                                   artifact_resolver=lambda space, value: artifacts[(space, value)])

    def test_projection_replay_is_not_a_new_current_receipt(self):
        estate = Estate()
        gate = estate.gate()
        estate.commit(gate, estate.proposal(gate, estate.a))
        receipt, manifest = estate.receipt(gate)
        artifacts = estate.projection_artifacts(gate)
        kwargs = {"manifest_bytes": octets(manifest), "artifact_resolver": lambda space, value: artifacts[(space, value)]}
        gate.accept_projection(receipt["frame_hash"], **kwargs)
        with self.assertRaisesRegex(ValueError, "receipt replay"):
            gate.accept_projection(receipt["frame_hash"], **kwargs)

    def test_registry_signature_anchor_rollback_and_same_sequence_fork(self):
        estate = Estate()
        good = estate.registry()
        authority = estate.authority(good)
        with self.assertRaisesRegex(ValueError, "rollback"):
            estate.authority(good, minimum_registry_seq=9)
        with self.assertRaisesRegex(ValueError, "same-sequence fork"):
            estate.authority(good, minimum_registry_seq=8, same_sequence_hash="e" * 64)
        self.assertEqual(estate.authority(good, minimum_registry_seq=8,
                                         same_sequence_hash=authority.commitment).sequence, 8)
        for field, value in (("registry_seq", 9), ("sig", None)):
            wrong = copy.deepcopy(good)
            wrong[field] = value
            with self.assertRaisesRegex(ValueError, "signature refused"):
                estate.authority(wrong)
        with self.assertRaisesRegex(ValueError, "signature refused"):
            RegistryAuthority(octets(good), owner_rappid=estate.identities["bob"], owner_spki_der=estate.spki["bob"])

    def test_registry_profile_pin_kind_family_and_registered_genesis(self):
        for variant in ("profile", "kind-family", "genesis"):
            with self.subTest(variant=variant):
                estate = Estate()
                registry = estate.registry()
                if variant == "profile":
                    next(entry for entry in registry["entries"] if entry["type"] == "protocol")["spec_hash"] = "e" * 64
                elif variant == "kind-family":
                    next(entry for entry in registry["entries"] if entry.get("kind") == "hive.reconciliation")["family"] = "memory"
                else:
                    next(entry for entry in registry["entries"] if entry.get("stream_id") == estate.hive)["frame_hash"] = "e" * 64
                registry["sig"] = estate.sign({key: value for key, value in registry.items() if key != "sig"})
                with self.assertRaises(ValueError):
                    estate.gate(registry)

    def test_signed_tombstone_revokes_candidate_not_independent_member(self):
        estate = Estate(conflict=True)
        registry = estate.registry()
        tombstone = {"type": "tombstone", "rappid": estate.identities["bob"], "revoked_utc": stamp(5)}
        tombstone["sig"] = estate.sign(tombstone)
        registry["entries"].append(tombstone)
        registry["sig"] = estate.sign({key: value for key, value in registry.items() if key != "sig"})
        gate = estate.gate(registry)
        payload = estate.proposal(gate, estate.a, estate.b)
        self.assertEqual(decision_map(payload)[estate.b["frame_hash"]], "quarantined")
        self.assertEqual(decision_map(payload)[estate.a["frame_hash"]], "accepted")
        estate.commit(gate, payload)


class ScalarParityVectors(unittest.TestCase):
    def agrees(self, definition, value, validator, expected):
        schema = {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": "#/$defs/" + definition}
        try:
            canonical_object({"value": value}, "shared RAPP/I-JSON scalar domain")
            schema_ok = Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(value)
        except (ValueError, TypeError):
            schema_ok = False
        try:
            canonical_object({"value": value}, "shared RAPP/I-JSON scalar domain")
            validator(value)
            python_ok = True
        except (ValueError, TypeError):
            python_ok = False
        self.assertEqual((schema_ok, python_ok), (expected, expected), (definition, repr(value)))

    def test_schema_is_valid_draft_2020_12(self):
        Draft202012Validator.check_schema(SCHEMA)

    def test_uint53_boundaries(self):
        for value, expected in ((0, True), (2**53 - 1, True), (-1, False), (2**53, False),
                                (True, False), (False, False), (1.0, False), ("1", False)):
            with self.subTest(value=value):
                self.agrees("uint53", value, lambda item: bounded_int(item, "uint53", 0, H.UINT53_MAX), expected)

    def test_rappid_lengths_and_grammar(self):
        values = [
            (f"rappid:@{'a' * 39}/{'b' * 100}:" + "c" * 64, True),
            ("rappid:@a/b:" + "c" * 64, True),
            (f"rappid:@{'a' * 40}/b:" + "c" * 64, False),
            (f"rappid:@a/{'b' * 101}:" + "c" * 64, False),
            ("rappid:@a--b/c:" + "c" * 64, False),
            ("rappid:@a/b--c:" + "c" * 64, False),
            ("rappid:@a-/b:" + "c" * 64, False),
            ("rappid:@A/b:" + "c" * 64, False),
            ("rappid:@a/b:" + "c" * 64 + "\n", False),
        ]
        for value, expected in values:
            with self.subTest(value=value):
                self.agrees("rappid", value, lambda item: H.rappid(item, "rappid"), expected)

    def test_portable_paths(self):
        valid = ["a", "a/b.json", "a/.hidden", "a...b/file", "é/file", "a" * 1024]
        invalid = ["", ".", "..", "/a", "a/", "a//b", "a/./b", "a/../b", "a/.", "a/..", "a\\b", "C:foo",
                   "a:b", "a\x00b", "a\nb", "a\x7fb", "a.", "a ", "a/b./c", "CON", "con.txt", "a/LpT9.log",
                   "a/aux/file", "a.../file", "a" * 1025, "e\u0301/file"]
        for value in valid + invalid:
            with self.subTest(value=repr(value)):
                self.agrees("relativePath", value, lambda item: relative_path(item, "path"), value in valid)

    def test_mutation_keys_are_opaque_bounded_text_not_paths(self):
        valid = ["x", "account:one", "x" * 256, "x" * 257, "x" * 512, "../opaque-key", "é"]
        invalid = ["", "x" * 513, "a\nb", "a\x00b", "a\x7fb", "e\u0301", True]
        for value in valid + invalid:
            with self.subTest(value=repr(value)):
                self.agrees("mutationKey", value, lambda item: H.mutation_key(item, "mutation"), value in valid)

    def test_sealed_plaintext_limit(self):
        definition = SCHEMA["$defs"]["goddSlice"]["properties"]["content"]["properties"]["plaintext_bytes"]
        for value, expected in ((0, True), (2**30, True), (2**30 + 1, False), (-1, False), (True, False)):
            with self.subTest(value=value):
                self.assertEqual(Draft202012Validator(definition).is_valid(value), expected)
                try:
                    bounded_int(value, "plaintext_bytes", 0, R.MAX_SEALED_PLAINTEXT_BYTES)
                    valid = True
                except ValueError:
                    valid = False
                self.assertEqual(valid, expected)

    def test_all_derived_and_signed_payloads_match_schema(self):
        estate = Estate(conflict=True)
        resolver = estate.reconcile([estate.a, estate.b])
        gate = estate.gate()
        convergence = estate.proposal(gate, estate.a, estate.b, resolver)
        estate.commit(gate, convergence)
        receipt, manifest = estate.receipt(gate)
        validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
        for document in [estate.declaration, estate.a["payload"], resolver["payload"], convergence,
                         gate.catalog, receipt["payload"], manifest]:
            with self.subTest(schema=document["schema"]):
                validator.validate(document)

    def test_reconciliation_is_closed(self):
        estate = Estate(conflict=True)
        resolver = estate.reconcile([estate.a, estate.b])
        payload = copy.deepcopy(resolver["payload"])
        payload["unsigned_resolution"] = True
        self.assertFalse(Draft202012Validator(SCHEMA).is_valid(payload))
        with self.assertRaisesRegex(ValueError, "expected keys"):
            H.validate_reconciliation(payload, estate.declaration)


def run():
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(AuthenticatedVectors),
        unittest.defaultTestLoader.loadTestsFromTestCase(ScalarParityVectors),
    ])
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    raise SystemExit(0 if run().wasSuccessful() else 1)
