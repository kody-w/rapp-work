"""Reproducible PUBLIC TEST KEYS and synthetic Ed25519/AES-GCM fixtures only."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from rapp_federation import CellAnchor, Clock, Federation
from schema_source import ACTIONS, KINDS, MIND, MODES, PROFILE
from wire import (
    H, Hb, b64, build_frame, canonical, keyed_rappid, pack_sealed, plaintext_commitment,
    require, sealed_aad, sign, spki_bytes, unsigned,
)


ROOT = Path(__file__).resolve().parents[1]
DAY = 86400
LEASE = 180 * DAY
PUBLIC_TEST_LABEL = "PUBLIC RAPP FEDERATION CONFORMANCE KEY; NEVER DEPLOY: "


def digest(label):
    return hashlib.sha256((PUBLIC_TEST_LABEL + label).encode("ascii")).hexdigest()


def stamp(seconds=0, milliseconds=0):
    value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=seconds, milliseconds=milliseconds)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def resign(frame, signer, world):
    frame = copy.deepcopy(frame)
    frame["payload_hash"] = H("rapp/1:particle", frame["payload"])
    frame["frame_hash"] = H("rapp/1:wave", {
        key: value for key, value in frame.items() if key not in {"frame_hash", "sig"}
    })
    frame["sig"] = world.signature(unsigned(frame), signer)
    return frame


class World:
    def __init__(self, *, mode="offline-bounded", recipient="human", build=True,
                 grant_uses=2, grant_total=20, destination_uses=2, destination_total=20,
                 units=5, offline_horizon=None, lease_seconds=LEASE):
        self.mode, self.recipient = mode, recipient
        self.grant_uses, self.grant_total = grant_uses, grant_total
        self.destination_uses, self.destination_total = destination_uses, destination_total
        self.units, self.lease_seconds = units, lease_seconds
        self.offline_horizon = lease_seconds if offline_horizon is None else offline_horizon
        self.receipt_clock = Clock(stamp(20), stamp(20))
        self.private, self.spki, self.ids, self.hives, self.streams, self.heads = {}, {}, {}, {}, {}, {}
        self.frames, self.order, self.cps, self.policies, self.genesi, self.mothers = {}, [], {}, {}, {}, {}
        self.key_calls = 0
        self.receipts, self.request_approval = [], None
        roles = {
            "source": ("owner", "requester", "artifact", "key-service"),
            "destination": ("owner", "human", "ai", "service"),
            "relay": ("owner", "carrier"),
        }
        for cell, actors in roles.items():
            owner_label = {"source": "cell-a", "destination": "cell-b", "relay": "cell-c"}[cell]
            for actor in actors:
                name = cell + "-" + actor
                private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(digest(name)))
                spki = spki_bytes(private.public_key())
                self.private[name], self.spki[name] = private, spki
                self.ids[name] = keyed_rappid(owner_label, actor, spki)
            owner = cell + "-owner"
            self.hives[cell] = keyed_rappid(owner_label, "hive", self.spki[owner])
            self.streams[cell + "-authority"] = self.ids[owner] + ":federation-authority"
            self.streams[cell + "-governance"] = self.ids[owner] + ":federation-governance"
            self.streams[cell + "-discovery"] = self.ids[owner] + ":federation-discovery"
        self.streams["source-work"] = self.ids["source-requester"] + ":federation-work"
        for actor in ("human", "ai", "service"):
            self.streams["destination-" + actor] = self.ids["destination-" + actor] + ":federation-inbox"
        self.streams["relay-carrier"] = self.ids["relay-carrier"] + ":federation-carrier"
        self.anchors = [CellAnchor(self.hives[cell], cell + "-world", self.ids[cell + "-owner"],
                                   self.spki[cell + "-owner"], self.streams[cell + "-authority"])
                        for cell in ("source", "destination", "relay")]
        for cell in ("source", "destination", "relay"):
            owner = cell + "-owner"
            hive = self.hives[cell]
            mother_payload = {
                "schema": "rapp-hive/1-declaration", "hive_rappid": hive, "world_id": cell + "-world",
                "created_utc": stamp(), "authority_channel_id": "local",
                "members": [{"rappid": self.ids[owner], "role": "owner", "area": "members/owner"}],
                "rooms": [{"id": "general", "area": "rooms/general", "members": [self.ids[owner]],
                           "access": "repository"}],
                "channels": [{"id": "local", "kind": "local", "role": "authority",
                              "locator": "fixture/hive", "writeback": True}],
                "policy": {"godd_sharing": "explicit", "default_godd_scope": "local-only",
                           "external_publication": "disabled", "conflict_mode": "explicit",
                           "default_transfer": "copy"},
            }
            mother = build_frame("hive.declaration", hive, stamp(), mother_payload)
            mother["sig"] = self.signature(unsigned(mother), owner)
            self.mothers[cell] = mother
            self.genesi[hive] = mother["frame_hash"]
            self.genesis(cell + "-authority", owner, cell, "authority")
            self.genesis(cell + "-governance", owner, cell, "actor")
            self.genesis(cell + "-discovery", owner, cell, "discovery")
        self.genesis("source-work", "source-requester", "source", "actor")
        for actor in ("human", "ai", "service"):
            self.genesis("destination-" + actor, "destination-" + actor, "destination", "actor")
        self.genesis("relay-carrier", "relay-carrier", "relay", "relay")
        self.registries = {cell: self.registry_document(cell) for cell in ("source", "destination", "relay")}
        self.egg, self.dek, self.resource = self.sealed()
        if build:
            self.build()

    def signature(self, value, actor):
        return sign(value, self.ids[actor], self.private[actor])

    def party(self, cell, actor=None):
        actor = actor or cell + "-owner"
        return {"hive_rappid": self.hives[cell], "world_id": cell + "-world", "actor_rappid": self.ids[actor]}

    def emit(self, name, kind, actor, stream, seconds, payload, *, previous="current"):
        stream_id = self.streams.get(stream, stream)
        if previous == "current":
            previous = self.heads.get(stream_id)
        frame = build_frame("federation." + kind, stream_id, stamp(seconds), payload, previous=previous)
        frame["sig"] = self.signature(unsigned(frame), actor)
        self.heads[stream_id] = frame
        self.frames[name] = frame
        self.order.append(name)
        return frame

    def genesis(self, stream, actor, cell, role):
        payload = {
            "schema": PROFILE + "-checkpoint", "hive_mind": MIND, "phase": "genesis",
            "hive_rappid": self.hives[cell], "actor_rappid": self.ids[actor],
            "stream_role": role, "depends_on": [],
        }
        frame = self.emit(stream + "-genesis", "checkpoint", actor, stream, 0, payload)
        self.genesi[frame["stream_id"]] = frame["frame_hash"]

    def registry_document(self, cell, sequence=7):
        owner = cell + "-owner"
        prefix = self.ids[owner].split("/", 1)[0] + "/"
        entries = [
            {"type": "estate_owner", "rappid": self.ids[owner]},
            {"type": "protocol", "name": PROFILE, "spec_repo": "example/rapp",
             "spec_path": "protocols/rapp-federation/1/SPEC.md",
             "spec_hash": hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(), "deprecated": False},
        ]
        entries += [{"type": "kind", "kind": "federation." + kind, "family": "memory", "deprecated": False}
                    for kind in KINDS]
        entries += [{"type": "spki", "rappid": identity, "spki_der_b64": base64.b64encode(self.spki[name]).decode("ascii"),
                     "deprecated": False} for name, identity in sorted(self.ids.items()) if name.startswith(cell + "-")]
        entries += [{"type": "genesis", "stream_id": stream, "frame_hash": address, "deprecated": False}
                    for stream, address in sorted(self.genesi.items()) if stream.startswith(prefix)]
        document = {"schema": "rapp/1-registry", "registry_seq": sequence,
                    "canonical_source": "https://" + cell + ".example.invalid/registry", "entries": entries}
        document["sig"] = self.signature(document, owner)
        return document

    def registry_hash(self, cell):
        return H("rapp/1:particle", unsigned(self.registries[cell]))

    def checkpoint(self, cell, *, seconds=1, challenge=None, controls=(), head=None, name=None):
        previous = self.cps.get(cell)
        name = name or cell + "-checkpoint"
        head = head or {key: self.mothers[cell][key] for key in
                        ("stream_id", "seq", "utc", "payload_hash", "frame_hash", "prev")}
        payload = {
            "schema": PROFILE + "-checkpoint", "hive_mind": MIND, "phase": "authority",
            "issuer": self.party(cell), "depends_on": sorted(set(
                ([previous["frame_hash"]] if previous else []) + list(controls))),
            "authority_seq": previous["payload"]["authority_seq"] + 1 if previous else 1,
            "previous_checkpoint": previous["frame_hash"] if previous else None,
            "registry_seq": self.registries[cell]["registry_seq"], "registry_hash": self.registry_hash(cell),
            "hive_head": head, "hive_head_assurance": "owner-attested-not-locally-verified",
            "issued_utc": stamp(seconds), "valid_until_utc": stamp(self.lease_seconds),
            "max_clock_uncertainty_ms": 1000,
            "offline_horizon_ms": min(self.lease_seconds - seconds, self.offline_horizon) * 1000,
            "controls": sorted(controls), "challenge": challenge,
        }
        frame = self.emit(name, "checkpoint", cell + "-owner", cell + "-authority", seconds, payload)
        self.cps[cell] = frame
        return frame

    def common(self, name, cell, actor, references=(), *, checkpoint=None):
        checkpoint = checkpoint or self.cps[cell]["frame_hash"]
        return {
            "schema": PROFILE + "-" + name, "hive_mind": MIND, "issuer": self.party(cell, actor),
            "checkpoint": checkpoint,
            "depends_on": sorted(set([checkpoint] + [value for value in references if value is not None])),
        }

    def build(self):
        for cell in ("source", "destination", "relay"):
            self.checkpoint(cell)
        for cell, peer in (("source", "destination"), ("destination", "source")):
            policy = {
                **self.common("policy", cell, cell + "-owner"),
                "policy_seq": 1, "previous_policy": None,
                "allowed_peers": [self.hives[peer]],
                "allowed_actors": sorted(identity for name, identity in self.ids.items()
                                          if name.startswith(cell + "-")
                                          and not name.endswith(("artifact", "key-service"))),
                "actions": sorted(ACTIONS), "modes": sorted(MODES),
                "max_units": min(10, self.destination_total) if cell == "destination" else 10,
                "max_total_units": self.destination_total if cell == "destination" else 20,
                "max_uses": self.destination_uses if cell == "destination" else 2,
                "max_offline_ms": self.lease_seconds * 1000,
                "max_clock_uncertainty_ms": 1000, "allow_irreversible": True,
                "offline_revocation": "lease-limited",
            }
            self.policies[cell] = self.emit(cell + "-policy", "policy", cell + "-owner",
                                            cell + "-governance", 2, policy)
            consent = {
                **self.common("peer", cell, cell + "-owner"),
                "peer": {"hive_rappid": self.hives[peer], "world_id": peer + "-world"}, "consent": "allow",
                "not_before": stamp(), "not_after": stamp(self.lease_seconds),
            }
            self.emit(cell + "-peer", "peer", cell + "-owner", cell + "-governance", 3, consent)
        destination_actor = "destination-" + self.recipient
        grant = {
            **self.common("grant", "source", "source-owner", [self.policies["source"]["frame_hash"]]),
            "grant_id": digest("grant/" + self.recipient), "recipient": self.party("destination", destination_actor),
            "resource": self.resource, "policy": self.policies["source"]["frame_hash"],
            "actions": sorted(ACTIONS), "modes": sorted(MODES),
            "not_before": stamp(), "not_after": stamp(self.lease_seconds),
            "max_units": min(10, self.grant_total), "max_total_units": self.grant_total,
            "max_uses": self.grant_uses, "max_offline_ms": self.lease_seconds * 1000,
            "offline_revocation": "lease-limited", "delegation": False, "dogg_publication": False,
        }
        self.grant = self.emit("grant", "grant", "source-owner", "source-governance", 4, grant)
        self.terms = {
            "source": self.party("source", "source-requester"),
            "destination": self.party("destination", destination_actor), "resource": self.resource,
            "grant": self.grant["frame_hash"], "source_policy": self.policies["source"]["frame_hash"],
            "destination_policy": self.policies["destination"]["frame_hash"],
            "action": "godd.exchange", "mode": self.mode, "units": self.units,
            "not_before": stamp(), "not_after": stamp(self.lease_seconds),
            "irreversible": False, "offline_risk_ack": self.mode == "offline-bounded",
        }
        self.make_agreement()
        self.make_agreement_approval()
        self.make_request()

    def make_agreement(self, *, name="agreement", seconds=5):
        payload = {
            **self.common("agreement", "source", "source-requester", [
                self.terms["grant"], self.terms["source_policy"], self.terms["destination_policy"],
                self.frames["source-peer"]["frame_hash"], self.frames["destination-peer"]["frame_hash"],
            ]),
            "terms": copy.deepcopy(self.terms), "terms_hash": H("rapp/1:particle", self.terms),
            "source_peer": self.frames["source-peer"]["frame_hash"],
            "destination_peer": self.frames["destination-peer"]["frame_hash"],
        }
        self.agreement = self.emit(name, "agreement", "source-requester", "source-work", seconds, payload)
        return self.agreement

    def make_agreement_approval(self, *, name="agreement-approval", seconds=6):
        actor = "destination-" + self.recipient
        payload = {
            **self.common("approval", "destination", actor, [self.agreement["frame_hash"]]),
            "scope": "agreement", "target": self.agreement["frame_hash"],
            "commitment": self.agreement["payload"]["terms_hash"], "decision": "accept",
        }
        self.agreement_approval = self.emit(name, "approval", actor, actor, seconds, payload)
        return self.agreement_approval

    def make_request(self, *, name="request", seconds=7, request_id=None, challenge=None, supersedes=None):
        payload = {
            **self.common("request", "source", "source-requester", [
                self.agreement["frame_hash"], self.agreement_approval["frame_hash"], self.terms["grant"],
                self.terms["source_policy"], self.terms["destination_policy"],
                self.cps["destination"]["frame_hash"], supersedes,
            ]),
            "request_id": request_id or digest("request/" + self.recipient + "/" + self.mode),
            "agreement": self.agreement["frame_hash"], "agreement_approval": self.agreement_approval["frame_hash"],
            "terms": copy.deepcopy(self.terms), "destination_checkpoint": self.cps["destination"]["frame_hash"],
            "challenge": challenge if self.mode == "online-confirmed" else None, "supersedes": supersedes,
        }
        if self.mode == "online-confirmed" and challenge is None:
            payload["challenge"] = digest("unconfirmed-placeholder")
        self.request = self.emit(name, "request", "source-requester", "source-work", seconds, payload)
        return self.request

    def make_request_approval(self, *, seconds=8):
        actor = "destination-" + self.recipient
        payload = {
            **self.common("approval", "destination", actor, [self.request["frame_hash"]]),
            "scope": "request", "target": self.request["frame_hash"],
            "commitment": self.request["payload_hash"], "decision": "accept",
        }
        self.request_approval = self.emit("request-approval", "approval", actor, actor, seconds, payload)
        return self.request_approval

    def receipt(self, phase, *, seconds=None, reason=None, units=None, approval=True, name=None):
        actor = "destination-" + self.recipient
        prior = self.receipts[-1]["frame_hash"] if self.receipts else None
        approval_hash = (self.request_approval["frame_hash"] if approval and self.request_approval
                         and phase in {"accepted", "executing", "completed", "failed"} else None)
        source_checkpoint = self.request["payload"]["checkpoint"]
        reason = reason or ("executor-failure" if phase == "failed" else "policy" if phase == "rejected" else "none")
        assurance = ("online-confirmed" if self.mode == "online-confirmed" else "offline-authorized"
                     ) if phase in {"accepted", "executing"} else (
            "indeterminate" if phase == "failed" else "known-revoked" if reason == "revoked"
            else "authority-unavailable" if reason in {"clock", "dependency"} else "historical-snapshot")
        payload = {
            **self.common("receipt", "destination", actor, [
                self.request["frame_hash"], prior, approval_hash, source_checkpoint,
            ], checkpoint=self.request["payload"]["destination_checkpoint"]),
            "request": self.request["frame_hash"], "request_id": self.request["payload"]["request_id"],
            "phase": phase, "prior": prior, "approval": approval_hash, "source_checkpoint": source_checkpoint,
            "result": None, "units": (self.terms["units"] if phase == "completed" else 0) if units is None else units,
            "reason": reason, "assurance": assurance,
            "clock_basis": {"lower_utc": self.receipt_clock.lower, "upper_utc": self.receipt_clock.upper},
        }
        seconds = 9 + len(self.receipts) if seconds is None else seconds
        frame = self.emit(name or "receipt-" + phase, "receipt", actor, actor, seconds, payload)
        self.receipts.append(frame)
        return frame

    def advance(self, gate, phases=("received", "validated", "accepted", "executing"), *, approval=True, start=9):
        self.receipt_clock = gate._clock
        if approval and self.request_approval is None:
            gate.accept(canonical(self.make_request_approval(seconds=start - 1)))
        for index, phase in enumerate(phases):
            gate.accept(canonical(self.receipt(phase, seconds=start + index, approval=approval)))

    def control(self, *, cell="source", action="revoke", target_kind="grant", target=None, peer=None, seconds=30):
        target = target or (self.grant["frame_hash"] if action == "revoke" else
                            self.request["frame_hash"] if action == "cancel" else None)
        controls = [frame for frame in self.frames.values()
                    if frame["kind"] == "federation.control" and frame["payload"]["issuer"]["hive_rappid"] == self.hives[cell]]
        payload = {
            **self.common("control", cell, cell + "-owner", [target]), "control_seq": len(controls) + 1,
            "action": action, "target_kind": target_kind, "target_hash": target,
            "peer_hive": peer, "reason": "owner-choice",
        }
        return self.emit(cell + "-control-" + str(len(controls) + 1), "control", cell + "-owner",
                         cell + "-governance", seconds, payload)

    def discovery(self):
        payload = {
            "schema": PROFILE + "-discovery", "hive_mind": MIND,
            "hive_rappid": self.hives["source"], "advertiser_rappid": self.ids["source-owner"],
            "capabilities": sorted(ACTIONS), "endpoint": "https://cell-a.example.invalid/chat",
            "expires_utc": stamp(300), "data_class": "dogg", "pii_status": "none",
            "publication_evidence_hash": digest("public-dogg-review"),
        }
        return self.emit("discovery", "discovery", "source-owner", "source-discovery", 10, payload)

    def bundle(self, *, seconds=15):
        request = self.request
        items = [
            {"space": "rapp/1:wave", "hash": request["frame_hash"], "bytes": len(canonical(request)),
             "octets_sha256": hashlib.sha256(canonical(request)).hexdigest(), "essential": True},
            {"space": "rapp/1:egg-manifest", "hash": self.resource["hash"], "bytes": len(self.egg),
             "octets_sha256": hashlib.sha256(self.egg).hexdigest(), "essential": True},
        ]
        payload = {
            **self.common("bundle", "source", "source-requester", [request["frame_hash"]]),
            "bundle_id": digest("bundle/" + self.recipient), "request": request["frame_hash"],
            "destination": self.terms["destination"], "items": sorted(items, key=lambda item: (item["space"], item["hash"])),
            "expires_utc": stamp(self.lease_seconds), "max_hops": 4,
        }
        return self.emit("bundle", "bundle", "source-requester", "source-work", seconds, payload)

    def custody(self):
        bundle = self.frames["bundle"]["frame_hash"]
        payload = {
            **self.common("custody", "relay", "relay-carrier", [bundle]), "bundle": bundle,
            "previous_custody": None, "hop": 0, "status": "stored", "next_custodian": None,
        }
        return self.emit("custody", "custody", "relay-carrier", "relay-carrier", 16, payload)

    def observation(self):
        bundle = self.frames["bundle"]["frame_hash"]
        payload = {
            **self.common("observation", "relay", "relay-carrier", [bundle]), "subject": bundle,
            "status": "content-verified", "missing": [], "clock_lower": stamp(20), "clock_upper": stamp(20),
        }
        return self.emit("observation", "observation", "relay-carrier", "relay-carrier", 17, payload)

    def sealed(self):
        plaintext = b'{"classification":"godd","fixture":"synthetic private input","version":1}'
        dek = bytes.fromhex(digest("PUBLIC TEST AES KEY"))
        nonce = bytes.fromhex(digest("PUBLIC TEST AES NONCE"))[:12]
        payload = {
            "schema": "rapp-sealed-artifact/1", "cipher": "A256GCM", "nonce": b64(nonce),
            "plaintext_commitment": plaintext_commitment(dek, plaintext), "plaintext_bytes": len(plaintext),
            "media_type": "application/json", "key_id": digest("public-test-key-id"),
            "key_service_rappid": self.ids["source-key-service"],
            "key_service_url": "https://keys.example.invalid/chat",
            "access": "scoped-key-release", "aad_hash": "0" * 64,
        }
        manifest = {
            "schema": "rapp/1-egg", "variant": "sealed", "rappid": self.ids["source-artifact"],
            "created_utc": stamp(), "contents": [], "payload": payload, "sig": None,
        }
        payload["aad_hash"] = H("rapp/1:sealed-aad", sealed_aad(manifest))
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext, canonical(sealed_aad(manifest)))
        manifest["contents"] = [{"path": "ciphertext.bin", "hash": Hb("rapp/1:egg", ciphertext)}]
        manifest["sig"] = self.signature(unsigned(manifest), "source-artifact")
        resource = {"space": "rapp/1:egg-manifest", "hash": H("rapp/1:egg-manifest", unsigned(manifest)),
                    "artifact_rappid": self.ids["source-artifact"], "key_service_rappid": self.ids["source-key-service"]}
        return pack_sealed(manifest, ciphertext), dek, resource

    def key_service(self, permit):
        require(permit.request_hash == self.request["frame_hash"] and permit.request_id == self.request["payload"]["request_id"]
                and permit.grant_hash == self.grant["frame_hash"] and permit.source_hive == self.hives["source"]
                and permit.destination_hive == self.hives["destination"]
                and permit.destination_world == "destination-world"
                and permit.recipient_rappid == self.ids["destination-" + self.recipient]
                and permit.artifact_hash == self.resource["hash"]
                and permit.key_service_rappid == self.ids["source-key-service"]
                and permit.action == self.terms["action"] and permit.units == self.terms["units"]
                and permit.not_after == self.terms["not_after"]
                and permit.source_checkpoint == self.request["payload"]["checkpoint"]
                and permit.destination_checkpoint == self.request["payload"]["destination_checkpoint"],
                "fixture-key-scope")
        self.key_calls += 1
        return self.dek

    def gate(self, database, *, clock=None):
        gate = Federation(database, local_hive=self.hives["destination"], anchors=self.anchors,
                          clock=clock or Clock(stamp(20), stamp(20)))
        for cell, registry in self.registries.items():
            gate.install_registry(self.hives[cell], canonical(registry))
        return gate

    def load(self, gate, *, through="request"):
        for name in self.order:
            frame = self.frames[name]
            if frame["kind"] == "federation.discovery":
                gate.approve_dogg(H("rapp/1:particle", unsigned(frame)), frame["payload"]["publication_evidence_hash"])
            gate.accept(canonical(frame))
            if name == through:
                return
        raise ValueError("unknown fixture stop: " + through)


def fixture_document():
    world = World()
    world.make_request_approval()
    for phase in ("received", "validated", "accepted", "executing", "completed"):
        world.receipt(phase)
    world.discovery()
    world.bundle()
    world.custody()
    world.observation()
    control = world.control()
    world.checkpoint("source", seconds=31, controls=[control["frame_hash"]], name="source-final-checkpoint")
    return {
        "schema": "rapp-federation/1-conformance-fixture",
        "warning": "All identities, signing seeds, AES keys, and business data are PUBLIC SYNTHETIC TEST VECTORS.",
        "anchors": [anchor.document() for anchor in world.anchors],
        "registries": world.registries, "mother_genesis_frames": world.mothers,
        "frames": [{"name": name, "frame": world.frames[name]} for name in world.order],
        "sealed_egg_b64": base64.b64encode(world.egg).decode("ascii"),
        "expected_request_hash": world.request["frame_hash"],
        "expected_resource_hash": world.resource["hash"],
        "expected_plaintext": '{"classification":"godd","fixture":"synthetic private input","version":1}',
    }


def fixture_bytes():
    return (json.dumps(fixture_document(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Regenerate the public fixture after an intentional SPEC change")
    args = parser.parse_args()
    path = ROOT / "fixtures" / "ed25519-bilateral.json"
    if args.write:
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(fixture_bytes())
        print("wrote", path.name)
    else:
        require(path.is_file() and path.read_bytes() == fixture_bytes(), "fixture-drift")
        print("Ed25519 fixture: exact reproducible match")
