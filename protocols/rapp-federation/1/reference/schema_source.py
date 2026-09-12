"""The auditable source of ../schema.json. Run with --check to detect drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


PROFILE = "rapp-federation/1"
CONFORMANCE_CLASS = "interval-local-receiver"
MIND = "urn:rapp:hive-mind"
KINDS = (
    "discovery", "peer", "policy", "grant", "agreement", "approval", "request",
    "receipt", "control", "checkpoint", "bundle", "custody", "observation",
)
ACTIONS = ["godd.exchange", "task.execute", "proposal.submit"]
MODES = ["online-confirmed", "offline-bounded", "deferred"]
MAX_UINT = (1 << 53) - 1


def obj(properties):
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def const(value):
    return {"const": value}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def integer(low=0, high=MAX_UINT):
    return {"type": "integer", "minimum": low, "maximum": high}


def array(items, low=0, high=64):
    return {"type": "array", "items": items, "minItems": low, "maxItems": high, "uniqueItems": True}


def nullable(schema):
    return {"oneOf": [schema, {"type": "null"}]}


def tagged(name, fields):
    return obj({"schema": const(PROFILE + "-" + name), "hive_mind": const(MIND), **fields})


def private(name, fields):
    return tagged(name, {"issuer": ref("party"), "checkpoint": ref("hash"),
                         "depends_on": ref("dependencies"), **fields})


def build_schema():
    definitions = {
        "hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "rappid": {"type": "string", "maxLength": 213, "pattern":
                   "^rappid:@[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*:[0-9a-f]{64}$"},
        "memoryStream": {"type": "string", "maxLength": 278, "pattern":
                         "^rappid:@[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*:[0-9a-f]{64}:[a-z0-9]+(?:-[a-z0-9]+)*$"},
        "registeredStream": {"oneOf": [ref("rappid"), ref("memoryStream")]},
        "label": {"type": "string", "maxLength": 64, "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"},
        "utc": {"type": "string", "format": "date-time",
                "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z$"},
        "signature": {"type": "string", "maxLength": 1024,
                      "pattern": "^[A-Za-z0-9_-]+\\.\\.[A-Za-z0-9_-]{86}$"},
        "endpoint": {"type": "string", "format": "uri", "maxLength": 512,
                     "pattern": "^https://[^/?#@\\s]+(?:/[^?#@\\s]*)?/chat$"},
        "dependencies": array(ref("hash")),
        "party": obj({"hive_rappid": ref("rappid"), "world_id": ref("label"), "actor_rappid": ref("rappid")}),
        "cell": obj({"hive_rappid": ref("rappid"), "world_id": ref("label")}),
        "resource": obj({
            "space": const("rapp/1:egg-manifest"), "hash": ref("hash"),
            "artifact_rappid": ref("rappid"), "key_service_rappid": ref("rappid"),
        }),
        "hiveHead": obj({
            "stream_id": ref("rappid"), "seq": integer(), "utc": ref("utc"),
            "payload_hash": ref("hash"), "frame_hash": ref("hash"), "prev": nullable(ref("hash")),
        }),
        "actions": array(enum(*ACTIONS), 1, len(ACTIONS)),
        "modes": array(enum(*MODES), 1, len(MODES)),
        "horizon": integer(),
        "uncertainty": integer(),
        "units": integer(1, 1000000),
        "totalUnits": integer(1, 1000000000),
        "uses": integer(1, 1024),
        "clockBasis": {"oneOf": [
            obj({"lower_utc": ref("utc"), "upper_utc": ref("utc")}),
            obj({"lower_utc": const(None), "upper_utc": const(None)}),
        ]},
    }
    definitions["terms"] = obj({
        "source": ref("party"), "destination": ref("party"), "resource": ref("resource"),
        "grant": ref("hash"), "source_policy": ref("hash"), "destination_policy": ref("hash"),
        "action": enum(*ACTIONS), "mode": enum(*MODES), "units": ref("units"),
        "not_before": ref("utc"), "not_after": ref("utc"),
        "irreversible": {"type": "boolean"}, "offline_risk_ack": {"type": "boolean"},
    })
    definitions["discovery"] = tagged("discovery", {
        "hive_rappid": ref("rappid"), "advertiser_rappid": ref("rappid"),
        "capabilities": array(enum(*ACTIONS), 1, len(ACTIONS)),
        "endpoint": ref("endpoint"), "expires_utc": ref("utc"),
        "data_class": const("dogg"), "pii_status": const("none"),
        "publication_evidence_hash": ref("hash"),
    })
    definitions["peer"] = private("peer", {
        "peer": ref("cell"), "consent": const("allow"),
        "not_before": ref("utc"), "not_after": ref("utc"),
    })
    definitions["policy"] = private("policy", {
        "policy_seq": integer(1), "previous_policy": nullable(ref("hash")),
        "allowed_peers": array(ref("rappid"), 1),
        "allowed_actors": array(ref("rappid"), 1),
        "actions": ref("actions"), "modes": ref("modes"),
        "max_units": ref("units"), "max_total_units": ref("totalUnits"),
        "max_uses": ref("uses"), "max_offline_ms": ref("horizon"),
        "max_clock_uncertainty_ms": ref("uncertainty"),
        "allow_irreversible": {"type": "boolean"}, "offline_revocation": enum("deny", "lease-limited"),
    })
    definitions["grant"] = private("grant", {
        "grant_id": ref("hash"), "recipient": ref("party"), "resource": ref("resource"),
        "policy": ref("hash"), "actions": ref("actions"), "modes": ref("modes"),
        "not_before": ref("utc"), "not_after": ref("utc"),
        "max_units": ref("units"), "max_total_units": ref("totalUnits"),
        "max_uses": ref("uses"), "max_offline_ms": ref("horizon"),
        "offline_revocation": enum("deny", "lease-limited"),
        "delegation": const(False), "dogg_publication": const(False),
    })
    definitions["agreement"] = private("agreement", {
        "terms": ref("terms"), "terms_hash": ref("hash"),
        "source_peer": ref("hash"), "destination_peer": ref("hash"),
    })
    definitions["approval"] = private("approval", {
        "scope": enum("agreement", "request"), "target": ref("hash"),
        "commitment": ref("hash"), "decision": enum("accept", "reject"),
    })
    definitions["request"] = private("request", {
        "request_id": ref("hash"), "agreement": ref("hash"), "agreement_approval": ref("hash"),
        "terms": ref("terms"), "destination_checkpoint": ref("hash"),
        "challenge": nullable(ref("hash")), "supersedes": nullable(ref("hash")),
    })
    definitions["receipt"] = private("receipt", {
        "request": ref("hash"), "request_id": ref("hash"),
        "phase": enum("received", "validated", "accepted", "executing", "completed", "failed", "rejected"),
        "prior": nullable(ref("hash")), "approval": nullable(ref("hash")),
        "source_checkpoint": ref("hash"), "result": nullable(ref("resource")),
        "units": integer(0, 1000000),
        "reason": enum("none", "policy", "revoked", "expired", "conflict", "dependency", "clock",
                       "executor-failure", "duplicate"),
        "assurance": enum("historical-snapshot", "online-confirmed", "offline-authorized",
                          "authority-unavailable", "known-revoked", "indeterminate"),
        "clock_basis": ref("clockBasis"),
    })
    definitions["control"] = private("control", {
        "control_seq": integer(1), "action": enum("revoke", "block", "cancel"),
        "target_kind": enum("grant", "agreement", "peer", "request"),
        "target_hash": nullable(ref("hash")), "peer_hive": nullable(ref("rappid")),
        "reason": enum("owner-choice", "policy", "key-compromise", "abuse", "superseded"),
    })
    definitions["genesis"] = tagged("checkpoint", {
        "phase": const("genesis"), "hive_rappid": ref("rappid"), "actor_rappid": ref("rappid"),
        "stream_role": enum("authority", "actor", "discovery", "relay"),
        "depends_on": array(ref("hash"), 0, 0),
    })
    definitions["authorityCheckpoint"] = tagged("checkpoint", {
        "phase": const("authority"), "issuer": ref("party"), "depends_on": ref("dependencies"),
        "authority_seq": integer(1), "previous_checkpoint": nullable(ref("hash")),
        "registry_seq": integer(), "registry_hash": ref("hash"), "hive_head": ref("hiveHead"),
        "hive_head_assurance": const("owner-attested-not-locally-verified"),
        "issued_utc": ref("utc"), "valid_until_utc": ref("utc"),
        "max_clock_uncertainty_ms": ref("uncertainty"), "offline_horizon_ms": ref("horizon"),
        "controls": array(ref("hash")), "challenge": nullable(ref("hash")),
    })
    definitions["checkpoint"] = {"oneOf": [ref("genesis"), ref("authorityCheckpoint")]}
    definitions["bundleItem"] = obj({
        "space": enum("rapp/1:wave", "rapp/1:egg-manifest"), "hash": ref("hash"),
        "bytes": integer(1, 1 << 20), "octets_sha256": ref("hash"), "essential": {"type": "boolean"},
    })
    definitions["bundle"] = private("bundle", {
        "bundle_id": ref("hash"), "request": ref("hash"), "destination": ref("party"),
        "items": array(ref("bundleItem"), 1), "expires_utc": ref("utc"),
        "max_hops": integer(1, 32),
    })
    definitions["custody"] = private("custody", {
        "bundle": ref("hash"), "previous_custody": nullable(ref("hash")), "hop": integer(0, 32),
        "status": enum("stored", "forwarded", "refused", "expired"),
        "next_custodian": nullable(ref("rappid")),
    })
    definitions["observation"] = private("observation", {
        "subject": ref("hash"),
        "status": enum("transport-arrived", "content-verified", "pending-dependencies", "expired", "rejected"),
        "missing": array(ref("hash")),
        "clock_lower": nullable(ref("utc")), "clock_upper": nullable(ref("utc")),
    })
    definitions["payload"] = {"oneOf": [ref(name) for name in KINDS]}
    definitions["frame"] = obj({
        "spec": const("rapp/1"), "kind": enum(*("federation." + name for name in KINDS)),
        "stream_id": ref("memoryStream"), "seq": integer(), "utc": ref("utc"),
        "payload": ref("payload"), "payload_hash": ref("hash"), "frame_hash": ref("hash"),
        "prev": nullable(ref("hash")), "prev_wave": const(None), "sig": ref("signature"),
    })
    definitions["frame"]["allOf"] = [
        {"if": {"properties": {"kind": const("federation." + name)}},
         "then": {"properties": {"payload": ref(name)}}} for name in KINDS
    ]
    definitions["registryEntry"] = {"oneOf": [
        obj({"type": const("estate_owner"), "rappid": ref("rappid")}),
        obj({"type": const("protocol"),
             "name": {"type": "string", "minLength": 1, "maxLength": 128},
             "spec_repo": {"type": "string", "minLength": 1, "maxLength": 200},
             "spec_path": {"type": "string", "minLength": 1, "maxLength": 256},
             "spec_hash": ref("hash"), "deprecated": {"type": "boolean"}}),
        obj({"type": const("kind"),
             "kind": {"type": "string", "maxLength": 129,
                      "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*\\.[a-z0-9]+(?:-[a-z0-9]+)*$"},
             "family": enum("body", "memory", "swarm"), "deprecated": {"type": "boolean"}}),
        obj({"type": const("spki"), "rappid": ref("rappid"),
             "spki_der_b64": {"type": "string", "minLength": 1, "maxLength": 256},
             "deprecated": {"type": "boolean"}}),
        obj({"type": const("genesis"), "stream_id": ref("registeredStream"),
             "frame_hash": ref("hash"), "deprecated": const(False)}),
        obj({"type": const("tombstone"), "rappid": ref("rappid"),
             "revoked_utc": ref("utc"), "sig": ref("signature")}),
    ]}
    definitions["registry"] = obj({
        "schema": const("rapp/1-registry"), "registry_seq": integer(),
        "canonical_source": {"type": "string", "format": "uri", "maxLength": 512,
                             "pattern": "^https://[^\\s?#@]+$"},
        "entries": array(ref("registryEntry"), 1, 256), "sig": ref("signature"),
    })
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:rapp:profile:rapp-federation:1",
        "title": "RAPP Federation / Work 1 — bounded signed RAPP/1 frames",
        "$ref": "#/$defs/frame", "$defs": definitions,
    }


def schema_bytes():
    return (json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / "schema.json"
    if arguments.check:
        if not path.is_file() or path.read_bytes() != schema_bytes():
            raise SystemExit("schema.json differs from schema_source.py")
        print("schema.json: exact generated match")
    else:
        path.write_bytes(schema_bytes())
        print("wrote schema.json")
