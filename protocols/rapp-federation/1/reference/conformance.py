"""Executable positive/adversarial conformance; writes only owned project state."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import sqlite3
import sys
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jsonschema import Draft202012Validator

from rapp_federation import Clock, Federation, Registry, SCHEMA, validate
from schema_source import CONFORMANCE_CLASS, KINDS, MIND, PROFILE, schema_bytes
from vectors import DAY, LEASE, ROOT, World, digest, fixture_bytes, resign, stamp
from wire import (
    FRAME_KEYS, H, Refusal, b64, canonical, decrypt_sealed, inspect_sealed, keyed_rappid,
    loads, sealed_aad, signature_header, unsigned, verify_frame,
)


NEGATIVE_RESULTS = []
VERIFIED_FIXTURE_COUNT = 0


class Vectors(unittest.TestCase):
    def setUp(self):
        self.gates = []
        self.paths = []

    def tearDown(self):
        for gate in self.gates:
            gate.close()
        for path in self.paths:
            for suffix in ("", "-journal", "-wal", "-shm"):
                candidate = Path(str(path) + suffix)
                if candidate.exists():
                    candidate.unlink()

    def fresh(self, *, through=None, clock=None, **kwargs):
        world = World(**kwargs)
        path = ROOT / "reference" / (".conformance-" + uuid.uuid4().hex + ".sqlite3")
        self.paths.append(path)
        gate = world.gate(path, clock=clock)
        self.gates.append(gate)
        if through:
            world.load(gate, through=through)
        return world, gate

    def before(self, world, gate, name):
        position = world.order.index(name)
        if position:
            world.load(gate, through=world.order[position - 1])

    def reject(self, code, function, *args, **kwargs):
        with self.assertRaises(Refusal) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)
        NEGATIVE_RESULTS.append({"test": self.id().split(".")[-1], "refusal": code})

    def modified(self, world, frame, change, *, signer=None):
        altered = copy.deepcopy(frame)
        change(altered)
        if signer is None:
            actor = signature_header(frame["sig"])[0]
            signer = next(name for name, identity in world.ids.items() if identity == actor)
        return resign(altered, signer, world)

    def registry_signed(self, world, document, cell="source"):
        document = copy.deepcopy(document)
        document["sig"] = world.signature(unsigned(document), cell + "-owner")
        return canonical(document)

    def restart(self, world, gate):
        path = next(Path(row[2]) for row in gate.db.execute("PRAGMA database_list") if row[1] == "main")
        gate.close()
        self.gates.remove(gate)
        reopened = world.gate(path)
        self.gates.append(reopened)
        return reopened


class ShapeAndCrypto(Vectors):
    def test_federation_uses_registered_memory_streams_owned_by_exact_signer(self):
        world = World()
        for name in world.order:
            frame = world.frames[name]
            self.assertTrue(frame["stream_id"].startswith(signature_header(frame["sig"])[0] + ":"))
        for registry in world.registries.values():
            self.assertTrue(all(entry["family"] == "memory" for entry in registry["entries"] if entry["type"] == "kind"))
        for stream in (world.ids["source-requester"], "net:universal-hive"):
            changed = copy.deepcopy(world.request)
            changed["stream_id"] = stream
            self.reject("schema", validate, changed)

    def test_calendar_validation_does_not_require_optional_jsonschema_format_packages(self):
        frame = copy.deepcopy(World().request)
        frame["utc"] = "2026-02-30T00:00:00.000Z"
        self.reject("utc", validate, frame)
        frame["utc"] = stamp(7)
        frame["payload"]["terms"]["not_after"] = "2026-13-01T00:00:00.000Z"
        self.reject("utc", validate, frame)

    def test_https_validation_does_not_require_optional_jsonschema_format_packages(self):
        world = World()
        discovery = world.discovery()
        discovery["payload"]["endpoint"] = "https://example.invalid:65536/chat"
        self.reject("endpoint", validate, discovery)
        registry = copy.deepcopy(world.registries["source"])
        registry["canonical_source"] = "https:///not-a-host"
        self.reject("registry-locator", validate, registry, "registry")

    def test_noncanonical_envelope_bytes_are_refused_not_rewritten(self):
        world, gate = self.fresh(through="agreement-approval")
        pretty = json.dumps(world.request, indent=2).encode("utf-8")
        self.reject("frame-noncanonical", gate.accept, pretty)
        self.reject("frame-noncanonical", gate.stage, pretty)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_schema_is_closed_and_generated_exactly(self):
        self.assertEqual((ROOT / "schema.json").read_bytes(), schema_bytes())
        Draft202012Validator.check_schema(SCHEMA)
        objects = []

        def visit(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    objects.append(value)
                    self.assertIs(value.get("additionalProperties"), False)
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(SCHEMA)
        self.assertGreaterEqual(len(objects), 25)

    def test_public_fixture_bytes_are_reproducible(self):
        raw = (ROOT / "fixtures" / "ed25519-bilateral.json").read_bytes()
        self.assertEqual(raw, fixture_bytes())
        fixture = json.loads(raw)
        self.assertGreater(len(fixture["frames"]), 25)
        self.assertEqual({entry["frame"]["kind"] for entry in fixture["frames"]},
                         {"federation." + kind for kind in KINDS})

    def test_real_ed25519_exact_eleven_key_fixture_frames(self):
        global VERIFIED_FIXTURE_COUNT
        world = World()
        fixture = json.loads((ROOT / "fixtures" / "ed25519-bilateral.json").read_bytes())
        count = 0
        for entry in fixture["frames"]:
            frame = entry["frame"]
            validate(frame)
            hive, actor = Federation.issuer(frame["payload"])
            cell = next(cell for cell, identity in world.hives.items() if identity == hive)
            registry = Registry(canonical(fixture["registries"][cell]),
                                next(anchor for anchor in world.anchors if anchor.hive_rappid == hive))
            self.assertEqual(set(frame), FRAME_KEYS)
            self.assertEqual(len(frame), 11)
            self.assertEqual(verify_frame(frame, registry.keys), actor)
            self.assertEqual(len(signature_header(frame["sig"])[2]), 64)
            count += 1
        self.assertEqual(count, len(fixture["frames"]))
        VERIFIED_FIXTURE_COUNT = count

    def test_all_eleven_keys_are_required(self):
        frame = World().request
        for key in FRAME_KEYS:
            altered = copy.deepcopy(frame)
            del altered[key]
            with self.subTest(key=key):
                self.reject("schema", validate, altered)

    def test_unknown_frame_and_nested_members_are_refused(self):
        frame = World().request
        changes = [
            lambda item: item.update(transport_identity="trusted-tls-user"),
            lambda item: item["payload"].update(plaintext="private prompt"),
            lambda item: item["payload"]["terms"]["resource"].update(private_path="/private/source"),
        ]
        for change in changes:
            altered = copy.deepcopy(frame)
            change(altered)
            self.reject("schema", validate, altered)

    def test_kind_payload_mismatch_is_closed(self):
        frame = copy.deepcopy(World().request)
        frame["kind"] = "federation.approval"
        self.reject("schema", validate, frame)

    def test_unsigned_frames_are_not_accepted(self):
        frame = copy.deepcopy(World().request)
        frame["sig"] = None
        self.reject("schema", validate, frame)

    def test_boolean_is_not_a_sequence_or_quota(self):
        frame = copy.deepcopy(World().request)
        frame["seq"] = True
        self.reject("schema", validate, frame)
        frame["seq"] = 1
        frame["payload"]["terms"]["units"] = True
        self.reject("schema", validate, frame)

    def test_maximum_parent_rappid_lengths_agree(self):
        identity = "rappid:@" + "a" * 39 + "/" + "b" * 100 + ":" + "0" * 64
        validate({"hive_rappid": identity, "world_id": "test", "actor_rappid": identity}, "party")
        too_long = identity.replace("a" * 39, "a" * 40)
        self.reject("schema", validate,
                    {"hive_rappid": too_long, "world_id": "test", "actor_rappid": too_long}, "party")
        double_hyphen = identity.replace("a" * 39, "a--b")
        self.reject("schema", validate,
                    {"hive_rappid": double_hyphen, "world_id": "test", "actor_rappid": double_hyphen}, "party")

    def test_duplicate_json_members_and_numeric_repairs_refused(self):
        self.reject("json-duplicate-key", loads, b'{"a":1,"a":2}')
        for raw in (b'{"a":1.0}', b'{"a":1e0}', b'{"a":NaN}', b'{"a":Infinity}'):
            self.reject("json-number", loads, raw)
        self.reject("json-integer", loads, b'{"a":9007199254740992}')
        self.reject("json-bom", loads, b'\xef\xbb\xbf{}')

    def test_nfc_surrogates_depth_and_size_are_bounded(self):
        self.reject("json-nfc", canonical, {"name": "e\u0301"})
        self.reject("json-surrogate", canonical, {"name": "\ud800"})
        value = {}
        for _ in range(65):
            value = {"nested": value}
        self.reject("json-depth", canonical, value)
        self.reject("json-size", canonical, {"text": "x" * (1 << 20)})

    def test_jcs_uses_utf16_order_not_codepoint_order(self):
        raw = canonical({"\ue000": 2, "\U0001f600": 1})
        self.assertEqual(raw, '{"😀":1,"\ue000":2}'.encode("utf-8"))
        self.assertEqual(H("rapp/1:particle", {"a": 1}),
                         hashlib.sha256(b'rapp/1:particle\n{"a":1}').hexdigest())

    def test_payload_tampering_is_cryptographically_refused(self):
        world, gate = self.fresh()
        altered = copy.deepcopy(world.request)
        altered["payload"]["terms"]["units"] = 6
        self.reject("payload-hash", verify_frame, altered, gate.registry(world.hives["source"]).keys)

    def test_wave_tampering_is_cryptographically_refused(self):
        world, gate = self.fresh()
        altered = copy.deepcopy(world.request)
        altered["frame_hash"] = "0" * 64
        self.reject("frame-hash", verify_frame, altered, gate.registry(world.hives["source"]).keys)

    def test_signature_byte_tampering_is_refused(self):
        world, gate = self.fresh()
        frame = copy.deepcopy(world.request)
        kid, protected, signature = signature_header(frame["sig"])
        corrupt = bytes([signature[0] ^ 1]) + signature[1:]
        frame["sig"] = protected + ".." + b64(corrupt)
        self.reject("signature-invalid", verify_frame, frame, gate.registry(world.hives["source"]).keys)

    def test_jws_algorithm_and_detachment_are_not_negotiated(self):
        world = World()
        kid, _, signature = signature_header(world.request["sig"])
        header = {"alg": "none", "b64": False, "crit": ["b64"], "kid": kid}
        self.reject("signature-header", signature_header, b64(canonical(header)) + ".." + b64(signature))
        self.reject("signature-format", signature_header, world.request["sig"].replace("..", ".e30."))

    def test_registered_owner_cannot_impersonate_another_actor_stream(self):
        world, gate = self.fresh(through="agreement-approval")
        frame = resign(world.request, "source-owner", world)
        self.reject("issuer-signature", gate.accept, canonical(frame))

    def test_transport_identity_cannot_replace_foreign_signature(self):
        world, gate = self.fresh(through="agreement-approval")
        frame = resign(world.request, "relay-carrier", world)
        self.reject("unknown-key", gate.accept, canonical(frame))
        registry = copy.deepcopy(world.registries["source"])
        registry["authenticated"] = True
        self.reject("schema", gate.install_registry, world.hives["source"], canonical(registry))

    def test_plaintext_is_not_a_sealed_egg(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        self.reject("egg-container", gate.open_request, world.request["frame_hash"], b'{"godd":"private"}',
                    world.key_service)
        self.assertEqual(world.key_calls, 0)
        self.assertEqual(gate.status(world.request["frame_hash"])["opened"], 0)

    def test_real_sealed_fixture_verifies_and_decrypts(self):
        world, gate = self.fresh()
        manifest, ciphertext = inspect_sealed(world.egg, world.resource["hash"],
                                              gate.registry(world.hives["source"]).keys)
        plaintext = decrypt_sealed(manifest, ciphertext, world.dek)
        self.assertIn(b"synthetic private input", plaintext)
        self.assertNotIn(plaintext, world.egg)
        self.assertEqual(len(ciphertext), len(plaintext) + 16)

    def test_sealed_tag_and_keyed_commitment_are_checked(self):
        world, gate = self.fresh()
        manifest, ciphertext = inspect_sealed(world.egg, world.resource["hash"],
                                              gate.registry(world.hives["source"]).keys)
        corrupt = bytes([ciphertext[0] ^ 1]) + ciphertext[1:]
        self.reject("egg-aead", decrypt_sealed, manifest, corrupt, world.dek)
        manifest["payload"]["plaintext_commitment"] = "0" * 64
        plaintext = b"x" * manifest["payload"]["plaintext_bytes"]
        from wire import unb64
        new_ciphertext = AESGCM(world.dek).encrypt(unb64(manifest["payload"]["nonce"]),
                                                  plaintext, canonical(sealed_aad(manifest)))
        self.reject("egg-commitment", decrypt_sealed, manifest, new_ciphertext, world.dek)

    def test_sealed_zip_trailing_bytes_and_wrong_address_refused(self):
        world, gate = self.fresh()
        keys = gate.registry(world.hives["source"]).keys
        self.reject("egg-noncanonical", inspect_sealed, world.egg + b"unbound", world.resource["hash"], keys)
        self.reject("egg-address", inspect_sealed, world.egg, "0" * 64, keys)

    def test_discovery_requires_full_frame_dogg_review(self):
        world, gate = self.fresh(through="request")
        discovery = world.discovery()
        self.reject("dogg-unapproved", gate.accept, canonical(discovery))
        gate.approve_dogg(H("rapp/1:particle", unsigned(discovery)),
                          discovery["payload"]["publication_evidence_hash"])
        self.assertEqual(gate.accept(canonical(discovery))["status"], "discovery-only")
        self.assertIsNone(gate.status(world.request["frame_hash"])["phase"])

    def test_discovery_private_fields_and_credential_urls_refused(self):
        world = World()
        discovery = world.discovery()
        for field in ("world_id", "members", "rooms", "plaintext", "private_head", "policy"):
            altered = copy.deepcopy(discovery)
            altered["payload"][field] = "private"
            self.reject("schema", validate, altered)
        altered = copy.deepcopy(discovery)
        altered["payload"]["pii_status"] = "present"
        self.reject("schema", validate, altered)
        for locator in ("https://user:password@example.invalid/chat", "https://example.invalid/chat?token=secret"):
            altered = copy.deepcopy(discovery)
            altered["payload"]["endpoint"] = locator
            self.reject("schema", validate, altered)

    def test_dogg_approval_cannot_be_reused_for_changed_public_bytes(self):
        world, gate = self.fresh(through="request")
        discovery = world.discovery()
        gate.approve_dogg(H("rapp/1:particle", unsigned(discovery)),
                          discovery["payload"]["publication_evidence_hash"])
        changed = self.modified(world, discovery, lambda item: item["payload"].update(
            endpoint="https://another.example.invalid/chat"))
        self.reject("dogg-unapproved", gate.accept, canonical(changed))


class StreamForks(Vectors):
    def policy_fork(self, world, gate, cell="source"):
        original = world.policies[cell]
        rival = self.modified(world, original,
                              lambda item: item["payload"].update(max_clock_uncertainty_ms=999))
        self.reject("stream-fork", gate.accept, canonical(rival))
        return original, rival

    def test_owner_policy_fork_retains_exact_evidence_and_refuses_both_branches(self):
        world, gate = self.fresh(through="request")
        history = gate.history()
        original, rival = self.policy_fork(world, gate)
        row = gate.db.execute("SELECT * FROM stream_faults").fetchone()
        self.assertEqual((row["stream"], row["sequence"], row["hive"], row["original"], row["evidence"], row["raw"]),
                         (original["stream_id"], original["seq"], world.hives["source"],
                          original["frame_hash"], rival["frame_hash"], canonical(rival)))
        self.assertEqual(gate.history(), history)
        self.assertEqual(gate.latest("policies", world.hives["source"]), original["frame_hash"])
        for frame in (original, rival):
            self.reject("stream-equivocation", gate.accept, canonical(frame))
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM stream_faults").fetchone()[0], 1)
        self.assertEqual(gate.accept(canonical(world.policies["destination"]))["status"], "duplicate")

    def test_original_successors_and_cross_stream_dependents_fail_across_restart(self):
        world, gate = self.fresh(through="request")
        original, _ = self.policy_fork(world, gate)
        payload = copy.deepcopy(original["payload"])
        payload.update(policy_seq=2, previous_policy=original["frame_hash"],
                       depends_on=sorted(payload["depends_on"] + [original["frame_hash"]]))
        successor = world.emit("next-policy", "policy", "source-owner", "source-governance", 30, payload)
        dependent = world.make_request(name="next-request", seconds=31, request_id=digest("post-fork"))
        for _ in range(2):
            for frame in (successor, dependent, world.request, world.agreement):
                self.reject("stream-equivocation", gate.accept, canonical(frame))
            gate = self.restart(world, gate)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_new_receipt_authorization_and_key_release_stop_after_policy_fork(self):
        for phase in ("validated", "executing"):
            with self.subTest(phase=phase):
                world, gate = self.fresh(through="request")
                phases = ("received", "validated") if phase == "validated" else (
                    "received", "validated", "accepted", "executing")
                world.advance(gate, phases)
                request_hash = world.request["frame_hash"]
                before = gate.status(request_hash)
                self.policy_fork(world, gate)
                receipt = world.receipt("accepted") if phase == "validated" else None
                for _ in range(2):
                    if receipt is not None:
                        self.reject("stream-equivocation", gate.accept, canonical(receipt))
                    else:
                        self.reject("authority-equivocation", gate.open_request, request_hash,
                                    world.egg, world.key_service)
                    self.assertEqual(gate.status(request_hash), before)
                    self.assertEqual(world.key_calls, 0)
                    gate = self.restart(world, gate)

    def test_registry_refresh_cannot_clear_owner_stream_fault(self):
        world, gate = self.fresh(through="request")
        original, _ = self.policy_fork(world, gate)
        world.registries["source"] = world.registry_document("source", sequence=8)
        gate.install_registry(world.hives["source"], canonical(world.registries["source"]))
        gate = self.restart(world, gate)
        self.reject("stream-equivocation", gate.accept, canonical(original))
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM stream_faults").fetchone()[0], 1)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 1)

    def test_inflight_outcome_can_be_recorded_without_reauthorizing_faulted_policy(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        request_hash = world.request["frame_hash"]
        self.assertIn(b"synthetic private input", gate.open_request(request_hash, world.egg, world.key_service))
        self.policy_fork(world, gate)
        gate = self.restart(world, gate)
        self.assertEqual(gate.accept(canonical(world.receipt("completed")))["status"], "business-completed")
        gate = self.restart(world, gate)
        self.assertEqual(gate.status(request_hash)["phase"], "completed")
        self.assertEqual(world.key_calls, 1)

    def test_forged_or_wrong_stream_owner_forks_cannot_latch(self):
        for variant in ("invalid-signature", "wrong-signer", "wrong-issuer", "owner-on-worker-stream"):
            with self.subTest(variant=variant):
                world, gate = self.fresh(through="request")
                rival = self.modified(world, world.policies["source"],
                                      lambda item: item["payload"].update(max_clock_uncertainty_ms=999))
                if variant == "invalid-signature":
                    _, _, signature = signature_header(rival["sig"])
                    header = rival["sig"].split(".")[0]
                    rival["sig"] = header + ".." + b64(bytes([signature[0] ^ 1]) + signature[1:])
                    code = "signature-invalid"
                elif variant == "wrong-signer":
                    rival["sig"] = world.signature(unsigned(rival), "source-requester")
                    code = "issuer-signature"
                elif variant == "wrong-issuer":
                    rival["payload"]["issuer"] = world.party("source", "source-requester")
                    rival = resign(rival, "source-requester", world)
                    code = "stream-issuer"
                else:
                    rival["stream_id"] = world.streams["source-work"]
                    rival = resign(rival, "source-owner", world)
                    code = "stream-issuer"
                self.reject(code, gate.accept, canonical(rival))
                gate = self.restart(world, gate)
                self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM stream_faults").fetchone()[0], 0)
                self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
                world.advance(gate)
                self.assertIn(b"synthetic private input", gate.open_request(
                    world.request["frame_hash"], world.egg, world.key_service))

    def test_nonowner_stream_fork_latches_only_its_stream_across_restart(self):
        for ingestion in ("direct", "staged"):
            with self.subTest(ingestion=ingestion):
                world, gate = self.fresh(through="request")
                original = world.request
                rival = self.modified(world, original,
                                      lambda item: item["payload"].update(request_id=digest("worker-rival")))
                dependent = world.make_request_approval()
                successor = world.make_request(name="worker-successor", seconds=30,
                                                request_id=digest("worker-successor"))
                rival_successor = world.emit("rival-successor", "request", "source-requester", "source-work", 31,
                                             copy.deepcopy(successor["payload"]), previous=rival)
                history = gate.history()
                if ingestion == "direct":
                    self.reject("stream-fork", gate.accept, canonical(rival))
                else:
                    gate.stage(canonical(rival))
                    result = gate.drain()
                    self.assertEqual(result["quarantined"],
                                     [{"frame_hash": rival["frame_hash"], "refusal": "stream-fork"}])
                for _ in range(2):
                    row = gate.db.execute("SELECT * FROM stream_faults").fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual((row["stream"], row["sequence"], row["original"], row["raw"]),
                                     (original["stream_id"], original["seq"], original["frame_hash"], canonical(rival)))
                    self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
                    for frame in (original, rival, successor, rival_successor, dependent):
                        self.reject("stream-equivocation", gate.accept, canonical(frame))
                    self.assertEqual(gate.accept(canonical(world.agreement))["status"], "duplicate")
                    self.assertEqual(gate.accept(canonical(world.policies["destination"]))["status"], "duplicate")
                    self.assertEqual(gate.history(), history)
                    gate = self.restart(world, gate)

    def test_nonowner_request_or_receipt_fork_blocks_pending_key_release(self):
        for subject in ("request", "receipt"):
            with self.subTest(subject=subject):
                world, gate = self.fresh(through="request")
                world.advance(gate)
                request_hash = world.request["frame_hash"]
                before = gate.status(request_hash)
                original = world.request if subject == "request" else world.receipts[-1]
                rival = self.modified(world, original, lambda item: item.update(utc=stamp(21)))
                self.reject("stream-fork", gate.accept, canonical(rival))
                for _ in range(2):
                    self.reject("stream-equivocation", gate.open_request, request_hash, world.egg, world.key_service)
                    self.assertEqual(gate.status(request_hash), before)
                    self.assertEqual(world.key_calls, 0)
                    self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
                    gate = self.restart(world, gate)

    def test_nonowner_fork_does_not_suspend_unaffected_prefix_authorization(self):
        world, gate = self.fresh(through="request")
        original = world.request
        later = world.make_request(name="later-request", seconds=30, request_id=digest("later-request"))
        gate.accept(canonical(later))
        rival = self.modified(world, later, lambda item: item.update(utc=stamp(31)))
        self.reject("stream-fork", gate.accept, canonical(rival))
        gate = self.restart(world, gate)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM stream_faults").fetchone()[0], 1)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
        world.request = original
        world.advance(gate)
        self.assertIn(b"synthetic private input", gate.open_request(
            original["frame_hash"], world.egg, world.key_service))
        self.assertEqual(world.key_calls, 1)
        self.reject("stream-equivocation", gate.accept, canonical(later))

    def test_nonowner_fork_proof_survives_revocation_and_index_recovery(self):
        for recovery in ("retained-index", "rebuilt-index", "removed-key"):
            with self.subTest(recovery=recovery):
                world, gate = self.fresh(through="request")
                original = world.request
                rival = self.modified(world, original, lambda item: item.update(utc=stamp(21)))
                self.reject("stream-fork", gate.accept, canonical(rival))
                if recovery == "rebuilt-index":
                    gate.db.execute("DELETE FROM stream_faults")
                registry = world.registry_document("source", sequence=8)
                actor = world.ids["source-requester"]
                tombstone = {"type": "tombstone", "rappid": actor, "revoked_utc": stamp(40)}
                tombstone["sig"] = world.signature(tombstone, "source-owner")
                registry["entries"].append(tombstone)
                if recovery == "removed-key":
                    registry["entries"] = [entry for entry in registry["entries"]
                                           if not (entry["type"] == "spki" and entry["rappid"] == actor)]
                registry["sig"] = world.signature(unsigned(registry), "source-owner")
                world.registries["source"] = registry
                gate.install_registry(world.hives["source"], canonical(registry))
                gate = self.restart(world, gate)
                row = gate.db.execute("SELECT original, evidence FROM stream_faults").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(tuple(row), (original["frame_hash"], rival["frame_hash"]))
                self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
                code = "unknown-key" if recovery == "removed-key" else "stream-equivocation"
                for frame in (original, rival):
                    self.reject(code, gate.accept, canonical(frame))
                self.assertEqual(gate.accept(canonical(world.policies["destination"]))["status"], "duplicate")

    def test_staged_owner_fork_and_later_batch_survive_restart(self):
        world, gate = self.fresh(through="request")
        original = world.policies["source"]
        rival = self.modified(world, original, lambda item: item["payload"].update(max_clock_uncertainty_ms=999))
        gate.stage(canonical(rival))
        gate = self.restart(world, gate)
        self.assertEqual(gate.drain()["quarantined"],
                         [{"frame_hash": rival["frame_hash"], "refusal": "stream-fork"}])
        gate = self.restart(world, gate)
        successor = world.make_request(name="staged-successor", seconds=30, request_id=digest("staged-successor"))
        for frame in (original, rival, successor):
            gate.stage(canonical(frame))
        result = gate.drain()
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["pending"], 0)
        self.assertEqual({entry["refusal"] for entry in result["quarantined"]}, {"stream-equivocation"})

    def test_earlier_fork_moves_frontier_back_without_losing_prior_evidence(self):
        world, gate = self.fresh(through="request")
        rival_grant = self.modified(world, world.grant, lambda item: item["payload"].update(max_total_units=19))
        self.reject("stream-fork", gate.accept, canonical(rival_grant))
        original, rival_policy = self.policy_fork(world, gate)
        gate = self.restart(world, gate)
        rows = list(gate.db.execute("SELECT sequence, evidence FROM stream_faults ORDER BY sequence"))
        self.assertEqual([tuple(row) for row in rows],
                         [(original["seq"], rival_policy["frame_hash"]),
                          (world.grant["seq"], rival_grant["frame_hash"])])
        self.reject("stream-equivocation", gate.accept, canonical(world.frames["source-peer"]))
        self.assertEqual(gate.accept(canonical(world.frames["source-governance-genesis"]))["status"], "duplicate")

    def test_committed_fault_is_visible_to_an_already_open_receiver_connection(self):
        world, gate = self.fresh(through="request")
        other = world.gate(self.paths[-1])
        self.gates.append(other)
        original, rival = self.policy_fork(world, gate)
        self.reject("stream-equivocation", other.accept, canonical(original))
        self.assertEqual(other.db.execute("SELECT raw FROM quarantine WHERE hash=?",
                                          (rival["frame_hash"],)).fetchone()[0], canonical(rival))
        self.assertEqual(other.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 1)

    def test_retained_fork_evidence_rebuilds_a_missing_stream_fault_index(self):
        world, gate = self.fresh(through="request")
        original, _ = self.policy_fork(world, gate)
        gate.db.execute("DELETE FROM stream_faults")
        gate = self.restart(world, gate)
        self.reject("stream-equivocation", gate.accept, canonical(original))
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM stream_faults").fetchone()[0], 1)

    def test_corrupt_fork_proof_requires_recovery_quarantine(self):
        world, gate = self.fresh(through="request")
        self.policy_fork(world, gate)
        gate.db.execute("UPDATE stream_faults SET raw=?", (b"{}",))
        path = self.paths[-1]
        gate.close()
        self.gates.remove(gate)
        self.reject("recovery-quarantine", Federation, path, local_hive=world.hives["destination"],
                    anchors=world.anchors, clock=Clock(stamp(20), stamp(20)))


class Authority(Vectors):
    def test_registered_memory_genesis_cannot_be_owned_by_a_different_principal(self):
        world, gate = self.fresh(through="request")
        world.streams["wrong-owner"] = world.ids["source-owner"] + ":wrong-owner"
        world.genesis("wrong-owner", "source-requester", "source", "actor")
        gate.install_registry(world.hives["source"], canonical(world.registry_document("source", sequence=8)))
        self.reject("stream-key-binding", gate.accept, canonical(world.frames["wrong-owner-genesis"]))

    def test_signed_checkpoint_does_not_verify_absent_mother_history(self):
        world, gate = self.fresh(through="request")
        self.assertEqual(world.cps["source"]["payload"]["hive_head_assurance"], "owner-attested-not-locally-verified")
        self.reject("dependency-missing", gate.frame, world.mothers["source"]["frame_hash"])
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint,
                                lambda item: item["payload"].update(hive_head_assurance="fully-verified"))
        self.reject("schema", validate, changed)

    def test_signed_private_registry_cannot_be_redacted_and_keep_its_signature(self):
        world, gate = self.fresh()
        registry = copy.deepcopy(world.registries["source"])
        registry["entries"] = [entry for entry in registry["entries"]
                               if not (entry["type"] == "spki" and entry["rappid"] == world.ids["source-artifact"])]
        self.reject("signature-invalid", gate.install_registry, world.hives["source"], canonical(registry))
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)

    def test_registry_rejects_invalid_spki_even_for_unused_keys(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        entry = next(item for item in registry["entries"]
                     if item["type"] == "spki" and item["rappid"] == world.ids["source-artifact"])
        invalid = b"not-a-DER-public-key"
        entry["rappid"] = keyed_rappid("cell-a", "invalid-key", invalid)
        entry["spki_der_b64"] = base64.b64encode(invalid).decode("ascii")
        self.reject("key-invalid", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))

    def test_owner_head_equivocation_durably_suspends_new_authorization(self):
        world, gate = self.fresh(through="request")
        world.advance(gate, ("received", "validated"))
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint, lambda item: item["payload"]["hive_head"].update(frame_hash="0" * 64))
        self.reject("competing-sovereign-heads", gate.accept, canonical(changed))
        receipt = world.receipt("accepted")
        self.reject("authority-equivocation", gate.accept, canonical(receipt))
        gate = self.restart(world, gate)
        self.reject("authority-equivocation", gate.accept, canonical(receipt))
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)

    def test_signed_registry_equivocation_suspends_effects_not_only_second_document(self):
        world, gate = self.fresh(through="request")
        registry = copy.deepcopy(world.registries["source"])
        registry["canonical_source"] = "https://conflicting.example.invalid/registry"
        self.reject("registry-equivocation", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))
        world.advance(gate, ("received", "validated"))
        self.reject("authority-equivocation", gate.accept, canonical(world.receipt("accepted")))

    def test_nonowner_cannot_manufacture_an_authority_fault_latch(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint,
                                lambda item: item["payload"].update(issuer=world.party("source", "source-requester")),
                                signer="source-requester")
        self.reject("owner-required", gate.accept, canonical(changed))
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM authority_faults").fetchone()[0], 0)
        world.advance(gate)
        self.assertIn(b"synthetic private input", gate.open_request(world.request["frame_hash"], world.egg, world.key_service))

    def test_registry_rollback_and_same_sequence_equivocation(self):
        world, gate = self.fresh()
        self.reject("registry-rollback", gate.install_registry, world.hives["source"],
                    canonical(world.registry_document("source", sequence=6)))
        changed = copy.deepcopy(world.registries["source"])
        changed["canonical_source"] = "https://alternate.example.invalid/registry"
        self.reject("registry-equivocation", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, changed))

    def test_registry_wrong_out_of_band_owner_signature(self):
        world, gate = self.fresh()
        registry = copy.deepcopy(world.registries["source"])
        registry["sig"] = world.signature(unsigned(registry), "destination-owner")
        self.reject("signer", gate.install_registry, world.hives["source"], canonical(registry))

    def test_registry_key_tail_substitution(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        entry = next(item for item in registry["entries"]
                     if item["type"] == "spki" and item["rappid"] == world.ids["source-requester"])
        entry["spki_der_b64"] = base64.b64encode(world.spki["relay-carrier"]).decode("ascii")
        self.reject("registry-key-binding", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))

    def test_registry_cannot_replace_known_genesis(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        next(item for item in registry["entries"] if item["type"] == "genesis")["frame_hash"] = "0" * 64
        self.reject("registry-genesis-substitution", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))

    def test_registry_duplicate_genesis_and_unsupported_reanchor_refused(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        item = copy.deepcopy(next(item for item in registry["entries"] if item["type"] == "genesis"))
        item["frame_hash"] = "0" * 64
        registry["entries"].append(item)
        self.reject("registry-competing-genesis", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))
        registry = world.registry_document("source", sequence=8)
        registry["entries"].append({"type": "re-anchor", "transport_owner": "trusted"})
        self.reject("schema", gate.install_registry, world.hives["source"], self.registry_signed(world, registry))

    def test_registry_allows_other_registered_profiles_without_authorizing_them(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        registry["entries"] += [
            {"type": "protocol", "name": "rapp-hive/1", "spec_repo": "example/hive",
             "spec_path": "protocols/rapp-hive/1/SPEC.md", "spec_hash": "1" * 64, "deprecated": False},
            {"type": "kind", "kind": "hive.declaration", "family": "body", "deprecated": False},
        ]
        self.assertEqual(gate.install_registry(world.hives["source"], self.registry_signed(world, registry))["registry_seq"], 8)
        self.reject("schema", validate, world.mothers["source"])

    def test_registry_requires_exact_spec_hash_and_memory_kind_binding(self):
        world, gate = self.fresh()
        registry = world.registry_document("source", sequence=8)
        next(item for item in registry["entries"] if item["type"] == "protocol")["spec_hash"] = "0" * 64
        self.reject("registry-profile-hash", gate.install_registry, world.hives["source"],
                    self.registry_signed(world, registry))
        registry = world.registry_document("source", sequence=8)
        next(item for item in registry["entries"] if item["type"] == "kind")["family"] = "swarm"
        self.reject("registry-kinds", gate.install_registry, world.hives["source"], self.registry_signed(world, registry))

    def test_stale_registry_checkpoint_cannot_authorize_execution(self):
        world, gate = self.fresh(through="request")
        gate.install_registry(world.hives["source"], canonical(world.registry_document("source", sequence=8)))
        world.advance(gate, ("received", "validated"))
        receipt = world.receipt("accepted", seconds=11)
        self.reject("registry-stale", gate.accept, canonical(receipt))
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)

    def test_signed_tombstone_is_sticky_and_backdating_does_not_restore_key(self):
        world, gate = self.fresh(through="request")
        registry = world.registry_document("source", sequence=8)
        tombstone = {"type": "tombstone", "rappid": world.ids["source-requester"], "revoked_utc": stamp(10)}
        tombstone["sig"] = world.signature(tombstone, "source-owner")
        registry["entries"].append(tombstone)
        gate.install_registry(world.hives["source"], self.registry_signed(world, registry))
        self.assertEqual(gate.accept(canonical(world.request))["status"], "duplicate")
        replay = world.emit("backdated", "request", "source-requester", "source-work", 7,
                            copy.deepcopy(world.request["payload"]))
        self.reject("actor-inactive", gate.accept, canonical(replay))
        self.reject("registry-revocation-rollback", gate.install_registry, world.hives["source"],
                    canonical(world.registry_document("source", sequence=9)))

    def test_competing_sovereign_heads_are_refused(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint, lambda item: item["payload"]["hive_head"].update(frame_hash="0" * 64))
        self.reject("competing-sovereign-heads", gate.accept, canonical(changed))

    def test_signed_authority_stream_forks_are_not_last_writer_wins(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        gate.accept(canonical(checkpoint))
        rival = self.modified(world, checkpoint, lambda item: item["payload"].update(challenge=digest("rival")))
        self.reject("sovereign-fork", gate.accept, canonical(rival))
        self.assertEqual(gate.latest("authority", world.hives["source"]), checkpoint["frame_hash"])

    def test_foreign_hive_cannot_be_local_head_or_dimension(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint,
                                lambda item: item["payload"]["hive_head"].update(stream_id=world.hives["destination"]))
        self.reject("foreign-dimension", gate.accept, canonical(changed))

    def test_missing_mother_head_successors_are_refused(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint, lambda item: item["payload"]["hive_head"].update(
            seq=2, prev=world.mothers["source"]["payload_hash"], frame_hash=digest("unproved-head")))
        self.reject("hive-head-lineage", gate.accept, canonical(changed))

    def test_authority_checkpoint_rollback_refused(self):
        world, gate = self.fresh(through="request")
        checkpoint = world.checkpoint("source", seconds=21)
        changed = self.modified(world, checkpoint, lambda item: item["payload"].update(previous_checkpoint=None))
        self.reject("authority-rollback", gate.accept, canonical(changed))

    def test_second_registered_authority_stream_is_refused(self):
        world, gate = self.fresh(through="request")
        stream = world.ids["source-owner"] + ":impostor-authority"
        world.streams["source-impostor"] = stream
        world.genesis("source-impostor", "source-owner", "source", "authority")
        gate.install_registry(world.hives["source"], canonical(world.registry_document("source", sequence=8)))
        self.reject("competing-authorities", gate.accept, canonical(world.frames["source-impostor-genesis"]))

    def test_checkpoint_must_include_known_control_frontier(self):
        world, gate = self.fresh(through="request")
        control = world.control()
        gate.accept(canonical(control))
        checkpoint = world.checkpoint("source", seconds=31)
        self.reject("control-frontier", gate.accept, canonical(checkpoint))

    def test_owner_control_cannot_be_forged_by_registered_worker(self):
        world, gate = self.fresh(through="request")
        payload = copy.deepcopy(world.control()["payload"])
        payload["issuer"] = world.party("source", "source-requester")
        frame = world.emit("worker-revocation", "control", "source-requester", "source-work", 31, payload)
        self.reject("owner-required", gate.accept, canonical(frame))

    def test_store_cannot_be_reopened_as_different_receiver(self):
        world, gate = self.fresh(through="request")
        path = self.paths[-1]
        with self.assertRaises(Refusal) as raised:
            Federation(path, local_hive=world.hives["source"], anchors=world.anchors, clock=Clock(stamp(20), stamp(20)))
        self.assertEqual(raised.exception.code, "store-configuration-substitution")


class ConsentAndScope(Vectors):
    def test_offline_receipt_cannot_claim_globally_fresh_online_assurance(self):
        world, gate = self.fresh(through="request")
        world.advance(gate, ("received", "validated"))
        receipt = world.receipt("accepted")
        changed = self.modified(world, receipt, lambda item: item["payload"].update(assurance="online-confirmed"))
        self.reject("receipt-assurance", gate.accept, canonical(changed))
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM usage").fetchone()[0], 0)

    def test_receipt_cannot_invent_tighter_clock_bounds_than_the_trusted_host(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(20), stamp(20, 500)))
        world.advance(gate, ("received", "validated"))
        receipt = world.receipt("accepted")
        changed = self.modified(world, receipt,
                                lambda item: item["payload"]["clock_basis"].update(upper_utc=stamp(20)))
        self.reject("receipt-clock-basis", gate.accept, canonical(changed))

    def test_human_ai_and_service_have_identical_rights_and_gates(self):
        for species in ("human", "ai", "service"):
            with self.subTest(actor=species):
                world, gate = self.fresh(through="request", recipient=species)
                world.advance(gate)
                plaintext = gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
                result = gate.accept(canonical(world.receipt("completed")))
                self.assertEqual(result["status"], "business-completed")
                self.assertIn(b"synthetic private input", plaintext)
                self.assertEqual(world.key_calls, 1)

    def test_unilateral_peer_consent_does_not_form_bilateral_agreement(self):
        world, gate = self.fresh(through="grant")
        def change(frame):
            old = frame["payload"]["destination_peer"]
            frame["payload"]["destination_peer"] = frame["payload"]["source_peer"]
            frame["payload"]["depends_on"].remove(old)
        altered = self.modified(world, world.agreement, change)
        self.reject("peer-consent-bilateral", gate.accept, canonical(altered))

    def test_source_cannot_supply_destination_agreement_approval(self):
        world, gate = self.fresh(through="agreement")
        payload = {
            **world.common("approval", "source", "source-owner", [world.agreement["frame_hash"]]),
            "scope": "agreement", "target": world.agreement["frame_hash"],
            "commitment": world.agreement["payload"]["terms_hash"], "decision": "accept",
        }
        forged = world.emit("one-sided-approval", "approval", "source-owner", "source-governance", 6, payload)
        self.reject("approval-destination", gate.accept, canonical(forged))

    def test_rejected_agreement_cannot_authorize_request(self):
        world, gate = self.fresh(through="agreement")
        rejected = self.modified(world, world.agreement_approval, lambda item: item["payload"].update(decision="reject"))
        gate.accept(canonical(rejected))
        old = world.agreement_approval["frame_hash"]
        def change(frame):
            frame["payload"]["agreement_approval"] = rejected["frame_hash"]
            frame["payload"]["depends_on"] = sorted(rejected["frame_hash"] if value == old else value
                                                    for value in frame["payload"]["depends_on"])
        request = self.modified(world, world.request, change)
        self.reject("one-sided-agreement", gate.accept, canonical(request))

    def test_approval_must_commit_exact_terms_hash(self):
        world, gate = self.fresh(through="agreement")
        changed = self.modified(world, world.agreement_approval,
                                lambda item: item["payload"].update(commitment="0" * 64))
        self.reject("approval-commitment", gate.accept, canonical(changed))

    def test_competing_approval_does_not_replace_destination_decision(self):
        world, gate = self.fresh(through="agreement-approval")
        payload = copy.deepcopy(world.agreement_approval["payload"])
        payload["decision"] = "reject"
        frame = world.emit("competing-approval", "approval", "destination-human", "destination-human", 7, payload)
        self.reject("approval-conflict", gate.accept, canonical(frame))

    def test_grant_cannot_widen_source_policy(self):
        world, gate = self.fresh()
        self.before(world, gate, "grant")
        changed = self.modified(world, world.grant, lambda item: item["payload"].update(max_units=11))
        self.reject("grant-widened", gate.accept, canonical(changed))

    def test_grants_are_nondelegable_and_cannot_authorize_dogg_publication(self):
        world = World()
        for flag in ("delegation", "dogg_publication"):
            changed = copy.deepcopy(world.grant)
            changed["payload"][flag] = True
            self.reject("schema", validate, changed)

    def test_request_cannot_change_agreed_units_within_grant(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request, lambda item: item["payload"]["terms"].update(units=6))
        self.reject("request-terms-changed", gate.accept, canonical(changed))

    def test_request_cannot_change_sealed_resource(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request,
                                lambda item: item["payload"]["terms"]["resource"].update(hash=digest("other-resource")))
        self.reject("grant-resource", gate.accept, canonical(changed))

    def test_request_recipient_cannot_be_substituted(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request, lambda item: item["payload"]["terms"]["destination"].update(
            actor_rappid=world.ids["destination-service"]))
        self.reject("grant-recipient", gate.accept, canonical(changed))

    def test_request_world_cannot_be_substituted(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request, lambda item: item["payload"]["terms"]["destination"].update(
            world_id="source-world"))
        self.reject("wrong-world", gate.accept, canonical(changed))

    def test_request_to_other_receiver_hive_is_refused(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request, lambda item: item["payload"]["terms"].update(
            destination=world.party("relay", "relay-carrier")))
        self.reject("wrong-recipient-hive", gate.accept, canonical(changed))

    def test_grant_validity_cannot_be_widened(self):
        world, gate = self.fresh(through="grant")
        def change(frame):
            frame["payload"]["terms"]["not_after"] = stamp(LEASE + DAY)
            frame["payload"]["terms_hash"] = H("rapp/1:particle", frame["payload"]["terms"])
        changed = self.modified(world, world.agreement, change)
        self.reject("grant-window-widened", gate.accept, canonical(changed))

    def test_agreement_is_not_individual_destination_acceptance(self):
        world, gate = self.fresh(through="request")
        world.advance(gate, ("received", "validated"), approval=False)
        receipt = world.receipt("accepted", approval=False)
        self.reject("destination-acceptance-required", gate.accept, canonical(receipt))
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)
        self.assertEqual(world.key_calls, 0)

    def test_agreement_approval_cannot_be_used_as_request_approval(self):
        world, gate = self.fresh(through="request")
        world.advance(gate, ("received", "validated"), approval=False)
        receipt = world.receipt("accepted", approval=False)
        def change(frame):
            frame["payload"]["approval"] = world.agreement_approval["frame_hash"]
            frame["payload"]["depends_on"] = sorted(set(frame["payload"]["depends_on"] +
                                                        [world.agreement_approval["frame_hash"]]))
        altered = self.modified(world, receipt, change)
        self.reject("destination-acceptance-required", gate.accept, canonical(altered))

    def test_receipt_cannot_skip_business_phases(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.make_request_approval()))
        receipt = world.receipt("completed")
        self.reject("receipt-phase", gate.accept, canonical(receipt))

    def test_early_receipts_cannot_claim_charges_or_results(self):
        world, gate = self.fresh(through="request")
        receipt = world.receipt("received", units=1)
        self.reject("receipt-premature-result", gate.accept, canonical(receipt))

    def test_completed_receipt_requires_local_opening_and_bounded_units(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        completed = world.receipt("completed")
        self.reject("execution-not-observed", gate.accept, canonical(completed))
        gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        excessive = self.modified(world, completed, lambda item: item["payload"].update(units=6))
        self.reject("receipt-budget", gate.accept, canonical(excessive))
        self.assertEqual(gate.accept(canonical(completed))["status"], "business-completed")

    def test_terminal_receipt_survives_benign_registry_refresh(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        gate.install_registry(
            world.hives["destination"],
            canonical(world.registry_document("destination", sequence=8)),
        )
        completed = world.receipt("completed")
        self.assertEqual(gate.accept(canonical(completed))["status"], "business-completed")
        self.assertEqual(gate.status(world.request["frame_hash"])["phase"], "completed")

    def test_policy_successor_requires_current_policy_parent(self):
        world, gate = self.fresh()
        world.load(gate, through="source-policy")
        old = world.policies["source"]
        payload = copy.deepcopy(old["payload"])
        payload["policy_seq"] = 2
        next_policy = world.emit("policy-fork", "policy", "source-owner", "source-governance", 3,
                                payload, previous=old)
        self.reject("policy-rollback", gate.accept, canonical(next_policy))


class Durability(Vectors):
    def test_loss_of_consumption_receipts_or_execution_markers_requires_recovery_quarantine(self):
        mutations = (
            "DELETE FROM requests", "DELETE FROM usage", "DELETE FROM execution_attempts",
            "UPDATE requests SET opened=0, local_status='pending'",
            "UPDATE requests SET phase='validated', receipt=NULL",
        )
        for mutation in mutations:
            with self.subTest(loss=mutation):
                world, gate = self.fresh(through="request")
                world.advance(gate)
                gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
                path = self.paths[-1]
                gate.db.execute(mutation)
                gate.close()
                self.gates.remove(gate)
                self.reject("recovery-quarantine", Federation, path, local_hive=world.hives["destination"],
                            anchors=world.anchors, clock=Clock(stamp(20), stamp(20)))

    def test_ed25519_signing_material_cannot_substitute_for_artifact_decryption_material(self):
        for raw_public_key in (False, True):
            with self.subTest(raw_public_key=raw_public_key):
                world, gate = self.fresh(through="request")
                world.advance(gate)
                material = (world.private["destination-human"].public_key().public_bytes_raw()
                            if raw_public_key else world.spki["destination-human"])
                self.reject("egg-aead" if raw_public_key else "dek", gate.open_request,
                            world.request["frame_hash"], world.egg, lambda _: material)
                self.assertEqual(gate.status(world.request["frame_hash"])["local_status"], "in-doubt")

    def test_native_wrapped_release_json_cannot_bypass_the_missing_key_transport_adapter(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        release = {"schema": "rapp-sealed-key-release/1", "wrap_alg": "ECDH-ES+A256KW",
                   "recipient_rappid": world.ids["destination-human"], "wrapped_key_jwe": "unverified-network-value"}
        self.reject("dek", gate.open_request, world.request["frame_hash"], world.egg, lambda _: release)
        self.assertEqual(gate.status(world.request["frame_hash"])["opened"], 1)

    def test_complete_exchange_and_duplicate_survive_restart(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        completed = world.receipt("completed")
        gate.accept(canonical(completed))
        before = gate.status(world.request["frame_hash"])
        gate = self.restart(world, gate)
        self.assertEqual(gate.accept(canonical(world.request))["status"], "duplicate")
        self.assertEqual(gate.accept(canonical(completed))["status"], "duplicate")
        self.assertEqual(gate.status(world.request["frame_hash"]), before)
        self.reject("execution-not-authorized", gate.open_request, world.request["frame_hash"], world.egg, world.key_service)
        self.assertEqual(world.key_calls, 1)

    def test_changed_payload_replay_is_durably_rejected(self):
        world, gate = self.fresh(through="request")
        gate = self.restart(world, gate)
        payload = copy.deepcopy(world.request["payload"])
        payload["depends_on"] = sorted(set(payload["depends_on"] + [world.cps["relay"]["frame_hash"]]))
        changed = world.emit("changed-request-replay", "request", "source-requester", "source-work", 8, payload)
        count = len(gate.history())
        self.reject("request-id-payload-replay", gate.accept, canonical(changed))
        self.assertEqual(len(gate.history()), count)

    def test_same_payload_new_envelope_never_becomes_new_execution_root(self):
        world, gate = self.fresh(through="request")
        original = world.request
        new_envelope = world.emit("same-payload-new-envelope", "request", "source-requester", "source-work", 8,
                                  copy.deepcopy(original["payload"]))
        self.assertEqual(gate.accept(canonical(new_envelope))["status"], "duplicate-request")
        self.assertEqual(gate.status(original["frame_hash"])["frame_hash"], original["frame_hash"])
        self.reject("request-original-required", gate.status, new_envelope["frame_hash"])

    def test_two_receivers_share_one_serialized_release_reservation(self):
        world, first = self.fresh(through="request")
        world.advance(first)
        second = world.gate(self.paths[-1])
        self.gates.append(second)
        barrier = threading.Barrier(2)
        def run(gate):
            barrier.wait()
            try:
                return gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
            except Refusal as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(run, (first, second)))
        self.assertEqual(sum(type(value) is bytes for value in outcomes), 1)
        self.assertIn("execution-already-opened", outcomes)
        self.assertEqual(world.key_calls, 1)

    def test_key_service_failure_persists_in_doubt_without_retry(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        calls = []
        def unavailable(permit):
            calls.append(permit)
            raise RuntimeError("synthetic key service interruption")
        with self.assertRaises(RuntimeError):
            gate.open_request(world.request["frame_hash"], world.egg, unavailable)
        self.assertEqual(gate.status(world.request["frame_hash"])["local_status"], "in-doubt")
        gate = self.restart(world, gate)
        self.reject("execution-already-opened", gate.open_request, world.request["frame_hash"], world.egg, unavailable)
        self.assertEqual(len(calls), 1)
        self.assertEqual(gate.accept(canonical(world.receipt("failed")))["status"], "business-failed")

    def test_bad_dek_cannot_retry_or_claim_completion(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        self.reject("egg-aead", gate.open_request, world.request["frame_hash"], world.egg, lambda _: b"\0" * 32)
        self.reject("execution-already-opened", gate.open_request, world.request["frame_hash"], world.egg, world.key_service)
        self.reject("execution-not-observed", gate.accept, canonical(world.receipt("completed")))

    def test_in_memory_inspection_store_cannot_release_keys(self):
        world = World()
        gate = world.gate(":memory:")
        self.gates.append(gate)
        world.load(gate)
        world.advance(gate, ("received", "validated"))
        self.reject("durable-store-required", gate.accept, canonical(world.receipt("accepted")))
        self.reject("durable-store-required", gate.open_request, world.request["frame_hash"], world.egg, world.key_service)

    def next_request(self, world, gate, number, *, start):
        world.make_request(name="request-" + str(number), seconds=start, request_id=digest("quota/" + str(number)))
        gate.accept(canonical(world.request))
        world.request_approval, world.receipts = None, []
        world.advance(gate, ("received", "validated", "accepted"), start=start + 2)

    def test_grant_use_quota_is_durable_across_distinct_requests(self):
        world, gate = self.fresh(through="request", grant_uses=1)
        world.advance(gate, ("received", "validated", "accepted"))
        gate = self.restart(world, gate)
        self.reject("grant-budget-exhausted", self.next_request, world, gate, 2, start=30)
        usage = gate.db.execute("SELECT uses, units FROM usage").fetchone()
        self.assertEqual(tuple(usage), (1, 5))

    def test_grant_aggregate_units_cannot_be_double_spent(self):
        world, gate = self.fresh(through="request", grant_total=5)
        world.advance(gate, ("received", "validated", "accepted"))
        self.reject("grant-budget-exhausted", self.next_request, world, gate, 2, start=30)

    def test_destination_policy_can_narrow_grant_use_budget(self):
        world, gate = self.fresh(through="request", destination_uses=1)
        world.advance(gate, ("received", "validated", "accepted"))
        self.reject("grant-budget-exhausted", self.next_request, world, gate, 2, start=30)

    def test_destination_policy_can_narrow_total_units_budget(self):
        world, gate = self.fresh(through="request", destination_total=5)
        world.advance(gate, ("received", "validated", "accepted"))
        self.reject("grant-budget-exhausted", self.next_request, world, gate, 2, start=30)

    def test_rejection_does_not_silently_refund_grant_reservation(self):
        world, gate = self.fresh(through="request", grant_uses=1)
        world.advance(gate, ("received", "validated", "accepted"))
        gate.accept(canonical(world.receipt("rejected", approval=False)))
        self.reject("grant-budget-exhausted", self.next_request, world, gate, 2, start=30)

    def test_request_and_receipt_database_never_contains_dek_or_plaintext(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        plaintext = gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        raw = self.paths[-1].read_bytes()
        self.assertNotIn(world.dek, raw)
        self.assertNotIn(world.dek.hex().encode("ascii"), raw)
        self.assertNotIn(plaintext, raw)


class ModesControlsAndTransport(Vectors):
    def test_exact_expiry_is_exclusive_not_an_extra_authorization_instant(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(LEASE), stamp(LEASE)))
        world.advance(gate, ("received", "validated"))
        self.reject("expired", gate.accept, canonical(world.receipt("accepted")))

    def test_clock_upper_endpoint_at_expiry_is_uncertain_not_valid(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(LEASE, -1), stamp(LEASE)))
        world.advance(gate, ("received", "validated"))
        self.reject("clock-uncertain", gate.accept, canonical(world.receipt("accepted")))

    def test_offline_horizon_is_policy_configured_not_a_one_year_global_limit(self):
        world, gate = self.fresh(through="request", lease_seconds=730 * DAY)
        gate.observe_clock(Clock(stamp(400 * DAY), stamp(400 * DAY)))
        world.advance(gate)
        self.assertIn(b"synthetic private input", gate.open_request(world.request["frame_hash"], world.egg, world.key_service))

    def test_bundle_binds_exact_octets_in_addition_to_native_object_identity(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        changed = self.modified(world, bundle,
                                lambda item: item["payload"]["items"][0].update(octets_sha256=digest("wrong-representation")))
        gate.accept(canonical(changed))
        artifacts = {
            ("rapp/1:wave", world.request["frame_hash"]): canonical(world.request),
            ("rapp/1:egg-manifest", world.resource["hash"]): world.egg,
        }
        self.reject("bundle-octets", gate.verify_bundle_contents, changed["frame_hash"], artifacts)

    def confirmed(self, world, gate, *, both=True, issue=True, wrong_intent=False):
        world.heads[world.streams["source-work"]] = world.agreement
        intent = copy.deepcopy(world.terms)
        if wrong_intent:
            intent["units"] += 1
        nonce = digest("receiver-fresh-online-challenge")
        if issue:
            gate.issue_challenge(intent, nonce=nonce)
        source = world.checkpoint("source", seconds=20, challenge=nonce, name="source-online-checkpoint")
        destination = world.checkpoint("destination", seconds=20, challenge=nonce if both else None,
                                        name="destination-online-checkpoint")
        gate.accept(canonical(source))
        gate.accept(canonical(destination))
        gate.accept(canonical(world.make_request(seconds=21, challenge=nonce)))
        gate.observe_clock(Clock(stamp(30), stamp(30)))
        return nonce

    def test_online_mode_requires_both_request_bound_owner_confirmations(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate)
        world.advance(gate, start=24)
        plaintext = gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        self.assertIn(b"synthetic private input", plaintext)
        gate.accept(canonical(world.receipt("completed", seconds=28)))
        self.assertEqual(world.key_calls, 1)
    def test_missing_dependency_is_not_assumed_authorized(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request, lambda item: item["payload"]["depends_on"].append(digest("absent")))
        changed["payload"]["depends_on"].sort()
        changed = resign(changed, "source-requester", world)
        count = len(gate.history())
        self.reject("dependency-missing", gate.accept, canonical(changed))
        self.assertEqual(len(gate.history()), count)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)

    def test_undeclared_capability_dependency_is_refused_even_if_cached(self):
        world, gate = self.fresh(through="agreement-approval")
        changed = self.modified(world, world.request,
                                lambda item: item["payload"]["depends_on"].remove(world.grant["frame_hash"]))
        self.reject("dependency-undeclared", gate.accept, canonical(changed))

    def test_causal_readiness_is_separate_from_unchanged_rapp_utc_order(self):
        world, gate = self.fresh(through="grant")
        approval = self.modified(world, world.agreement_approval, lambda item: item.update(utc=stamp(4)))
        old_hash = world.agreement_approval["frame_hash"]
        def change(frame):
            frame["payload"]["agreement_approval"] = approval["frame_hash"]
            frame["payload"]["depends_on"] = sorted(
                approval["frame_hash"] if value == old_hash else value for value in frame["payload"]["depends_on"])
        request = self.modified(world, world.request, change)
        for frame in (request, approval, world.agreement):
            gate.stage(canonical(frame))
        result = gate.drain()
        self.assertEqual(result["pending"], 0)
        self.assertEqual(result["quarantined"], [])
        history = gate.history()
        addresses = [frame["frame_hash"] for frame in history]
        self.assertLess(addresses.index(approval["frame_hash"]), addresses.index(world.agreement["frame_hash"]))
        self.assertEqual(gate.frame(approval["frame_hash"]), approval)
        self.assertEqual(history, sorted(history, key=lambda frame: (frame["utc"], frame["frame_hash"])))

    def test_equal_utc_tie_break_is_frame_hash_not_arrival(self):
        world, gate = self.fresh(through="request")
        history = gate.history()
        roots = [frame for frame in history if frame["utc"] == stamp()]
        self.assertGreater(len(roots), 3)
        self.assertEqual([frame["frame_hash"] for frame in roots], sorted(frame["frame_hash"] for frame in roots))

    def test_staged_missing_context_survives_restart_without_business_effect(self):
        world, gate = self.fresh()
        result = gate.stage(canonical(world.request))
        self.assertEqual(result["status"], "staged-unaccepted")
        self.assertEqual(gate.drain()["pending"], 1)
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 0)
        gate = self.restart(world, gate)
        world.load(gate, through="agreement-approval")
        self.assertEqual(gate.drain()["pending"], 0)
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)

    def test_staged_duplicate_is_removed_without_an_infinite_drain(self):
        world, gate = self.fresh(through="request")
        gate.stage(canonical(world.request))
        result = gate.drain()
        self.assertEqual(result["pending"], 0)
        self.assertEqual(result["accepted"], [world.request["frame_hash"]])

    def test_invalid_candidate_is_quarantined_without_blocking_independent_valid_frame(self):
        world, gate = self.fresh(through="request")
        invalid_payload = copy.deepcopy(world.request["payload"])
        invalid_payload["depends_on"] = sorted(set(invalid_payload["depends_on"] + [world.cps["relay"]["frame_hash"]]))
        invalid = world.emit("bad-replay", "request", "source-requester", "source-work", 8, invalid_payload)
        valid = world.checkpoint("relay", seconds=21, name="independent-relay-checkpoint")
        gate.stage(canonical(invalid))
        gate.stage(canonical(valid))
        result = gate.drain()
        self.assertEqual(result["pending"], 0)
        self.assertIn(valid["frame_hash"], result["accepted"])
        self.assertEqual(result["quarantined"], [
            {"frame_hash": invalid["frame_hash"], "refusal": "request-id-payload-replay"}])
        self.assertEqual(gate.db.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0], 1)

    def test_bundle_manifest_and_inventory_are_not_business_acceptance(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        self.assertEqual(gate.accept(canonical(bundle))["status"], "bundle-manifest-only")
        artifacts = {
            ("rapp/1:wave", world.request["frame_hash"]): canonical(world.request),
            ("rapp/1:egg-manifest", world.resource["hash"]): world.egg,
        }
        self.assertEqual(gate.verify_bundle_contents(bundle["frame_hash"], artifacts),
                         {"status": "content-verified", "execution_authorized": False})
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)
        self.assertEqual(world.key_calls, 0)

    def test_bundle_wrong_destination_is_refused(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        altered = self.modified(world, bundle, lambda item: item["payload"]["destination"].update(
            actor_rappid=world.ids["destination-ai"]))
        self.reject("bundle-destination", gate.accept, canonical(altered))

    def test_bundle_requires_original_request_and_sealed_resource(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        altered = self.modified(world, bundle, lambda item: item["payload"].update(
            items=[value for value in item["payload"]["items"] if value["space"] == "rapp/1:wave"]))
        self.reject("bundle-essential", gate.accept, canonical(altered))

    def test_bundle_byte_substitution_is_refused(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        gate.accept(canonical(bundle))
        artifacts = {
            ("rapp/1:wave", world.request["frame_hash"]): canonical(world.request) + b"\n",
            ("rapp/1:egg-manifest", world.resource["hash"]): world.egg,
        }
        self.reject("bundle-bytes", gate.verify_bundle_contents, bundle["frame_hash"], artifacts)

    def test_bundle_missing_inventory_and_unrelated_records_are_refused(self):
        world, gate = self.fresh(through="request")
        bundle = world.bundle()
        gate.accept(canonical(bundle))
        self.reject("bundle-inventory", gate.verify_bundle_contents, bundle["frame_hash"], {})
        new_payload = copy.deepcopy(bundle["payload"])
        new_payload["bundle_id"] = digest("other-bundle")
        new_payload["items"].append({
            "space": "rapp/1:wave", "hash": world.cps["relay"]["frame_hash"],
            "bytes": len(canonical(world.cps["relay"])),
            "octets_sha256": hashlib.sha256(canonical(world.cps["relay"])).hexdigest(), "essential": False,
        })
        new_payload["items"].sort(key=lambda item: (item["space"], item["hash"]))
        unrelated = world.emit("unrelated-bundle", "bundle", "source-requester", "source-work", 18, new_payload)
        self.reject("bundle-unrelated-content", gate.accept, canonical(unrelated))

    def test_custody_and_content_observations_cannot_advance_business_phase(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.bundle()))
        self.assertEqual(gate.accept(canonical(world.custody()))["status"], "custody-only")
        self.assertEqual(gate.accept(canonical(world.observation()))["status"], "observation-only")
        self.assertIsNone(gate.status(world.request["frame_hash"])["phase"])
        self.assertEqual(world.key_calls, 0)

    def test_relay_cannot_substitute_its_own_signed_business_receipt(self):
        world, gate = self.fresh(through="request")
        receipt = world.receipt("received")
        payload = copy.deepcopy(receipt["payload"])
        payload["issuer"] = world.party("relay", "relay-carrier")
        payload["checkpoint"] = world.cps["relay"]["frame_hash"]
        payload["depends_on"] = sorted(set(payload["depends_on"] + [world.cps["relay"]["frame_hash"]]))
        relay_receipt = world.emit("relay-forgery", "receipt", "relay-carrier", "relay-carrier", 10, payload)
        self.reject("relay-not-authority", gate.accept, canonical(relay_receipt))

    def test_custody_hop_limits_are_not_advisory(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.bundle()))
        custody = world.custody()
        altered = self.modified(world, custody, lambda item: item["payload"].update(hop=5))
        self.reject("custody-hop-limit", gate.accept, canonical(altered))

    def test_custody_successor_requires_previous_named_custodian(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.bundle()))
        custody = world.custody()
        gate.accept(canonical(custody))
        payload = copy.deepcopy(custody["payload"])
        payload["previous_custody"] = custody["frame_hash"]
        payload["depends_on"] = sorted(set(payload["depends_on"] + [custody["frame_hash"]]))
        payload["status"] = "forwarded"
        payload["next_custodian"] = world.ids["source-owner"]
        forwarded = world.emit("forwarded", "custody", "relay-carrier", "relay-carrier", 18, payload)
        gate.accept(canonical(forwarded))
        payload["previous_custody"] = forwarded["frame_hash"]
        payload["depends_on"] = sorted(set(payload["depends_on"] + [forwarded["frame_hash"]]))
        payload["status"], payload["next_custodian"], payload["hop"] = "stored", None, 1
        wrong = world.emit("wrong-custodian", "custody", "relay-carrier", "relay-carrier", 19, payload)
        self.reject("custody-transition", gate.accept, canonical(wrong))

    def test_global_owner_head_and_database_fields_do_not_exist(self):
        world = World()
        for field in ("global_owner", "global_head", "global_database", "local_dimension"):
            frame = copy.deepcopy(world.request)
            frame["payload"][field] = "implicit-authority"
            self.reject("schema", validate, frame)
        frame = copy.deepcopy(world.request)
        frame["payload"]["hive_mind"] = "urn:rapp:another-hive-mind"
        self.reject("schema", validate, frame)

    def test_checked_in_full_lifecycle_replays_all_thirteen_kinds(self):
        world, gate = self.fresh()
        fixture = json.loads((ROOT / "fixtures" / "ed25519-bilateral.json").read_bytes())
        for entry in fixture["frames"]:
            frame = entry["frame"]
            if frame["kind"] == "federation.discovery":
                gate.approve_dogg(H("rapp/1:particle", unsigned(frame)),
                                  frame["payload"]["publication_evidence_hash"])
            gate.accept(canonical(frame))
            if entry["name"] == "receipt-executing":
                self.assertEqual(gate.open_request(world.request["frame_hash"], world.egg, world.key_service).decode(),
                                 fixture["expected_plaintext"])
        self.assertEqual(len(gate.history()), len(fixture["frames"]))
        self.assertEqual(gate.status(fixture["expected_request_hash"])["phase"], "completed")
        self.assertEqual({frame["payload"]["hive_mind"] for frame in gate.history()}, {MIND})


    def test_online_mode_refuses_one_sided_confirmation(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate, both=False)
        world.advance(gate, ("received", "validated"), start=24)
        self.reject("online-unconfirmed", gate.accept, canonical(world.receipt("accepted", seconds=26)))

    def test_signed_echo_is_not_freshness_without_local_challenge(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate, issue=False)
        world.advance(gate, ("received", "validated"), start=24)
        self.reject("online-unconfirmed", gate.accept, canonical(world.receipt("accepted", seconds=26)))

    def test_online_challenge_is_bound_to_exact_terms(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate, wrong_intent=True)
        world.advance(gate, ("received", "validated"), start=24)
        self.reject("online-unconfirmed", gate.accept, canonical(world.receipt("accepted", seconds=26)))

    def test_online_challenge_expiry_is_not_extended_by_delivery(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate)
        gate.observe_clock(Clock(stamp(90), stamp(90)))
        world.advance(gate, ("received", "validated"), start=24)
        self.reject("online-challenge-expired", gate.accept, canonical(world.receipt("accepted", seconds=26)))

    def test_online_challenge_is_durable_single_request_scoped(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        nonce = self.confirmed(world, gate)
        world.advance(gate, ("received", "validated", "accepted"), start=24)
        gate.accept(canonical(world.make_request(name="second-online", seconds=40,
                                                request_id=digest("second-online"), challenge=nonce)))
        world.request_approval, world.receipts = None, []
        gate.observe_clock(Clock(stamp(50), stamp(50)))
        world.advance(gate, ("received", "validated"), start=42)
        self.reject("challenge-replay", gate.accept, canonical(world.receipt("accepted", seconds=44)))

    def test_advancing_authority_invalidates_old_online_checkpoint_for_new_effect(self):
        world, gate = self.fresh(through="agreement-approval", mode="online-confirmed")
        self.confirmed(world, gate)
        world.advance(gate)
        checkpoint = world.checkpoint("source", seconds=31, name="source-new-head-observation")
        gate.accept(canonical(checkpoint))
        self.reject("online-checkpoint-stale", gate.open_request, world.request["frame_hash"], world.egg,
                    world.key_service)

    def test_months_long_offline_partition_with_explicit_lease_succeeds(self):
        world, gate = self.fresh(through="request", lease_seconds=240 * DAY)
        gate.observe_clock(Clock(stamp(180 * DAY), stamp(180 * DAY)))
        world.advance(gate)
        self.assertIn(b"synthetic private input",
                      gate.open_request(world.request["frame_hash"], world.egg, world.key_service))

    def test_offline_authority_horizon_can_be_shorter_than_artifact_expiry(self):
        world, gate = self.fresh(through="request", offline_horizon=30 * DAY)
        gate.observe_clock(Clock(stamp(45 * DAY), stamp(45 * DAY)))
        world.advance(gate, ("received", "validated"))
        self.reject("offline-authority-stale", gate.accept, canonical(world.receipt("accepted")))

    def test_offline_mode_requires_explicit_revocation_risk_acknowledgement(self):
        world, gate = self.fresh(through="grant")
        def change(frame):
            frame["payload"]["terms"]["offline_risk_ack"] = False
            frame["payload"]["terms_hash"] = H("rapp/1:particle", frame["payload"]["terms"])
        altered = self.modified(world, world.agreement, change)
        self.reject("offline-risk-unacknowledged", gate.accept, canonical(altered))

    def test_irreversible_offline_effects_are_refused_even_if_owner_policy_allows(self):
        world, gate = self.fresh(through="grant")
        def change(frame):
            frame["payload"]["terms"]["irreversible"] = True
            frame["payload"]["terms_hash"] = H("rapp/1:particle", frame["payload"]["terms"])
        altered = self.modified(world, world.agreement, change)
        self.reject("offline-irreversible", gate.accept, canonical(altered))

    def test_unknown_clock_allows_retention_but_not_execution(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(None, None))
        world.advance(gate, ("received", "validated"))
        self.reject("clock-uncertain", gate.accept, canonical(world.receipt("accepted")))
        self.assertEqual(gate.status(world.request["frame_hash"])["reserved"], 0)

    def test_clock_uncertainty_over_policy_limit_refuses_execution(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(20), stamp(22)))
        world.advance(gate, ("received", "validated"))
        self.reject("clock-uncertain", gate.accept, canonical(world.receipt("accepted")))

    def test_clock_interval_straddling_expiry_is_not_guessed_valid(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(LEASE, -500), stamp(LEASE, 500)))
        world.advance(gate, ("received", "validated"))
        self.reject("clock-uncertain", gate.accept, canonical(world.receipt("accepted")))

    def test_expired_partition_lease_does_not_authorize_reconnection(self):
        world, gate = self.fresh(through="request")
        gate.observe_clock(Clock(stamp(LEASE + DAY), stamp(LEASE + DAY)))
        world.advance(gate, ("received", "validated"))
        self.reject("expired", gate.accept, canonical(world.receipt("accepted")))

    def test_clock_rollback_below_durable_floor_is_refused(self):
        _, gate = self.fresh()
        self.reject("clock-rollback", gate.observe_clock, Clock(stamp(10), stamp(10)))

    def test_deferred_mode_never_reserves_or_executes(self):
        world, gate = self.fresh(through="request", mode="deferred")
        gate.observe_clock(Clock(None, None))
        world.advance(gate, ("received", "validated"))
        self.reject("deferred-no-execution", gate.accept, canonical(world.receipt("accepted")))
        status = gate.status(world.request["frame_hash"])
        self.assertEqual((status["reserved"], status["opened"]), (0, 0))

    def test_deferred_promotion_requires_new_id_terms_and_approvals(self):
        world, gate = self.fresh(through="request", mode="deferred")
        deferred = world.request
        world.mode = "offline-bounded"
        world.terms["mode"] = world.mode
        world.terms["offline_risk_ack"] = True
        gate.accept(canonical(world.make_agreement(name="live-agreement", seconds=30)))
        gate.accept(canonical(world.make_agreement_approval(name="live-agreement-approval", seconds=31)))
        live = world.make_request(name="live-request", seconds=32, request_id=digest("live-promotion"),
                                  supersedes=deferred["frame_hash"])
        gate.accept(canonical(live))
        world.request_approval, world.receipts = None, []
        world.advance(gate, start=34)
        gate.open_request(live["frame_hash"], world.egg, world.key_service)
        self.assertEqual(gate.status(deferred["frame_hash"])["reserved"], 0)
        self.assertEqual(gate.status(live["frame_hash"])["opened"], 1)

    def test_known_revocation_overrides_valid_offline_lease(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.control()))
        world.advance(gate, ("received", "validated"))
        self.reject("revoked", gate.accept, canonical(world.receipt("accepted")))
        self.assertEqual(world.key_calls, 0)

    def test_revocation_between_acceptance_and_release_blocks_new_release(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        gate.accept(canonical(world.control()))
        self.reject("revoked", gate.open_request, world.request["frame_hash"], world.egg, world.key_service)
        self.assertEqual(world.key_calls, 0)

    def test_either_peer_can_block_new_work(self):
        for cell, other in (("source", "destination"), ("destination", "source")):
            with self.subTest(blocker=cell):
                world, gate = self.fresh(through="request")
                gate.accept(canonical(world.control(cell=cell, action="block", target_kind="peer", peer=world.hives[other])))
                world.advance(gate, ("received", "validated"))
                self.reject("peer-blocked", gate.accept, canonical(world.receipt("accepted")))

    def test_foreign_owner_cannot_revoke_source_grant(self):
        world, gate = self.fresh(through="request")
        self.reject("revocation-authority", gate.accept, canonical(world.control(cell="destination")))

    def test_destination_owner_can_cancel_inbound_request(self):
        world, gate = self.fresh(through="request")
        gate.accept(canonical(world.control(cell="destination", action="cancel", target_kind="request")))
        world.advance(gate, ("received", "validated"))
        self.reject("revoked", gate.accept, canonical(world.receipt("accepted")))

    def test_revocation_does_not_recall_plaintext_or_erase_prior_business_history(self):
        world, gate = self.fresh(through="request")
        world.advance(gate)
        plaintext = gate.open_request(world.request["frame_hash"], world.egg, world.key_service)
        old_frames = {frame["frame_hash"] for frame in gate.history()}
        gate.accept(canonical(world.control()))
        completion = world.receipt("completed")
        self.assertEqual(gate.accept(canonical(completion))["status"], "business-completed")
        self.assertIn(b"synthetic private input", plaintext)
        self.assertTrue(old_frames <= {frame["frame_hash"] for frame in gate.history()})
        self.assertEqual(world.key_calls, 1)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tests", nargs="*", help="Optional unittest class or method selectors")
    parser.add_argument("--report", metavar="PATH", help="Write a JSON report inside this profile directory")
    parser.add_argument("--verbose", action="store_true", help="Print each test name")
    arguments = parser.parse_args()
    inputs = ["SPEC.md", "schema.json", "requirements.txt", "reference/README.md",
              "fixtures/ed25519-bilateral.json"]
    inputs += ["reference/" + source.name for source in sorted((ROOT / "reference").glob("*.py"))]
    initial_hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in inputs}
    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromNames(arguments.tests, sys.modules[__name__]) if arguments.tests
             else loader.loadTestsFromModule(sys.modules[__name__]))
    result = unittest.TextTestRunner(verbosity=2 if arguments.verbose else 1).run(suite)
    changed_inputs = [name for name, original in initial_hashes.items()
                      if not (ROOT / name).is_file()
                      or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != original]
    summary = {
        "profile": PROFILE, "conformance_class": CONFORMANCE_CLASS, "activation": "candidate-not-activated",
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "verified_fixture_frames": VERIFIED_FIXTURE_COUNT, "negative_checks": len(NEGATIVE_RESULTS),
        "selected_tests": arguments.tests or ["full-suite"],
        "input_tree_stable": not changed_inputs, "changed_inputs": changed_inputs,
    }
    print(json.dumps(summary, sort_keys=True))
    if changed_inputs:
        print("Conformance inputs changed during execution: " + ", ".join(changed_inputs), file=sys.stderr)
    if arguments.report:
        path = Path(arguments.report)
        require_relative = not path.is_absolute() and ".." not in path.parts
        if not require_relative:
            parser.error("--report must be a relative path inside the profile")
        path = ROOT / path
        report = {**summary, "negative_vectors": NEGATIVE_RESULTS,
                  "environment": {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                                  "cryptography": version("cryptography"), "jsonschema": version("jsonschema")},
                  "source_sha256": initial_hashes}
        encoded = (json.dumps(report, indent=2) + "\n").encode("utf-8")
        if not path.is_file() or path.read_bytes() != encoded:
            path.write_bytes(encoded)
    return 0 if result.wasSuccessful() and result.testsRun and not changed_inputs else 1


if __name__ == "__main__":
    raise SystemExit(run())
