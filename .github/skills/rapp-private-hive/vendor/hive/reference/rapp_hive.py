#!/usr/bin/env python3
"""Structural validators for rapp-hive/1; authentication is in hive_acceptance."""

from __future__ import annotations

import argparse
import json
import sys

import rapp as R
from rapp_profile import (
    authoritative_frame_payload,
    boolean,
    bounded_int,
    canonical_object,
    exact_keys,
    hex64,
    label,
    load_json,
    particle_hash,
    relative_path,
    require,
    text,
    unique_strings,
    utc,
)


DECLARATION_SCHEMA = "rapp-hive/1-declaration"
OBJECT_SCHEMA = "rapp-hive/1-object"
SLICE_SCHEMA = "rapp-hive/1-godd-slice"
ASSIMILATION_SCHEMA = "rapp-hive/1-assimilation"
CONVERGENCE_SCHEMA = "rapp-hive/1-convergence"
RECONCILIATION_SCHEMA = "rapp-hive/1-reconciliation"
PROJECTION_SCHEMA = "rapp-hive/1-projection"
TEMPLATE_SCHEMA = "rapp-hive/1-template"
CATALOG_SCHEMA = "rapp-hive/1-catalog"
MANIFEST_SCHEMA = "rapp-hive/1-artifact-manifest"

KIND_SCHEMAS = {
    "hive.declaration": DECLARATION_SCHEMA,
    "hive.object": OBJECT_SCHEMA,
    "hive.godd-slice": SLICE_SCHEMA,
    "hive.assimilation": ASSIMILATION_SCHEMA,
    "hive.convergence": CONVERGENCE_SCHEMA,
    "hive.reconciliation": RECONCILIATION_SCHEMA,
    "hive.projection": PROJECTION_SCHEMA,
    "hive.template": TEMPLATE_SCHEMA,
}

DECLARATION_KEYS = {
    "schema",
    "hive_rappid",
    "world_id",
    "created_utc",
    "authority_channel_id",
    "members",
    "rooms",
    "channels",
    "policy",
}
OBJECT_KEYS = {
    "schema",
    "hive_rappid",
    "object_rappid",
    "producer_rappid",
    "world_id",
    "created_utc",
    "room_id",
    "audience",
    "object",
    "source_frames",
    "mutation_keys",
}
SLICE_KEYS = {
    "schema",
    "hive_rappid",
    "source_workspace_rappid",
    "producer_rappid",
    "world_id",
    "created_utc",
    "room_id",
    "audience",
    "classification",
    "content",
    "source_frames",
    "mutation_keys",
}
ASSIMILATION_KEYS = {
    "schema",
    "hive_rappid",
    "slice_payload_hash",
    "recipient_workspace_rappid",
    "recipient_rappid",
    "assimilated_utc",
    "target_namespace",
    "mode",
    "precedence",
    "resulting_layer_hash",
}
CONVERGENCE_KEYS = {
    "schema",
    "hive_rappid",
    "created_utc",
    "base_head_frame_hash",
    "base_convergence_payload_hash",
    "base_catalog_hash",
    "candidates",
    "decisions",
    "resolutions",
    "resulting_catalog_hash",
    "status",
}
RECONCILIATION_KEYS = {
    "schema",
    "hive_rappid",
    "world_id",
    "resolver_rappid",
    "created_utc",
    "base_head_frame_hash",
    "parents",
    "mutation_keys",
    "result",
}
PROJECTION_KEYS = {
    "schema",
    "hive_rappid",
    "convergence_payload_hash",
    "channel_id",
    "projected_utc",
    "registry_seq",
    "catalog_hash",
    "frame_head",
    "artifact_manifest_hash",
    "status",
}
TEMPLATE_KEYS = {
    "schema",
    "source_hive_rappid",
    "template_rappid",
    "created_utc",
    "egg_hash",
    "objects",
    "pii_evidence_hash",
}

MEMBER_ROLES = {"owner", "member", "viewer"}
CHANNEL_KINDS = {"github", "sharepoint", "nas", "lan", "local", "custom"}
CHANNEL_ROLES = {"authority", "writable", "mirror", "cache", "backup"}
DECISION_STATUSES = {"accepted", "duplicate", "conflict", "quarantined", "superseded"}
UINT53_MAX = 2**53 - 1


def rappid(value: object, where: str) -> str:
    require(R.rappid_valid(value), f"{where}: expected RAPP/1 rappid")
    return value


def optional_hex64(value: object, where: str) -> str | None:
    if value is None:
        return None
    return hex64(value, where)


def unique_texts(values: object, where: str, *, maximum: int) -> list[str]:
    require(isinstance(values, list), f"{where}: expected array")
    checked = [
        text(value, f"{where}[{index}]", maximum=maximum)
        for index, value in enumerate(values)
    ]
    require(len(checked) == len(set(checked)), f"{where}: duplicate values are forbidden")
    return checked


def mutation_key(value: object, where: str) -> str:
    value = text(value, where, maximum=512)
    require(all(ord(char) >= 32 and ord(char) != 127 for char in value), f"{where}: control character")
    return value


def mutation_keys(values: object, where: str) -> list[str]:
    require(isinstance(values, list), f"{where}: expected array")
    checked = [mutation_key(value, f"{where}[{index}]") for index, value in enumerate(values)]
    require(checked == sorted(set(checked)), f"{where}: must be unique and sorted")
    return checked


def validate_declaration(payload: dict) -> str:
    canonical_object(payload, "declaration")
    exact_keys(payload, DECLARATION_KEYS, "declaration")
    require(payload["schema"] == DECLARATION_SCHEMA, "declaration.schema: wrong protocol")
    rappid(payload["hive_rappid"], "declaration.hive_rappid")
    label(payload["world_id"], "declaration.world_id")
    utc(payload["created_utc"], "declaration.created_utc")
    label(payload["authority_channel_id"], "declaration.authority_channel_id")

    members = payload["members"]
    require(isinstance(members, list) and members, "declaration.members: expected non-empty array")
    member_ids = []
    owners = 0
    for index, member in enumerate(members):
        where = f"declaration.members[{index}]"
        exact_keys(member, {"rappid", "role", "area"}, where)
        member_id = rappid(member["rappid"], f"{where}.rappid")
        require(member["role"] in MEMBER_ROLES, f"{where}.role: unsupported")
        relative_path(member["area"], f"{where}.area")
        owners += member["role"] == "owner"
        member_ids.append(member_id)
    require(member_ids == sorted(set(member_ids)), "declaration.members: must be unique and sorted by rappid")
    require(owners == 1, "declaration.members: exactly one owner is required")

    rooms = payload["rooms"]
    require(isinstance(rooms, list) and rooms, "declaration.rooms: expected non-empty array")
    room_ids = []
    member_id_set = set(member_ids)
    for index, room in enumerate(rooms):
        where = f"declaration.rooms[{index}]"
        exact_keys(room, {"id", "area", "members", "access"}, where)
        room_id = label(room["id"], f"{where}.id")
        relative_path(room["area"], f"{where}.area")
        require(room["access"] in {"repository", "sealed"}, f"{where}.access: unsupported")
        room_members = room["members"]
        require(isinstance(room_members, list) and room_members, f"{where}.members: expected non-empty array")
        checked_room_members = [
            rappid(value, f"{where}.members[{member_index}]")
            for member_index, value in enumerate(room_members)
        ]
        require(
            checked_room_members == sorted(set(checked_room_members)),
            f"{where}.members: must be unique and sorted",
        )
        require(set(checked_room_members) <= member_id_set, f"{where}.members: contains a non-member")
        room_ids.append(room_id)
    require(room_ids == sorted(set(room_ids)), "declaration.rooms: must be unique and sorted by id")

    channels = payload["channels"]
    require(isinstance(channels, list) and channels, "declaration.channels: expected non-empty array")
    channel_ids = []
    authority_ids = []
    for index, channel in enumerate(channels):
        where = f"declaration.channels[{index}]"
        exact_keys(channel, {"id", "kind", "role", "locator", "writeback"}, where)
        channel_id = label(channel["id"], f"{where}.id")
        require(channel["kind"] in CHANNEL_KINDS, f"{where}.kind: unsupported")
        require(channel["role"] in CHANNEL_ROLES, f"{where}.role: unsupported")
        text(channel["locator"], f"{where}.locator", maximum=2048)
        boolean(channel["writeback"], f"{where}.writeback")
        if channel["role"] == "authority":
            authority_ids.append(channel_id)
            require(channel["writeback"], f"{where}: authority channel must support writeback")
        channel_ids.append(channel_id)
    require(channel_ids == sorted(set(channel_ids)), "declaration.channels: must be unique and sorted by id")
    require(authority_ids == [payload["authority_channel_id"]], "declaration: exactly one named authority channel")

    policy = exact_keys(
        payload["policy"],
        {
            "godd_sharing",
            "default_godd_scope",
            "external_publication",
            "conflict_mode",
            "default_transfer",
        },
        "declaration.policy",
    )
    require(policy["godd_sharing"] == "explicit", "declaration.policy.godd_sharing: must be explicit")
    require(
        policy["default_godd_scope"] == "local-only",
        "declaration.policy.default_godd_scope: must be local-only",
    )
    require(
        policy["external_publication"] == "disabled",
        "declaration.policy.external_publication: must be disabled",
    )
    require(policy["conflict_mode"] == "explicit", "declaration.policy.conflict_mode: must be explicit")
    require(policy["default_transfer"] == "copy", "declaration.policy.default_transfer: must be copy")
    return particle_hash(payload)


def _members(declaration: dict) -> set[str]:
    validate_declaration(declaration)
    return {member["rappid"] for member in declaration["members"]}


def _validate_source_frame(value: dict, where: str) -> tuple[str, str]:
    exact_keys(
        value,
        {"stream_id", "seq", "utc", "payload_hash", "frame_hash"},
        where,
    )
    text(value["stream_id"], f"{where}.stream_id", maximum=512)
    bounded_int(value["seq"], f"{where}.seq", 0, UINT53_MAX)
    utc(value["utc"], f"{where}.utc")
    hex64(value["payload_hash"], f"{where}.payload_hash")
    hex64(value["frame_hash"], f"{where}.frame_hash")
    return value["utc"], value["frame_hash"]


def _validate_room_audience(
    payload: dict,
    declaration: dict,
    *,
    where: str,
) -> tuple[str, list[str]]:
    room_id = label(payload["room_id"], f"{where}.room_id")
    rooms = {room["id"]: room for room in declaration["rooms"]}
    require(room_id in rooms, f"{where}.room_id: unknown room")
    audience = payload["audience"]
    require(isinstance(audience, list) and audience, f"{where}.audience: expected non-empty array")
    checked = [rappid(value, f"{where}.audience[{index}]") for index, value in enumerate(audience)]
    require(checked == sorted(set(checked)), f"{where}.audience: must be unique and sorted")
    require(set(checked) <= _members(declaration), f"{where}.audience: contains a non-member")
    require(
        set(checked) <= set(rooms[room_id]["members"]),
        f"{where}.audience: contains a member outside the selected room",
    )
    return rooms[room_id]["access"], checked


def _validate_sources_and_mutations(payload: dict, where: str) -> None:
    source_frames = payload["source_frames"]
    require(isinstance(source_frames, list), f"{where}.source_frames: expected array")
    frame_order = [
        _validate_source_frame(frame, f"{where}.source_frames[{index}]")
        for index, frame in enumerate(source_frames)
    ]
    require(
        frame_order == sorted(set(frame_order)),
        f"{where}.source_frames: must be unique in RAPP/1 Dream-Catcher order",
    )
    mutation_keys(payload["mutation_keys"], f"{where}.mutation_keys")


def validate_shared_object(payload: dict, declaration: dict) -> str:
    canonical_object(payload, "shared object")
    exact_keys(payload, OBJECT_KEYS, "shared object")
    require(payload["schema"] == OBJECT_SCHEMA, "shared object.schema: wrong protocol")
    validate_declaration(declaration)
    require(payload["hive_rappid"] == declaration["hive_rappid"], "shared object: hive mismatch")
    rappid(payload["object_rappid"], "shared object.object_rappid")
    producer = rappid(payload["producer_rappid"], "shared object.producer_rappid")
    require(producer in _members(declaration), "shared object: producer is not a Hive member")
    require(payload["world_id"] == declaration["world_id"], "shared object: world mismatch")
    utc(payload["created_utc"], "shared object.created_utc")
    room_access, _ = _validate_room_audience(payload, declaration, where="shared object")

    descriptor = exact_keys(
        payload["object"],
        {
            "space",
            "hash",
            "kind",
            "data_class",
            "pii_status",
            "pii_evidence_hash",
            "protection",
            "target_path",
        },
        "shared object.object",
    )
    require(
        descriptor["space"] in {"rapp/1:particle", "rapp/1:wave", "rapp/1:egg-manifest"},
        "shared object.object.space: unsupported",
    )
    hex64(descriptor["hash"], "shared object.object.hash")
    text(descriptor["kind"], "shared object.object.kind", maximum=128)
    require(
        descriptor["data_class"] in {"dogg", "godd", "neutral"},
        "shared object.object.data_class: unsupported",
    )
    require(
        descriptor["pii_status"] in {"none", "present", "unknown", "not-applicable"},
        "shared object.object.pii_status: unsupported",
    )
    optional_hex64(descriptor["pii_evidence_hash"], "shared object.object.pii_evidence_hash")
    require(
        descriptor["protection"] in {"member-visible", "sealed-room"},
        "shared object.object.protection: unsupported",
    )
    relative_path(descriptor["target_path"], "shared object.object.target_path")
    if descriptor["protection"] == "sealed-room":
        require(room_access == "sealed", "shared object: sealed-room object requires a sealed room")
        require(
            descriptor["space"] == "rapp/1:egg-manifest",
            "shared object: sealed-room object must use a sealed egg address",
        )
    if room_access == "sealed":
        require(
            descriptor["protection"] == "sealed-room",
            "shared object: sealed room requires sealed-room protection",
        )
    if descriptor["data_class"] == "godd":
        require(
            descriptor["protection"] == "sealed-room",
            "shared object: GODD object must use sealed-room protection",
        )
    if descriptor["data_class"] == "dogg":
        require(descriptor["pii_status"] == "none", "shared object: DOGG must be PII-free")
        require(
            descriptor["pii_evidence_hash"] is not None,
            "shared object: DOGG requires PII-scan evidence",
        )
    _validate_sources_and_mutations(payload, "shared object")
    return particle_hash(payload)


def validate_godd_slice(payload: dict, declaration: dict) -> str:
    canonical_object(payload, "godd slice")
    exact_keys(payload, SLICE_KEYS, "godd slice")
    require(payload["schema"] == SLICE_SCHEMA, "godd slice.schema: wrong protocol")
    declaration_hash = validate_declaration(declaration)
    del declaration_hash
    require(payload["hive_rappid"] == declaration["hive_rappid"], "godd slice: hive mismatch")
    rappid(payload["source_workspace_rappid"], "godd slice.source_workspace_rappid")
    producer = rappid(payload["producer_rappid"], "godd slice.producer_rappid")
    require(payload["world_id"] == declaration["world_id"], "godd slice: world mismatch")
    utc(payload["created_utc"], "godd slice.created_utc")

    members = _members(declaration)
    require(producer in members, "godd slice: producer is not a Hive member")
    room_access, _ = _validate_room_audience(payload, declaration, where="godd slice")
    require(room_access == "sealed", "godd slice: GODD requires a sealed room")

    classification = exact_keys(
        payload["classification"],
        {"estate", "scope", "sensitivity", "dogg_projection_allowed"},
        "godd slice.classification",
    )
    require(classification["estate"] == "godd", "godd slice.classification.estate: must be godd")
    require(classification["scope"] == "hive-shared", "godd slice.classification.scope: must be hive-shared")
    label(classification["sensitivity"], "godd slice.classification.sensitivity")
    boolean(
        classification["dogg_projection_allowed"],
        "godd slice.classification.dogg_projection_allowed",
    )

    content = exact_keys(
        payload["content"],
        {
            "sealed_egg_hash",
            "artifact_rappid",
            "plaintext_schema",
            "plaintext_bytes",
            "record_count",
        },
        "godd slice.content",
    )
    hex64(content["sealed_egg_hash"], "godd slice.content.sealed_egg_hash")
    rappid(content["artifact_rappid"], "godd slice.content.artifact_rappid")
    text(content["plaintext_schema"], "godd slice.content.plaintext_schema", maximum=128)
    bounded_int(
        content["plaintext_bytes"],
        "godd slice.content.plaintext_bytes",
        0,
        R.MAX_SEALED_PLAINTEXT_BYTES,
    )
    bounded_int(content["record_count"], "godd slice.content.record_count", 0, UINT53_MAX)

    _validate_sources_and_mutations(payload, "godd slice")
    return particle_hash(payload)


def validate_assimilation(payload: dict, declaration: dict, godd_slice: dict) -> str:
    canonical_object(payload, "assimilation")
    exact_keys(payload, ASSIMILATION_KEYS, "assimilation")
    require(payload["schema"] == ASSIMILATION_SCHEMA, "assimilation.schema: wrong protocol")
    validate_declaration(declaration)
    slice_hash = validate_godd_slice(godd_slice, declaration)
    require(payload["hive_rappid"] == declaration["hive_rappid"], "assimilation: hive mismatch")
    require(payload["slice_payload_hash"] == slice_hash, "assimilation: slice hash mismatch")
    rappid(payload["recipient_workspace_rappid"], "assimilation.recipient_workspace_rappid")
    recipient = rappid(payload["recipient_rappid"], "assimilation.recipient_rappid")
    require(recipient in _members(declaration), "assimilation: recipient is not a Hive member")
    require(recipient in godd_slice["audience"], "assimilation: recipient is outside slice audience")
    utc(payload["assimilated_utc"], "assimilation.assimilated_utc")
    relative_path(payload["target_namespace"], "assimilation.target_namespace")
    require(payload["mode"] in {"overlay", "copy", "materialize"}, "assimilation.mode: unsupported")
    bounded_int(payload["precedence"], "assimilation.precedence", 0, 1000)
    hex64(payload["resulting_layer_hash"], "assimilation.resulting_layer_hash")
    return particle_hash(payload)


def _validate_candidate(candidate: dict, where: str) -> tuple[str, str]:
    exact_keys(
        candidate,
        {
            "dimension_rappid",
            "stream_id",
            "seq",
            "utc",
            "payload_hash",
            "frame_hash",
            "mutation_keys",
            "source_channel_ids",
        },
        where,
    )
    rappid(candidate["dimension_rappid"], f"{where}.dimension_rappid")
    text(candidate["stream_id"], f"{where}.stream_id", maximum=512)
    bounded_int(candidate["seq"], f"{where}.seq", 0, UINT53_MAX)
    utc(candidate["utc"], f"{where}.utc")
    hex64(candidate["payload_hash"], f"{where}.payload_hash")
    hex64(candidate["frame_hash"], f"{where}.frame_hash")
    mutation_keys(candidate["mutation_keys"], f"{where}.mutation_keys")
    channels = unique_strings(candidate["source_channel_ids"], f"{where}.source_channel_ids", labels=True)
    require(channels == sorted(channels), f"{where}.source_channel_ids: must be sorted")
    return candidate["utc"], candidate["frame_hash"]


def validate_convergence(payload: dict, declaration: dict) -> str:
    """Validate shape and local references, NOT decisions, history or acceptance."""
    canonical_object(payload, "convergence")
    exact_keys(payload, CONVERGENCE_KEYS, "convergence")
    require(payload["schema"] == CONVERGENCE_SCHEMA, "convergence.schema: wrong protocol")
    validate_declaration(declaration)
    require(payload["hive_rappid"] == declaration["hive_rappid"], "convergence: hive mismatch")
    utc(payload["created_utc"], "convergence.created_utc")
    optional_hex64(payload["base_head_frame_hash"], "convergence.base_head_frame_hash")
    optional_hex64(
        payload["base_convergence_payload_hash"],
        "convergence.base_convergence_payload_hash",
    )
    hex64(payload["base_catalog_hash"], "convergence.base_catalog_hash")

    candidates = payload["candidates"]
    require(isinstance(candidates, list) and candidates, "convergence.candidates: expected non-empty array")
    candidate_order = [
        _validate_candidate(candidate, f"convergence.candidates[{index}]")
        for index, candidate in enumerate(candidates)
    ]
    require(
        candidate_order == sorted(candidate_order),
        "convergence.candidates: must use RAPP/1 utc then frame_hash order",
    )
    frame_hashes = [candidate["frame_hash"] for candidate in candidates]
    require(len(frame_hashes) == len(set(frame_hashes)), "convergence.candidates: duplicate frame")

    decisions = payload["decisions"]
    require(isinstance(decisions, list), "convergence.decisions: expected array")
    decision_hashes = []
    decision_by_hash = {}
    for index, decision in enumerate(decisions):
        where = f"convergence.decisions[{index}]"
        exact_keys(decision, {"frame_hash", "status", "reason_code"}, where)
        frame_hash = hex64(decision["frame_hash"], f"{where}.frame_hash")
        require(decision["status"] in DECISION_STATUSES, f"{where}.status: unsupported")
        label(decision["reason_code"], f"{where}.reason_code")
        decision_hashes.append(frame_hash)
        decision_by_hash[frame_hash] = decision
    require(
        decision_hashes == sorted(frame_hashes),
        "convergence.decisions: must cover every candidate exactly once in frame_hash order",
    )

    resolutions = payload["resolutions"]
    require(isinstance(resolutions, list), "convergence.resolutions: expected array")
    resolution_keys = []
    for index, resolution in enumerate(resolutions):
        where = f"convergence.resolutions[{index}]"
        exact_keys(resolution, {"mutation_key", "frame_hashes", "resolution_frame_hash"}, where)
        key = mutation_key(resolution["mutation_key"], f"{where}.mutation_key")
        refs = resolution["frame_hashes"]
        require(isinstance(refs, list) and len(refs) >= 2, f"{where}.frame_hashes: expected 2+ frames")
        checked_refs = [hex64(value, f"{where}.frame_hashes[{i}]") for i, value in enumerate(refs)]
        require(checked_refs == sorted(set(checked_refs)), f"{where}.frame_hashes: must be unique and sorted")
        resolution_hash = hex64(resolution["resolution_frame_hash"], f"{where}.resolution_frame_hash")
        require(resolution_hash in frame_hashes, f"{where}.resolution_frame_hash: unknown candidate")
        require(resolution_hash not in checked_refs, f"{where}: resolver cannot be its own parent")
        require(
            decision_by_hash[resolution_hash]["status"] == "accepted",
            f"{where}.resolution_frame_hash: resolution frame must be accepted",
        )
        resolution_keys.append(key)
    require(
        resolution_keys == sorted(set(resolution_keys)),
        "convergence.resolutions: must be unique and sorted by mutation_key",
    )

    conflicts = [decision for decision in decisions if decision["status"] == "conflict"]
    require(payload["status"] in {"converged", "partial"}, "convergence.status: unsupported")
    require(
        (payload["status"] == "partial") == bool(conflicts),
        "convergence.status: partial iff unresolved conflicts remain",
    )
    hex64(payload["resulting_catalog_hash"], "convergence.resulting_catalog_hash")
    return particle_hash(payload)


def validate_reconciliation(payload: dict, declaration: dict) -> str:
    canonical_object(payload, "reconciliation")
    exact_keys(payload, RECONCILIATION_KEYS, "reconciliation")
    validate_declaration(declaration)
    require(payload["schema"] == RECONCILIATION_SCHEMA, "reconciliation.schema: wrong protocol")
    require(payload["hive_rappid"] == declaration["hive_rappid"], "reconciliation: hive mismatch")
    require(payload["world_id"] == declaration["world_id"], "reconciliation: world mismatch")
    rappid(payload["resolver_rappid"], "reconciliation.resolver_rappid")
    utc(payload["created_utc"], "reconciliation.created_utc")
    hex64(payload["base_head_frame_hash"], "reconciliation.base_head_frame_hash")
    parents = payload["parents"]
    require(isinstance(parents, list) and len(parents) >= 2, "reconciliation.parents: expected 2+ frames")
    checked = [hex64(value, "reconciliation.parents") for value in parents]
    require(checked == sorted(set(checked)), "reconciliation.parents: must be unique and sorted")
    require(mutation_keys(payload["mutation_keys"], "reconciliation.mutation_keys"), "reconciliation: no mutations")
    validate_artifact_address(payload["result"], "reconciliation.result")
    return particle_hash(payload)


def validate_artifact_address(value: dict, where: str) -> tuple[str, str]:
    exact_keys(value, {"space", "hash"}, where)
    require(
        value["space"] in {"rapp/1:particle", "rapp/1:wave", "rapp/1:egg-manifest"},
        f"{where}.space: unsupported",
    )
    return value["space"], hex64(value["hash"], f"{where}.hash")


def catalog_payload(declaration: dict, frames: dict[str, dict]) -> dict:
    """Commit the append-only accepted-frame set, never a caller-supplied hash."""
    validate_declaration(declaration)
    entries = []
    for frame_hash, frame in sorted(frames.items()):
        require(frame_hash == frame["frame_hash"], "catalog: frame address mismatch")
        entries.append({"frame_hash": hex64(frame_hash, "catalog.frame_hash"),
                        "payload_hash": hex64(frame["payload_hash"], "catalog.payload_hash")})
    payload = {
        "schema": CATALOG_SCHEMA,
        "hive_rappid": declaration["hive_rappid"],
        "world_id": declaration["world_id"],
        "frames": entries,
    }
    validate_catalog(payload)
    return payload


def validate_catalog(payload: dict) -> str:
    canonical_object(payload, "catalog")
    exact_keys(payload, {"schema", "hive_rappid", "world_id", "frames"}, "catalog")
    require(payload["schema"] == CATALOG_SCHEMA, "catalog.schema: wrong protocol")
    rappid(payload["hive_rappid"], "catalog.hive_rappid")
    label(payload["world_id"], "catalog.world_id")
    require(isinstance(payload["frames"], list), "catalog.frames: expected array")
    hashes = []
    for entry in payload["frames"]:
        exact_keys(entry, {"frame_hash", "payload_hash"}, "catalog frame")
        hashes.append(hex64(entry["frame_hash"], "catalog frame.frame_hash"))
        hex64(entry["payload_hash"], "catalog frame.payload_hash")
    require(hashes == sorted(set(hashes)), "catalog.frames: must be unique and sorted by frame_hash")
    return particle_hash(payload)


def validate_artifact_manifest(payload: dict) -> str:
    canonical_object(payload, "artifact manifest")
    exact_keys(payload, {"schema", "hive_rappid", "world_id", "registry_seq", "registry_hash",
                         "frame_head", "catalog_hash", "artifacts"}, "artifact manifest")
    require(payload["schema"] == MANIFEST_SCHEMA, "artifact manifest.schema: wrong protocol")
    rappid(payload["hive_rappid"], "artifact manifest.hive_rappid")
    label(payload["world_id"], "artifact manifest.world_id")
    bounded_int(payload["registry_seq"], "artifact manifest.registry_seq", 0, UINT53_MAX)
    for key in ("registry_hash", "frame_head", "catalog_hash"):
        hex64(payload[key], "artifact manifest." + key)
    artifacts = payload["artifacts"]
    require(isinstance(artifacts, list) and artifacts, "artifact manifest.artifacts: expected non-empty array")
    order = [validate_artifact_address(value, "artifact manifest address") for value in artifacts]
    require(order == sorted(set(order)), "artifact manifest.artifacts: must be unique in (space, hash) order")
    return particle_hash(payload)


def validate_projection(payload: dict, declaration: dict, convergence: dict | None = None) -> str:
    """Validate receipt shape; only HiveAcceptance.accept_projection proves currency."""
    canonical_object(payload, "projection")
    exact_keys(payload, PROJECTION_KEYS, "projection")
    require(payload["schema"] == PROJECTION_SCHEMA, "projection.schema: wrong protocol")
    validate_declaration(declaration)
    require(payload["hive_rappid"] == declaration["hive_rappid"], "projection: hive mismatch")
    hex64(payload["convergence_payload_hash"], "projection.convergence_payload_hash")
    if convergence is not None:
        convergence_hash = validate_convergence(convergence, declaration)
        require(
            payload["convergence_payload_hash"] == convergence_hash,
            "projection: convergence hash mismatch",
        )
    channel_ids = {channel["id"] for channel in declaration["channels"]}
    require(payload["channel_id"] in channel_ids, "projection.channel_id: unknown channel")
    utc(payload["projected_utc"], "projection.projected_utc")
    bounded_int(payload["registry_seq"], "projection.registry_seq", 0, UINT53_MAX)
    hex64(payload["catalog_hash"], "projection.catalog_hash")
    hex64(payload["frame_head"], "projection.frame_head")
    hex64(payload["artifact_manifest_hash"], "projection.artifact_manifest_hash")
    require(payload["status"] in {"current", "stale", "failed"}, "projection.status: unsupported")
    if payload["status"] == "current" and convergence is not None:
        require(
            payload["catalog_hash"] == convergence["resulting_catalog_hash"],
            "projection: current channel must match convergence catalog",
        )
    return particle_hash(payload)


def validate_template(payload: dict) -> str:
    canonical_object(payload, "template")
    exact_keys(payload, TEMPLATE_KEYS, "template")
    require(payload["schema"] == TEMPLATE_SCHEMA, "template.schema: wrong protocol")
    source_hive = rappid(payload["source_hive_rappid"], "template.source_hive_rappid")
    template_rappid = rappid(payload["template_rappid"], "template.template_rappid")
    require(template_rappid != source_hive, "template: template identity must differ from live Hive")
    utc(payload["created_utc"], "template.created_utc")
    hex64(payload["egg_hash"], "template.egg_hash")
    hex64(payload["pii_evidence_hash"], "template.pii_evidence_hash")
    objects = payload["objects"]
    require(isinstance(objects, list), "template.objects: expected array")
    object_hashes = []
    for index, item in enumerate(objects):
        where = f"template.objects[{index}]"
        exact_keys(item, {"object_payload_hash", "data_class", "pii_status"}, where)
        object_hash = hex64(item["object_payload_hash"], f"{where}.object_payload_hash")
        require(item["data_class"] in {"dogg", "neutral"}, f"{where}: GODD is forbidden")
        if item["data_class"] == "dogg":
            require(item["pii_status"] == "none", f"{where}: DOGG must be PII-free")
        else:
            require(
                item["pii_status"] in {"none", "not-applicable"},
                f"{where}: neutral object has unresolved PII status",
            )
        object_hashes.append(object_hash)
    require(
        object_hashes == sorted(set(object_hashes)),
        "template.objects: must be unique and sorted by object_payload_hash",
    )
    return particle_hash(payload)


def authorize_hive_frame(
    frame: dict,
    *,
    expected_schema: str,
    head: dict | None,
    stream_id: str,
    registered_kinds: set[str],
    signature_verifier,
    authorization_verifier,
) -> dict:
    """Authenticate an envelope via trusted parent verifiers, not convergence acceptance."""
    require(isinstance(frame, dict), "rapp-hive/1: expected frame object")
    require(
        expected_schema in KIND_SCHEMAS.values() and KIND_SCHEMAS.get(frame.get("kind")) == expected_schema,
        "rapp-hive/1: exact kind-to-schema binding required",
    )
    return authoritative_frame_payload(
        frame,
        expected_schema=expected_schema,
        purpose="rapp-hive/1",
        head=head,
        stream_id=stream_id,
        registered_kinds=registered_kinds,
        signature_verifier=signature_verifier,
        authorization_verifier=authorization_verifier,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("document")
    parser.add_argument("--declaration")
    parser.add_argument("--slice")
    parser.add_argument("--convergence")
    args = parser.parse_args(argv)
    payload = load_json(args.document)
    schema = payload.get("schema")
    if schema == DECLARATION_SCHEMA:
        result = validate_declaration(payload)
    elif schema == OBJECT_SCHEMA:
        require(args.declaration is not None, "--declaration is required")
        result = validate_shared_object(payload, load_json(args.declaration))
    elif schema == SLICE_SCHEMA:
        require(args.declaration is not None, "--declaration is required")
        result = validate_godd_slice(payload, load_json(args.declaration))
    elif schema == ASSIMILATION_SCHEMA:
        require(args.declaration is not None and args.slice is not None, "--declaration and --slice are required")
        result = validate_assimilation(
            payload,
            load_json(args.declaration),
            load_json(args.slice),
        )
    elif schema in {CONVERGENCE_SCHEMA, RECONCILIATION_SCHEMA}:
        require(args.declaration is not None, "--declaration is required")
        validator = validate_convergence if schema == CONVERGENCE_SCHEMA else validate_reconciliation
        result = validator(payload, load_json(args.declaration))
    elif schema == PROJECTION_SCHEMA:
        require(args.declaration is not None and args.convergence is not None,
                "--declaration and --convergence are required")
        result = validate_projection(payload, load_json(args.declaration), load_json(args.convergence))
    elif schema == TEMPLATE_SCHEMA:
        result = validate_template(payload)
    elif schema == CATALOG_SCHEMA:
        result = validate_catalog(payload)
    elif schema == MANIFEST_SCHEMA:
        result = validate_artifact_manifest(payload)
    else:
        raise ValueError(f"unsupported standalone schema: {schema}")
    print(json.dumps({"status": "payload-conformant", "authenticated": False, "payload_hash": result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "refused", "error": str(error)}, sort_keys=True), file=sys.stderr)
        raise SystemExit(1)
