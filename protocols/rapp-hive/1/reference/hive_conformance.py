#!/usr/bin/env python3
"""Controlled conformance vectors for rapp-hive/1."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import rapp as R
import rapp_hive as H
from rapp_profile import particle_hash


PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def rid(owner: str, slug: str, fill: str) -> str:
    return f"rappid:@{owner}/{slug}:{fill * 64}"


HIVE = rid("example", "private-hive", "1")
ALICE = rid("alice", "member", "2")
BOB = rid("bob", "member", "3")
CAROL = rid("carol", "member", "4")
DAVE = rid("dave", "member", "5")
ECHO = rid("example-ai", "member", "b")
ALICE_WORKSPACE = rid("alice", "workspace", "6")
BOB_WORKSPACE = rid("bob", "workspace", "7")
ARTIFACT = rid("alice", "shared-godd", "8")
DIMENSION_A = rid("alice", "hive-dimension", "9")
DIMENSION_B = rid("bob", "hive-dimension", "a")


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append(condition)
    suffix = f" - {detail}" if detail and not condition else ""
    print(f"  [{PASS if condition else FAIL}] {name}{suffix}")


def refused(name: str, action, contains: str) -> None:
    try:
        action()
    except ValueError as error:
        check(name, contains in str(error), str(error))
    else:
        check(name, False, "accepted a document that must be refused")


def declaration_fixture() -> dict:
    return {
        "schema": H.DECLARATION_SCHEMA,
        "hive_rappid": HIVE,
        "world_id": "example-world",
        "created_utc": "2026-09-11T17:00:00.000Z",
        "authority_channel_id": "github-main",
        "members": [
            {"rappid": ALICE, "role": "owner", "area": "members/alice"},
            {"rappid": BOB, "role": "member", "area": "members/bob"},
            {"rappid": CAROL, "role": "member", "area": "members/carol"},
            {"rappid": DAVE, "role": "viewer", "area": "members/dave"},
            {"rappid": ECHO, "role": "member", "area": "members/example-ai"},
        ],
        "rooms": [
            {
                "id": "general",
                "area": "rooms/general",
                "members": [ALICE, BOB, CAROL, DAVE, ECHO],
                "access": "repository",
            },
            {
                "id": "strategy",
                "area": "rooms/strategy",
                "members": [ALICE, BOB],
                "access": "sealed",
            },
        ],
        "channels": [
            {
                "id": "github-main",
                "kind": "github",
                "role": "authority",
                "locator": "git@example.invalid:example/private-hive.git",
                "writeback": True,
            },
            {
                "id": "lan-gateway",
                "kind": "lan",
                "role": "mirror",
                "locator": "https://hive.lan.invalid",
                "writeback": False,
            },
            {
                "id": "nas-mirror",
                "kind": "nas",
                "role": "backup",
                "locator": "smb://nas.invalid/private-hive",
                "writeback": False,
            },
            {
                "id": "sharepoint",
                "kind": "sharepoint",
                "role": "writable",
                "locator": "https://example.invalid/sites/private-hive",
                "writeback": True,
            },
        ],
        "policy": {
            "godd_sharing": "explicit",
            "default_godd_scope": "local-only",
            "external_publication": "disabled",
            "conflict_mode": "explicit",
            "default_transfer": "copy",
        },
    }


def slice_fixture() -> dict:
    return {
        "schema": H.SLICE_SCHEMA,
        "hive_rappid": HIVE,
        "source_workspace_rappid": ALICE_WORKSPACE,
        "producer_rappid": ALICE,
        "world_id": "example-world",
        "created_utc": "2026-09-11T17:01:00.000Z",
        "room_id": "strategy",
        "audience": [ALICE, BOB],
        "classification": {
            "estate": "godd",
            "scope": "hive-shared",
            "sensitivity": "confidential",
            "dogg_projection_allowed": False,
        },
        "content": {
            "sealed_egg_hash": digest("sealed GODD egg"),
            "artifact_rappid": ARTIFACT,
            "plaintext_schema": "example-godd/1",
            "plaintext_bytes": 4096,
            "record_count": 12,
        },
        "source_frames": [
            {
                "stream_id": ALICE_WORKSPACE,
                "seq": 7,
                "utc": "2026-09-11T16:58:00.000Z",
                "payload_hash": digest("source payload"),
                "frame_hash": digest("source frame"),
            }
        ],
        "mutation_keys": ["accounts/example", "strategy/priority"],
    }


def shared_object_fixture() -> dict:
    return {
        "schema": H.OBJECT_SCHEMA,
        "hive_rappid": HIVE,
        "object_rappid": rid("example-ai", "agent", "c"),
        "producer_rappid": ECHO,
        "world_id": "example-world",
        "created_utc": "2026-09-11T17:00:30.000Z",
        "room_id": "general",
        "audience": [ALICE, BOB, CAROL, DAVE, ECHO],
        "object": {
            "space": "rapp/1:egg-manifest",
            "hash": digest("AI-contributed agent egg"),
            "kind": "agent",
            "data_class": "neutral",
            "pii_status": "not-applicable",
            "pii_evidence_hash": None,
            "protection": "member-visible",
            "target_path": "members/example-ai/agents/collaboration-agent.egg",
        },
        "source_frames": [],
        "mutation_keys": ["members/example-ai/agents/collaboration-agent"],
    }


def assimilation_fixture(godd_slice: dict) -> dict:
    return {
        "schema": H.ASSIMILATION_SCHEMA,
        "hive_rappid": HIVE,
        "slice_payload_hash": particle_hash(godd_slice),
        "recipient_workspace_rappid": BOB_WORKSPACE,
        "recipient_rappid": BOB,
        "assimilated_utc": "2026-09-11T17:02:00.000Z",
        "target_namespace": "godd/hive/alice/strategy",
        "mode": "overlay",
        "precedence": 500,
        "resulting_layer_hash": digest("bob resulting GODD layer"),
    }


def candidate(
    dimension: str,
    stamp: str,
    frame_label: str,
    payload_label: str,
    mutation_keys: list[str],
    channels: list[str],
) -> dict:
    return {
        "dimension_rappid": dimension,
        "stream_id": dimension,
        "seq": 1,
        "utc": stamp,
        "payload_hash": digest(payload_label),
        "frame_hash": digest(frame_label),
        "mutation_keys": sorted(mutation_keys),
        "source_channel_ids": sorted(channels),
    }


def convergence_fixture() -> dict:
    candidates = sorted(
        [
            candidate(
                DIMENSION_A,
                "2026-09-11T17:03:00.000Z",
                "alice frame",
                "alice payload",
                ["members/alice/project-a"],
                ["github-main", "lan-gateway"],
            ),
            candidate(
                DIMENSION_B,
                "2026-09-11T17:04:00.000Z",
                "bob frame",
                "bob payload",
                ["members/bob/project-b"],
                ["sharepoint"],
            ),
        ],
        key=lambda value: (value["utc"], value["frame_hash"]),
    )
    return {
        "schema": H.CONVERGENCE_SCHEMA,
        "hive_rappid": HIVE,
        "created_utc": "2026-09-11T17:05:00.000Z",
        "base_head_frame_hash": digest("mother hive base head"),
        "base_convergence_payload_hash": None,
        "base_catalog_hash": digest("base catalog"),
        "candidates": candidates,
        "decisions": [
            {"frame_hash": value, "status": "accepted", "reason_code": "independent"}
            for value in sorted(candidate["frame_hash"] for candidate in candidates)
        ],
        "resolutions": [],
        "resulting_catalog_hash": digest("catalog after independent merge"),
        "status": "converged",
    }


def projection_fixture(convergence: dict) -> dict:
    return {
        "schema": H.PROJECTION_SCHEMA,
        "hive_rappid": HIVE,
        "convergence_payload_hash": particle_hash(convergence),
        "channel_id": "sharepoint",
        "projected_utc": "2026-09-11T17:06:00.000Z",
        "registry_seq": 8,
        "catalog_hash": convergence["resulting_catalog_hash"],
        "frame_head": digest("mother hive accepted head"),
        "artifact_manifest_hash": digest("complete artifact manifest"),
        "status": "current",
    }


def template_fixture(shared_object: dict) -> dict:
    return {
        "schema": H.TEMPLATE_SCHEMA,
        "source_hive_rappid": HIVE,
        "template_rappid": rid("example", "hive-template", "d"),
        "created_utc": "2026-09-11T17:06:30.000Z",
        "egg_hash": digest("PII-free Hive template egg"),
        "objects": [
            {
                "object_payload_hash": particle_hash(shared_object),
                "data_class": "neutral",
                "pii_status": "not-applicable",
            }
        ],
        "pii_evidence_hash": digest("template PII scan"),
    }


declaration = declaration_fixture()
godd_slice = slice_fixture()
shared_object = shared_object_fixture()
assimilation = assimilation_fixture(godd_slice)
convergence = convergence_fixture()
projection = projection_fixture(convergence)
template = template_fixture(shared_object)

check("H01 declaration conforms", H.validate_declaration(declaration) == particle_hash(declaration))
check(
    "H02 an AI member contributes through the same RAPPID contract",
    H.validate_shared_object(shared_object, declaration) == particle_hash(shared_object),
)
unsafe_dogg = copy.deepcopy(shared_object)
unsafe_dogg["object"]["data_class"] = "dogg"
unsafe_dogg["object"]["pii_status"] = "unknown"
refused(
    "H03 DOGG with unproven PII status is refused",
    lambda: H.validate_shared_object(unsafe_dogg, declaration),
    "DOGG must be PII-free",
)
check("H04 sealed GODD slice conforms", H.validate_godd_slice(godd_slice, declaration) == particle_hash(godd_slice))
check(
    "H05 authorized recipient can assimilate a Hive GODD layer",
    H.validate_assimilation(assimilation, declaration, godd_slice) == particle_hash(assimilation),
)
check(
    "H06 convergence proposal shape conforms without authenticating decisions",
    H.validate_convergence(convergence, declaration) == particle_hash(convergence),
)
check(
    "H07 projection shape binds the advertised convergence payload",
    H.validate_projection(projection, declaration, convergence) == particle_hash(projection),
)
check(
    "H08 a Hive template egg contains only PII-free DOGG or neutral objects",
    H.validate_template(template) == particle_hash(template),
)

wrong_room = copy.deepcopy(godd_slice)
wrong_room["audience"].append(CAROL)
refused(
    "H09 a repository collaborator outside the room cannot join the slice audience",
    lambda: H.validate_godd_slice(wrong_room, declaration),
    "outside the selected room",
)

public_default = copy.deepcopy(declaration)
public_default["policy"]["default_godd_scope"] = "hive-shared"
refused(
    "H10 GODD sharing cannot become implicit",
    lambda: H.validate_declaration(public_default),
    "must be local-only",
)

unknown_channel = copy.deepcopy(convergence)
unknown_channel["candidates"][0]["source_channel_ids"] = ["unknown"]
check(
    "H11 unknown-channel summaries remain shape-only pending authenticated quarantine",
    H.validate_convergence(unknown_channel, declaration) == particle_hash(unknown_channel),
)

wrong_order = copy.deepcopy(convergence)
wrong_order["candidates"].reverse()
refused(
    "H12 Dream Catcher order is utc then frame_hash",
    lambda: H.validate_convergence(wrong_order, declaration),
    "utc then frame_hash order",
)

conflict_candidates = sorted(
    [
        candidate(
            DIMENSION_A,
            "2026-09-11T17:07:00.000Z",
            "conflict alice",
            "conflict alice payload",
            ["rooms/strategy/decision"],
            ["github-main"],
        ),
        candidate(
            DIMENSION_B,
            "2026-09-11T17:07:00.000Z",
            "conflict bob",
            "conflict bob payload",
            ["rooms/strategy/decision"],
            ["sharepoint"],
        ),
    ],
    key=lambda value: (value["utc"], value["frame_hash"]),
)
silent_winner = {
    "schema": H.CONVERGENCE_SCHEMA,
    "hive_rappid": HIVE,
    "created_utc": "2026-09-11T17:08:00.000Z",
    "base_head_frame_hash": convergence["base_head_frame_hash"],
    "base_convergence_payload_hash": particle_hash(convergence),
    "base_catalog_hash": convergence["base_catalog_hash"],
    "candidates": conflict_candidates,
    "decisions": [
        {
            "frame_hash": frame_hash,
            "status": "accepted" if index == 0 else "superseded",
            "reason_code": "last-write",
        }
        for index, frame_hash in enumerate(sorted(value["frame_hash"] for value in conflict_candidates))
    ],
    "resolutions": [],
    "resulting_catalog_hash": digest("invalid silent winner"),
    "status": "converged",
}
check(
    "H13 payload validation makes no authenticated conflict-resolution claim",
    H.validate_convergence(silent_winner, declaration) == particle_hash(silent_winner),
)

explicit_conflict = copy.deepcopy(silent_winner)
explicit_conflict["decisions"] = [
    {"frame_hash": value, "status": "conflict", "reason_code": "mutation-conflict"}
    for value in sorted(candidate["frame_hash"] for candidate in conflict_candidates)
]
explicit_conflict["status"] = "partial"
explicit_conflict["resulting_catalog_hash"] = digest("partial catalog")
check(
    "H14 partial proposal shape records both dimensions",
    H.validate_convergence(explicit_conflict, declaration) == particle_hash(explicit_conflict),
)

resolver = candidate(
    DIMENSION_A,
    "2026-09-11T17:09:00.000Z",
    "signed reconciliation frame",
    "signed reconciliation payload",
    ["rooms/strategy/decision"],
    ["github-main"],
)
resolved_candidates = sorted(conflict_candidates + [resolver], key=lambda value: (value["utc"], value["frame_hash"]))
resolved = copy.deepcopy(explicit_conflict)
resolved["created_utc"] = "2026-09-11T17:10:00.000Z"
resolved["candidates"] = resolved_candidates
resolved["decisions"] = [
    {
        "frame_hash": value,
        "status": "accepted" if value == resolver["frame_hash"] else "superseded",
        "reason_code": "signed-reconciliation" if value == resolver["frame_hash"] else "reconciled",
    }
    for value in sorted(candidate["frame_hash"] for candidate in resolved_candidates)
]
resolved["resolutions"] = [
    {
        "mutation_key": "rooms/strategy/decision",
        "frame_hashes": sorted(candidate["frame_hash"] for candidate in conflict_candidates),
        "resolution_frame_hash": resolver["frame_hash"],
    }
]
resolved["resulting_catalog_hash"] = digest("resolved catalog")
resolved["status"] = "converged"
check(
    "H15 reconciliation references exclude the resolver from its parent set",
    H.validate_convergence(resolved, declaration) == particle_hash(resolved),
)

wrong_projection = copy.deepcopy(projection)
wrong_projection["catalog_hash"] = digest("stale catalog")
refused(
    "H16 a current channel cannot report divergent bytes",
    lambda: H.validate_projection(wrong_projection, declaration, convergence),
    "must match convergence catalog",
)

frame = R.build_frame(
    "hive.declaration",
    HIVE,
    0,
    "2026-09-11T17:00:00.000Z",
    declaration,
    prev=None,
    sig=None,
)
unsafe_template = copy.deepcopy(template)
unsafe_template["objects"][0]["data_class"] = "dogg"
unsafe_template["objects"][0]["pii_status"] = "not-applicable"
refused(
    "H17 a template refuses DOGG without explicit PII-free status",
    lambda: H.validate_template(unsafe_template),
    "DOGG must be PII-free",
)

refused(
    "H18 the eleven-key envelope alone is not authenticated authority",
    lambda: H.authorize_hive_frame(
        frame, expected_schema=H.DECLARATION_SCHEMA, head=None, stream_id=HIVE,
        registered_kinds={"hive.declaration"}, signature_verifier=None, authorization_verifier=None,
    ),
    "signature verifier is required",
)

profile_root = Path(__file__).resolve().parents[1]
repository_root = Path(__file__).resolve().parents[4]
index = json.loads((repository_root / "protocols" / "index.json").read_text(encoding="utf-8"))
profile = next(value for value in index["profiles"] if value["name"] == "rapp-hive/1")
check(
    "H19 estate protocol index pins the exact specification and schema",
    hashlib.sha256((profile_root / "SPEC.md").read_bytes()).hexdigest() == profile["spec_sha256"]
    and hashlib.sha256((profile_root / "schema.json").read_bytes()).hexdigest() == profile["schema_sha256"]
    and profile["parent"] == "rapp/1",
)

from authenticated_conformance import run

authenticated = run()
check("H20 real Ed25519 acceptance and schema/Python scalar vectors", authenticated.wasSuccessful())

print("-" * 72)
passed = sum(results)
print(f"{len(results)} Hive checks | {passed} PASS | {len(results) - passed} FAIL")
raise SystemExit(0 if passed == len(results) else 1)
