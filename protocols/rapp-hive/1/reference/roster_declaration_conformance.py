"""Draft proposal 0001 vectors: owner-signed later rapp-hive/1 declarations.

The proposal is NOT accepted. The default HiveAcceptance gate must keep refusing
every declaration after the Mother genesis. The explicit roster_declarations=True
proposal mode must pass the positive and refusal vectors below and must replay
every existing authenticated vector unchanged. All identities are fixtures.
"""

from __future__ import annotations

import copy
import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

import authenticated_conformance as A
import rapp as R
import rapp_hive as H
from authenticated_conformance import SCHEMA, Estate, decision_map, octets, stamp
from hive_acceptance import ROSTER_REVOKED, HiveAcceptance
from rapp_profile import particle_hash


NAS = {"id": "nas-main", "kind": "nas", "role": "mirror",
       "locator": "smb://nas.example.invalid/private-hive", "writeback": False}


def roster_gate(estate, document=None, resolver=None):
    return HiveAcceptance(estate.authority(document), estate.hive,
                          resolver or (lambda address: estate.chains[address]), roster_declarations=True)


def roster(gate, seconds, *, channels=None, authority=None):
    payload = gate.declaration
    payload["created_utc"] = stamp(seconds)
    if channels is not None:
        payload["channels"] = sorted(copy.deepcopy(channels), key=lambda item: item["id"])
    if authority is not None:
        payload["authority_channel_id"] = authority
    return payload


def without(estate, gate, seconds, *names):
    """Remove members from the Hive and from every room."""
    gone = {estate.identities[name] for name in names}
    payload = roster(gate, seconds)
    payload["members"] = [item for item in payload["members"] if item["rappid"] not in gone]
    for room in payload["rooms"]:
        room["members"] = [value for value in room["members"] if value not in gone]
    return payload


def admit(estate, gate, seconds, name, *, role="member", rooms=("general",)):
    payload = roster(gate, seconds)
    payload["members"] = sorted(
        payload["members"] + [{"rappid": estate.identities[name], "role": role, "area": "members/" + name}],
        key=lambda item: item["rappid"])
    for room in payload["rooms"]:
        if room["id"] in rooms:
            room["members"] = sorted(room["members"] + [estate.identities[name]])
    return payload


def with_roles(estate, gate, seconds, **roles):
    payload = roster(gate, seconds)
    for item in payload["members"]:
        for name, role in roles.items():
            if item["rappid"] == estate.identities[name]:
                item["role"] = role
    return payload


def declare(estate, gate, payload, *, signer="alice", previous=None):
    return estate.frame("hive.declaration", estate.hive, payload, previous=previous or gate.head, signer=signer)


def summaries(estate, *frames, channels=("github-main",)):
    values = []
    for frame in frames:
        values.append({
            "dimension_rappid": frame["stream_id"], "source_channel_ids": sorted(channels),
            **{key: frame[key] for key in ("stream_id", "seq", "utc", "payload_hash", "frame_hash")},
            "mutation_keys": list(frame["payload"].get("mutation_keys", [])),
        })
    return sorted(values, key=lambda item: (item["utc"], item["frame_hash"]))


def propose(estate, gate, *frames, seconds, channels=("github-main",)):
    return gate.preview_convergence(summaries(estate, *frames, channels=channels), stamp(seconds))


def reasons(payload):
    return {item["frame_hash"]: (item["status"], item["reason_code"]) for item in payload["decisions"]}


def obj(estate, producer, seconds, keys, *, audience, room="general", target=None, stream=None, previous=None,
        sources=()):
    """Like Estate.object, but with an explicit audience (Estate.object addresses the genesis room)."""
    data = {"fixture": producer, "room": room, "revision": seconds}
    address = particle_hash(data)
    estate.artifacts[("rapp/1:particle", address)] = octets(data)
    payload = {
        "schema": H.OBJECT_SCHEMA, "hive_rappid": estate.hive, "object_rappid": estate.stream(producer, "object"),
        "producer_rappid": estate.identities[producer], "world_id": "example-world", "created_utc": stamp(seconds),
        "room_id": room, "audience": sorted(estate.identities[name] for name in audience),
        "object": {"space": "rapp/1:particle", "hash": address, "kind": "example-data", "data_class": "neutral",
                   "pii_status": "not-applicable", "pii_evidence_hash": None, "protection": "member-visible",
                   "target_path": target or f"members/{producer}/data.json"},
        "source_frames": sorted([
            {key: frame[key] for key in ("stream_id", "seq", "utc", "payload_hash", "frame_hash")}
            for frame in sources
        ], key=lambda item: (item["utc"], item["frame_hash"])),
        "mutation_keys": sorted(keys),
    }
    return estate.frame("hive.object", stream or estate.stream(producer), payload, previous=previous,
                        signer=producer)


CURRENT = ("alice", "carol", "viewer")


def room_object(estate, producer, seconds, keys, *, room, audience, target, stream):
    return obj(estate, producer, seconds, keys, audience=audience, room=room, target=target, stream=stream)


def godd_slice(estate, producer, seconds, audience, keys, *, stream, previous=None):
    payload = {
        "schema": H.SLICE_SCHEMA, "hive_rappid": estate.hive,
        "source_workspace_rappid": estate.stream(producer, "workspace"),
        "producer_rappid": estate.identities[producer], "world_id": "example-world",
        "created_utc": stamp(seconds), "room_id": "sealed",
        "audience": sorted(estate.identities[name] for name in audience),
        "classification": {"estate": "godd", "scope": "hive-shared", "sensitivity": "confidential",
                           "dogg_projection_allowed": False},
        "content": {"sealed_egg_hash": hashlib.sha256(f"PUBLIC TEST VECTOR sealed egg {seconds}".encode()).hexdigest(),
                    "artifact_rappid": estate.stream(producer, "shared-godd"), "plaintext_schema": "example-godd/1",
                    "plaintext_bytes": 64, "record_count": 1},
        "source_frames": [], "mutation_keys": sorted(keys),
    }
    return estate.frame("hive.godd-slice", stream, payload, previous=previous, signer=producer)


def key_release_eligible(declaration, slice_payload, recipient):
    """rapp-hive/1 section 3.1: a current member of the declared room AND in the slice's explicit audience."""
    room = next((item for item in declaration["rooms"] if item["id"] == slice_payload["room_id"]), None)
    members = {item["rappid"] for item in declaration["members"]}
    return (room is not None and recipient in members and recipient in room["members"]
            and recipient in slice_payload["audience"])


def receipt_genesis(estate, channel, slug):
    return estate.frame("hive.projection", estate.stream("alice", slug), {
        "schema": H.PROJECTION_SCHEMA, "hive_rappid": estate.hive, "convergence_payload_hash": "0" * 64,
        "channel_id": channel, "projected_utc": stamp(2), "registry_seq": 0,
        "catalog_hash": particle_hash(H.catalog_payload(estate.declaration, {})),
        "frame_head": estate.mother["frame_hash"], "artifact_manifest_hash": "0" * 64, "status": "stale",
    })


def receipt(estate, gate, genesis, channel, seconds, convergence, *, previous=None, **changes):
    manifest = gate.artifact_manifest()
    payload = {
        "schema": H.PROJECTION_SCHEMA, "hive_rappid": estate.hive, "convergence_payload_hash": convergence,
        "channel_id": channel, "projected_utc": stamp(seconds), "registry_seq": gate.registry.sequence,
        "catalog_hash": particle_hash(gate.catalog), "frame_head": gate.head["frame_hash"],
        "artifact_manifest_hash": particle_hash(manifest), "status": "current",
    }
    payload.update(changes)
    return estate.frame("hive.projection", genesis["stream_id"], payload, previous=previous or genesis), manifest


def project(estate, gate, frame, manifest):
    artifacts = estate.projection_artifacts(gate)
    return gate.accept_projection(frame["frame_hash"], manifest_bytes=octets(manifest),
                                  artifact_resolver=lambda space, value: artifacts[(space, value)])


def without_registry(checkpoint):
    return {key: value for key, value in checkpoint.items() if not key.startswith("registry_")}


class DefaultGateRefusesLaterDeclarations(unittest.TestCase):
    """Normative today: the only rapp-hive/1 declaration is the Mother's registered creation genesis."""

    def test_accept_declaration_requires_the_explicit_opt_in(self):
        estate = Estate()
        gate = estate.gate()
        later = declare(estate, gate, without(estate, gate, 50, "bob"))
        before = gate.checkpoint()
        with self.assertRaisesRegex(ValueError, "explicit proposal 0001 opt-in"):
            gate.accept_declaration(later["frame_hash"])
        with self.assertRaisesRegex(ValueError, "unaccepted policy replacement"):
            gate.accept_convergence(later["frame_hash"])
        self.assertEqual(gate.checkpoint(), before)
        self.assertEqual(gate.declaration, estate.declaration)
        for value in (1, "true", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "explicit boolean opt-in"):
                HiveAcceptance(estate.authority(), estate.hive, lambda address: estate.chains[address],
                               roster_declarations=value)

    def test_convergence_extending_a_later_declaration_is_refused(self):
        estate = Estate()
        gate = estate.gate()
        later = declare(estate, gate, without(estate, gate, 50, "bob"))
        payload = estate.proposal(gate, estate.a)
        stacked = estate.frame("hive.convergence", estate.hive, payload, previous=later)
        with self.assertRaisesRegex(ValueError, "unaccepted policy replacement"):
            gate.accept_convergence(stacked["frame_hash"])
        self.assertEqual(gate.head, estate.mother)
        estate.commit(gate, payload)
        self.assertEqual(len(gate.catalog["frames"]), 1)

    def test_restore_of_a_history_with_a_later_declaration_fails_closed(self):
        estate = Estate()
        gate = roster_gate(estate)
        estate.commit(gate, estate.proposal(gate, estate.a))
        later = declare(estate, gate, without(estate, gate, 150, "carol"))
        gate.accept_declaration(later["frame_hash"])
        head = estate.commit(gate, estate.proposal(gate, estate.b, seconds=200))
        legacy = estate.gate()
        with self.assertRaisesRegex(ValueError, "unaccepted policy replacement"):
            legacy.restore(head["frame_hash"])
        for action in (legacy.checkpoint, lambda: legacy.accept_declaration(later["frame_hash"])):
            with self.assertRaisesRegex(ValueError, "failed history recovery"):
                action()

    def test_identical_redeclaration_is_not_a_successor_in_either_mode(self):
        estate = Estate()
        same = estate.frame("hive.declaration", estate.hive, estate.declaration, previous=estate.mother)
        gate = estate.gate()
        with self.assertRaisesRegex(ValueError, "wrong Mother Hive kind"):
            gate.accept_convergence(same["frame_hash"])
        with self.assertRaisesRegex(ValueError, "opt-in"):
            gate.accept_declaration(same["frame_hash"])
        proposed = roster_gate(estate)
        with self.assertRaisesRegex(ValueError, "strictly after the Mother head"):
            proposed.accept_declaration(same["frame_hash"])
        self.assertEqual(proposed.head, estate.mother)

    def test_a_registered_genesis_not_signed_by_the_owner_is_refused_in_both_modes(self):
        estate = Estate()
        # Bob's key is registered and the registry names his frame as the Mother genesis, so only the declaration
        # owner check can refuse it (proposal mutation M1 reaches the default path here).
        forged = estate.frame("hive.declaration", estate.hive, estate.declaration, signer="bob")
        self.assertEqual(estate.genesis[estate.hive], forged["frame_hash"])
        for opt_in in (False, True):
            with self.subTest(roster_declarations=opt_in), self.assertRaisesRegex(
                    ValueError, "declaration: owner authorization mismatch"):
                HiveAcceptance(estate.authority(), estate.hive, lambda address: estate.chains[address],
                               roster_declarations=opt_in)


class RosterDeclarationVectors(unittest.TestCase):
    """Proposal 0001 positive vectors, all with real Ed25519 signatures."""

    def test_later_declaration_uses_the_same_closed_declaration_schema(self):
        estate = Estate()
        gate = roster_gate(estate)
        payload = admit(estate, gate, 50, "outsider")
        self.assertEqual(set(payload), H.DECLARATION_KEYS)
        Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(payload)
        self.assertEqual(H.validate_declaration(payload), particle_hash(payload))
        frame = declare(estate, gate, payload)
        self.assertEqual(set(frame), R.FRAME_KEYS)
        self.assertEqual((frame["kind"], frame["stream_id"], frame["seq"]), ("hive.declaration", estate.hive, 1))
        result = gate.accept_declaration(frame["frame_hash"])
        self.assertIs(result["authenticated"], True)
        self.assertEqual(result["mother_head_frame_hash"], frame["frame_hash"])
        self.assertEqual(gate.declaration, payload)
        self.assertEqual(gate.catalog, H.catalog_payload(estate.declaration, {}))

    def test_add_member_then_accept_their_candidate(self):
        estate = Estate()
        joined = estate.object("outsider", 20, ["outsider/key"])
        gate = roster_gate(estate)
        first = propose(estate, gate, joined, estate.a, seconds=100)
        self.assertEqual(reasons(first)[joined["frame_hash"]], ("quarantined", "invalid-candidate"))
        self.assertEqual(decision_map(first)[estate.a["frame_hash"]], "accepted")
        estate.commit(gate, first)
        gate.accept_declaration(declare(estate, gate, admit(estate, gate, 150, "outsider"))["frame_hash"])
        second = propose(estate, gate, joined, seconds=200)
        self.assertEqual(decision_map(second), {joined["frame_hash"]: "accepted"})
        estate.commit(gate, second)
        self.assertIn({"frame_hash": joined["frame_hash"], "payload_hash": joined["payload_hash"]},
                      gate.catalog["frames"])

    def test_remove_member_quarantines_unsettled_frames_and_keeps_history(self):
        estate = Estate()
        later_bob = estate.object("bob", 30, ["bob/key"], previous=estate.b)
        backdated = estate.object("bob", 5, ["bob/other"], stream=estate.stream("bob", "backdated"))
        cites_history = obj(estate, "carol", 60, ["carol/key"], audience=CURRENT, sources=[estate.b])
        cites_unsettled = obj(estate, "carol", 61, ["carol/other"], audience=CURRENT,
                              stream=estate.stream("carol", "second"), sources=[later_bob])
        # rapp-hive/1 section 5: an audience is a subset of the members in effect where the frame is accepted.
        addressed = estate.object("carol", 62, ["carol/addressed"], stream=estate.stream("carol", "third"))
        reissued = obj(estate, "carol", 63, ["carol/addressed"], audience=CURRENT,
                       stream=estate.stream("carol", "fourth"))
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.a, estate.b, seconds=100))
        catalog = gate.catalog
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        self.assertEqual(gate.catalog, catalog)
        proposal = propose(estate, gate, estate.b, later_bob, backdated, cites_history, cites_unsettled, addressed,
                           reissued, seconds=200)
        decisions = reasons(proposal)
        self.assertEqual(decisions[estate.b["frame_hash"]], ("duplicate", "already-accepted"))
        for frame in (cites_history, reissued):
            self.assertEqual(decisions[frame["frame_hash"]], ("accepted", "verified"))
        for frame in (later_bob, backdated, cites_unsettled, addressed):
            self.assertEqual(decisions[frame["frame_hash"]], ("quarantined", ROSTER_REVOKED))
        estate.commit(gate, proposal)
        catalog = {item["frame_hash"] for item in gate.catalog["frames"]}
        self.assertTrue({estate.a["frame_hash"], estate.b["frame_hash"], cites_history["frame_hash"],
                         reissued["frame_hash"]} <= catalog)
        self.assertFalse({later_bob["frame_hash"], backdated["frame_hash"], cites_unsettled["frame_hash"],
                          addressed["frame_hash"]} & catalog)
        self.assertIn(estate.b["frame_hash"], gate._active())

    def test_pending_conflict_of_a_removed_member_is_released_not_deadlocked(self):
        estate = Estate()
        mine = obj(estate, "carol", 20, ["shared/key"], audience=CURRENT)
        theirs = estate.object("bob", 21, ["shared/key"], stream=estate.stream("bob", "conflict"))
        gate = roster_gate(estate)
        partial = propose(estate, gate, mine, theirs, seconds=100)
        self.assertEqual(set(decision_map(partial).values()), {"conflict"})
        estate.commit(gate, partial)
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        with self.assertRaisesRegex(ValueError, "retain every unresolved"):
            propose(estate, gate, mine, seconds=200)
        released = propose(estate, gate, mine, theirs, seconds=200)
        self.assertEqual(reasons(released), {mine["frame_hash"]: ("accepted", "verified"),
                                             theirs["frame_hash"]: ("quarantined", ROSTER_REVOKED)})
        self.assertEqual(released["status"], "converged")
        estate.commit(gate, released)
        self.assertEqual(gate._pending, {})
        self.assertIn(theirs["frame_hash"], gate._retained)

    def test_pending_dependents_of_a_revoked_frame_are_released(self):
        estate = Estate()
        mine = obj(estate, "carol", 20, ["shared/key"], audience=CURRENT)
        theirs = estate.object("bob", 21, ["shared/key"], stream=estate.stream("bob", "conflict"))
        joined = obj(estate, "alice", 30, ["shared/key"], audience=CURRENT, stream=estate.stream("alice", "joined"),
                     sources=[mine, theirs])
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, mine, theirs, joined, seconds=100))
        self.assertEqual(set(gate._pending), {mine["frame_hash"], theirs["frame_hash"], joined["frame_hash"]})
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        released = propose(estate, gate, mine, theirs, joined, seconds=200)
        self.assertEqual(reasons(released), {mine["frame_hash"]: ("accepted", "verified"),
                                             theirs["frame_hash"]: ("quarantined", ROSTER_REVOKED),
                                             joined["frame_hash"]: ("quarantined", ROSTER_REVOKED)})
        estate.commit(gate, released)
        self.assertEqual(gate._pending, {})

    def test_accepted_frames_of_a_removed_member_still_conflict(self):
        estate = Estate()
        rival = obj(estate, "carol", 20, ["bob/key"], audience=CURRENT, stream=estate.stream("carol", "rival"))
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.b, seconds=100))
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        proposal = propose(estate, gate, rival, seconds=200)
        self.assertEqual(decision_map(proposal), {rival["frame_hash"]: "conflict"})
        self.assertEqual(proposal["status"], "partial")

    def test_revoked_ancestry_cannot_block_or_latch_fork_evidence(self):
        estate = Estate()
        left = estate.object("bob", 20, ["left/key"], previous=estate.b)
        right = estate.object("bob", 21, ["right/key"], previous=estate.b)
        first = obj(estate, "carol", 30, ["first/key"], audience=CURRENT, sources=[left])
        second = obj(estate, "carol", 31, ["second/key"], audience=CURRENT, stream=estate.stream("carol", "second"),
                     sources=[right])
        independent = obj(estate, "alice", 32, ["alice/key"], audience=CURRENT, stream=estate.a["stream_id"],
                          previous=estate.a)
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.a, estate.b, seconds=100))
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        proposal = propose(estate, gate, left, right, first, second, independent, seconds=200)
        self.assertEqual(reasons(proposal), {
            **{frame["frame_hash"]: ("quarantined", ROSTER_REVOKED) for frame in (left, right, first, second)},
            independent["frame_hash"]: ("accepted", "verified"),
        })
        estate.commit(gate, proposal)
        self.assertEqual(gate._forks, {})

    def test_demotion_to_viewer_revokes_future_mutation_only(self):
        estate = Estate(sealed_room=True)
        first = estate.object("carol", 20, ["carol/key"])
        later = estate.object("carol", 30, ["carol/key"], previous=first)
        secret = godd_slice(estate, "alice", 25, ["alice", "carol"], ["sealed/plan"],
                            stream=estate.stream("alice", "slices"))
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, first, secret, seconds=100))
        gate.accept_declaration(declare(estate, gate, with_roles(estate, gate, 150, carol="viewer"))["frame_hash"])
        # Proposed section 3.2: a viewer still in the room and the audience stays eligible for key release.
        self.assertTrue(key_release_eligible(gate.declaration, secret["payload"], estate.identities["carol"]))
        proposal = propose(estate, gate, first, later, seconds=200)
        self.assertEqual(reasons(proposal), {first["frame_hash"]: ("duplicate", "already-accepted"),
                                             later["frame_hash"]: ("quarantined", ROSTER_REVOKED)})

    def test_room_changes_govern_future_frames_and_key_release(self):
        estate = Estate(sealed_room=True)
        alice, bob, carol = (estate.identities[name] for name in ("alice", "bob", "carol"))
        secret = godd_slice(estate, "alice", 20, ["alice", "bob"], ["sealed/plan"],
                            stream=estate.stream("alice", "slices"))
        later_secret = godd_slice(estate, "alice", 40, ["alice", "bob"], ["sealed/later"],
                                  stream=secret["stream_id"], previous=secret)
        note = room_object(estate, "carol", 30, ["project/note"], room="project", audience=["alice", "carol"],
                           target="rooms/project/note.json", stream=estate.stream("carol", "project"))
        intruder = room_object(estate, "bob", 31, ["project/bob"], room="project", audience=["alice", "carol"],
                               target="rooms/project/bob.json", stream=estate.stream("bob", "project"))
        general = estate.object("bob", 32, ["bob/general"], previous=estate.b)
        gate = roster_gate(estate)
        first = propose(estate, gate, estate.b, secret, note, seconds=100)
        self.assertEqual(decision_map(first)[secret["frame_hash"]], "accepted")
        self.assertEqual(reasons(first)[note["frame_hash"]], ("quarantined", "invalid-candidate"))
        estate.commit(gate, first)
        self.assertTrue(key_release_eligible(gate.declaration, secret["payload"], bob))
        payload = roster(gate, 150)
        for room in payload["rooms"]:
            if room["id"] == "sealed":
                room["members"] = [value for value in room["members"] if value != bob]
        payload["rooms"] = sorted(payload["rooms"] + [
            {"id": "project", "area": "rooms/project", "members": sorted([alice, carol]), "access": "repository"}
        ], key=lambda item: item["id"])
        gate.accept_declaration(declare(estate, gate, payload)["frame_hash"])
        self.assertFalse(key_release_eligible(gate.declaration, secret["payload"], bob))
        self.assertTrue(key_release_eligible(gate.declaration, secret["payload"], alice))
        self.assertIn({"frame_hash": secret["frame_hash"], "payload_hash": secret["payload_hash"]},
                      gate.catalog["frames"])
        second = propose(estate, gate, note, intruder, later_secret, general, seconds=200)
        self.assertEqual(reasons(second), {
            note["frame_hash"]: ("accepted", "verified"),
            intruder["frame_hash"]: ("quarantined", "invalid-candidate"),
            later_secret["frame_hash"]: ("quarantined", ROSTER_REVOKED),
            general["frame_hash"]: ("accepted", "verified"),
        })
        estate.commit(gate, second)

    def test_authority_channel_switch_and_current_projection_at_a_declaration_head(self):
        estate = Estate()
        nas_genesis = receipt_genesis(estate, "nas-main", "nas-receipts")
        gate = roster_gate(estate)
        c1 = estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        github, manifest = receipt(estate, gate, estate.receipt_genesis, "github-main", 110, c1["payload_hash"])
        self.assertEqual(project(estate, gate, github, manifest)["status"], "current")
        d1 = declare(estate, gate, roster(gate, 150, channels=gate.declaration["channels"] + [NAS]))
        gate.accept_declaration(d1["frame_hash"])
        old, old_manifest = receipt(estate, gate, estate.receipt_genesis, "github-main", 155, c1["payload_hash"],
                                    previous=github, frame_head=c1["frame_hash"])
        with self.assertRaisesRegex(ValueError, "actual Mother Hive head"):
            project(estate, gate, old, old_manifest)
        nas, nas_manifest = receipt(estate, gate, nas_genesis, "nas-main", 160, c1["payload_hash"])
        self.assertEqual(nas_manifest["frame_head"], d1["frame_hash"])
        self.assertIn({"space": "rapp/1:wave", "hash": d1["frame_hash"]}, nas_manifest["artifacts"])
        self.assertEqual(project(estate, gate, nas, nas_manifest)["status"], "current")
        wrong, wrong_manifest = receipt(estate, gate, nas_genesis, "nas-main", 161, d1["payload_hash"], previous=nas)
        with self.assertRaisesRegex(ValueError, "unaccepted convergence"):
            project(estate, gate, wrong, wrong_manifest)
        d2 = declare(estate, gate, roster(gate, 170, channels=[dict(NAS, role="authority", writeback=True)],
                                          authority="nas-main"))
        gate.accept_declaration(d2["frame_hash"])
        self.assertEqual(gate.declaration["authority_channel_id"], "nas-main")
        retired, retired_manifest = receipt(estate, gate, estate.receipt_genesis, "github-main", 180,
                                            c1["payload_hash"], previous=github)
        with self.assertRaisesRegex(ValueError, "unknown channel"):
            project(estate, gate, retired, retired_manifest)
        current, current_manifest = receipt(estate, gate, nas_genesis, "nas-main", 181, c1["payload_hash"],
                                            previous=nas)
        self.assertEqual(project(estate, gate, current, current_manifest)["status"], "current")
        self.assertEqual(decision_map(propose(estate, gate, estate.b, seconds=200)),
                         {estate.b["frame_hash"]: "quarantined"})
        proposal = propose(estate, gate, estate.b, seconds=201, channels=["nas-main"])
        self.assertEqual(decision_map(proposal), {estate.b["frame_hash"]: "accepted"})
        self.assertEqual((proposal["base_head_frame_hash"], proposal["base_convergence_payload_hash"]),
                         (d2["frame_hash"], c1["payload_hash"]))
        estate.commit(gate, proposal)

    def test_a_retired_channel_is_never_current_even_after_a_cached_walk(self):
        estate = Estate()
        nas_genesis = receipt_genesis(estate, "nas-main", "nas-receipts")
        gate = roster_gate(estate)
        c1 = estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        d1 = declare(estate, gate, roster(gate, 150, channels=gate.declaration["channels"] + [NAS]))
        gate.accept_declaration(d1["frame_hash"])
        d2 = declare(estate, gate, roster(gate, 170, channels=[item for item in gate.declaration["channels"]
                                                                if item["id"] != "nas-main"]))
        # The owner signs a nas-main receipt at head D2, with the manifest derived on a twin verifier.
        twin = roster_gate(estate)
        twin.restore(d1["frame_hash"])
        twin.accept_declaration(d2["frame_hash"])
        late, manifest = receipt(estate, twin, nas_genesis, "nas-main", 175, c1["payload_hash"])
        fresh = roster_gate(estate)
        fresh.restore(d2["frame_hash"])
        with self.assertRaisesRegex(ValueError, "unknown channel"):
            project(estate, fresh, late, manifest)
        # A live verifier walks, and caches, the receipt chain while nas-main is still declared.
        with self.assertRaisesRegex(ValueError, "actual Mother Hive head"):
            project(estate, gate, late, manifest)
        self.assertIn(late["frame_hash"], gate._chains)
        gate.accept_declaration(d2["frame_hash"])
        self.assertEqual(gate.checkpoint(), fresh.checkpoint())
        with self.assertRaisesRegex(ValueError, "unknown channel in the roster in effect"):
            project(estate, gate, late, manifest)
        self.assertNotIn("nas-main", gate._receipt_heads)

    def test_convergence_base_commitments_across_a_declaration(self):
        estate = Estate()
        gate = roster_gate(estate)
        c1 = estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        catalog_hash = particle_hash(gate.catalog)
        d1 = declare(estate, gate, admit(estate, gate, 150, "outsider"))
        gate.accept_declaration(d1["frame_hash"])
        self.assertEqual(particle_hash(gate.catalog), catalog_hash)
        self.assertEqual(gate.checkpoint()["mother_head_frame_hash"], d1["frame_hash"])
        payload = propose(estate, gate, estate.b, seconds=200)
        self.assertEqual((payload["base_head_frame_hash"], payload["base_convergence_payload_hash"],
                          payload["base_catalog_hash"]), (d1["frame_hash"], c1["payload_hash"], catalog_hash))
        for field, value in (("base_convergence_payload_hash", None),
                             ("base_convergence_payload_hash", d1["payload_hash"]),
                             ("base_head_frame_hash", c1["frame_hash"]), ("base_catalog_hash", "a" * 64)):
            with self.subTest(field=field, value=value):
                wrong = copy.deepcopy(payload)
                wrong[field] = value
                with self.assertRaisesRegex(ValueError, "stale base"):
                    gate.accept_convergence(estate.convergence(gate, wrong)["frame_hash"])
        skipped = estate.frame("hive.convergence", estate.hive, payload, previous=c1)
        with self.assertRaisesRegex(ValueError, "competing Mother Hive successor"):
            gate.accept_convergence(skipped["frame_hash"])
        self.assertEqual(gate.head, d1)
        estate.commit(gate, payload)

    def test_declarations_before_the_first_convergence(self):
        estate = Estate()
        gate = roster_gate(estate)
        d1 = declare(estate, gate, admit(estate, gate, 50, "outsider"))
        gate.accept_declaration(d1["frame_hash"])
        d2 = declare(estate, gate, without(estate, gate, 60, "viewer"))
        gate.accept_declaration(d2["frame_hash"])
        with self.assertRaisesRegex(ValueError, "no accepted convergence"):
            gate.artifact_manifest()
        payload = propose(estate, gate, estate.a, seconds=100)
        self.assertEqual((payload["base_head_frame_hash"], payload["base_convergence_payload_hash"]),
                         (d2["frame_hash"], None))
        estate.commit(gate, payload)
        self.assertEqual(gate.artifact_manifest()["frame_head"], gate.head["frame_hash"])

    def test_a_no_op_declaration_only_advances_the_mother_head(self):
        estate = Estate()
        gate = roster_gate(estate)
        c1 = estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        before = gate.checkpoint()
        frame = declare(estate, gate, roster(gate, 150))
        gate.accept_declaration(frame["frame_hash"])
        after = gate.checkpoint()
        self.assertEqual({key: value for key, value in after.items() if key != "mother_head_frame_hash"},
                         {key: value for key, value in before.items() if key != "mother_head_frame_hash"})
        self.assertEqual(after["mother_head_frame_hash"], frame["frame_hash"])
        self.assertEqual(propose(estate, gate, estate.b, seconds=200)["base_convergence_payload_hash"],
                         c1["payload_hash"])

    def test_restore_replays_every_later_declaration(self):
        estate = Estate()
        joined = obj(estate, "outsider", 20, ["outsider/key"], audience=CURRENT)
        later_bob = estate.object("bob", 30, ["bob/key"], previous=estate.b)
        mine = obj(estate, "carol", 40, ["shared/key"], audience=CURRENT)
        theirs = estate.object("bob", 41, ["shared/key"], stream=estate.stream("bob", "conflict"))
        nas_genesis = receipt_genesis(estate, "nas-main", "nas-receipts")
        gate = roster_gate(estate)
        c1 = estate.commit(gate, propose(estate, gate, estate.a, estate.b, mine, theirs, seconds=100))
        payload = admit(estate, gate, 150, "outsider")
        payload["members"] = [item for item in payload["members"] if item["rappid"] != estate.identities["bob"]]
        for room in payload["rooms"]:
            room["members"] = [value for value in room["members"] if value != estate.identities["bob"]]
        gate.accept_declaration(declare(estate, gate, payload)["frame_hash"])
        second = propose(estate, gate, joined, later_bob, mine, theirs, seconds=200)
        self.assertEqual(reasons(second), {
            joined["frame_hash"]: ("accepted", "verified"), mine["frame_hash"]: ("accepted", "verified"),
            later_bob["frame_hash"]: ("quarantined", ROSTER_REVOKED),
            theirs["frame_hash"]: ("quarantined", ROSTER_REVOKED),
        })
        c2 = estate.commit(gate, second)
        gate.accept_declaration(declare(estate, gate, roster(gate, 250, channels=gate.declaration["channels"]
                                                               + [NAS]))["frame_hash"])
        head = gate.head
        manifest = gate.artifact_manifest()
        for resolver in (None, "retained"):
            with self.subTest(resolver=resolver):
                if resolver:
                    waves = {item["hash"] for item in manifest["artifacts"] if item["space"] == "rapp/1:wave"}
                    retained = {value: estate.chains[value] for value in waves}
                    fresh = roster_gate(estate, resolver=lambda value, retained=retained: retained[value])
                else:
                    fresh = roster_gate(estate)
                self.assertEqual(fresh.restore(head["frame_hash"]), gate.checkpoint())
                self.assertEqual(fresh.declaration, gate.declaration)
                self.assertEqual(fresh.catalog, gate.catalog)
                self.assertEqual(fresh.artifact_manifest(), manifest)
                self.assertEqual(fresh._stream_heads, gate._stream_heads)
                self.assertEqual(fresh._pending, gate._pending)
                self.assertEqual(len(fresh._rosters), 3)
        restored = roster_gate(estate)
        restored.restore(head["frame_hash"])
        frame, receipt_manifest = receipt(estate, restored, nas_genesis, "nas-main", 260, c1["payload_hash"])
        with self.assertRaisesRegex(ValueError, "must match convergence catalog"):
            project(estate, restored, frame, receipt_manifest)
        frame, receipt_manifest = receipt(estate, restored, nas_genesis, "nas-main", 261, c2["payload_hash"])
        self.assertEqual(project(estate, restored, frame, receipt_manifest)["status"], "current")

    def test_reconciliation_must_bind_the_declaration_head(self):
        estate = Estate()
        mine = estate.object("carol", 20, ["shared/key"])
        theirs = estate.object("bob", 21, ["shared/key"], stream=estate.stream("bob", "conflict"))
        gate = roster_gate(estate)
        partial = estate.commit(gate, propose(estate, gate, mine, theirs, seconds=100))
        stale = estate.reconcile([mine, theirs], seconds=120, base=partial)
        d1 = declare(estate, gate, admit(estate, gate, 150, "outsider"))
        gate.accept_declaration(d1["frame_hash"])
        fresh = estate.reconcile([mine, theirs], seconds=160, base=d1, stream=estate.stream("alice", "resolver-two"))
        resumed = roster_gate(estate)
        resumed.restore(d1["frame_hash"])
        proposal = propose(estate, resumed, mine, theirs, stale, fresh, seconds=200)
        self.assertEqual(reasons(proposal), {
            mine["frame_hash"]: ("superseded", "reconciled"), theirs["frame_hash"]: ("superseded", "reconciled"),
            stale["frame_hash"]: ("quarantined", "invalid-reconciliation"),
            fresh["frame_hash"]: ("accepted", "signed-reconciliation"),
        })
        estate.commit(resumed, proposal)

    def test_removed_member_dimension_head_survives_readmission(self):
        estate = Estate()
        second = estate.object("bob", 30, ["bob/key"], previous=estate.b)
        rival = estate.object("bob", 31, ["bob/rival"], previous=estate.b)
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.b, seconds=100))
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        revoked = propose(estate, gate, second, seconds=200)
        self.assertEqual(reasons(revoked), {second["frame_hash"]: ("quarantined", ROSTER_REVOKED)})
        estate.commit(gate, revoked)
        self.assertEqual(gate._stream_heads[estate.b["stream_id"]]["frame_hash"], estate.b["frame_hash"])
        gate.accept_declaration(declare(estate, gate, admit(estate, gate, 250, "bob"))["frame_hash"])
        readmitted = propose(estate, gate, second, seconds=300)
        self.assertEqual(decision_map(readmitted), {second["frame_hash"]: "accepted"})
        estate.commit(gate, readmitted)
        self.assertEqual(gate._stream_heads[estate.b["stream_id"]]["frame_hash"], second["frame_hash"])
        self.assertEqual(decision_map(propose(estate, gate, rival, seconds=301)), {rival["frame_hash"]: "quarantined"})

    def test_declaration_and_convergence_race_through_one_compare_and_swap(self):
        estate = Estate()
        gate = roster_gate(estate)
        declaration = declare(estate, gate, admit(estate, gate, 50, "outsider"))
        convergence = estate.convergence(gate, propose(estate, gate, estate.a, seconds=100))

        def attempt(frame):
            accept = gate.accept_declaration if frame["kind"] == "hive.declaration" else gate.accept_convergence
            try:
                accept(frame["frame_hash"])
                return True
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, [declaration, convergence])), [False, True])
        self.assertIn(gate.head["frame_hash"], {declaration["frame_hash"], convergence["frame_hash"]})
        self.assertEqual(len(gate._mother), 2)

    def test_resigned_variant_of_a_settled_frame_is_not_exempt(self):
        estate = Estate()
        successor = estate.object("alice", 20, ["alice/key"], previous=estate.a)
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        variant = copy.deepcopy(estate.a)
        variant["sig"] = estate.sign({key: value for key, value in variant.items() if key != "sig"}, "bob")
        estate.chains[successor["frame_hash"]] = [octets(variant), octets(successor)]
        proposal = propose(estate, gate, successor, seconds=200)
        self.assertEqual(reasons(proposal), {successor["frame_hash"]: ("quarantined", "invalid-candidate")})
        self.assertEqual(gate._frames[estate.a["frame_hash"]], estate.a)

    def test_unvalidated_payload_shape_cannot_enter_ancestry(self):
        estate = Estate()
        payload = copy.deepcopy(estate.b["payload"])
        payload["parents"] = [estate.a["frame_hash"]]
        widened = estate.frame("hive.object", estate.stream("bob", "widened"), payload, signer="bob")
        gate = roster_gate(estate)
        proposal = propose(estate, gate, estate.a, widened, seconds=100)
        self.assertEqual(reasons(proposal)[widened["frame_hash"]], ("quarantined", "invalid-candidate"))
        self.assertNotIn(widened["frame_hash"], gate._ancestry)


class RosterDeclarationRefusals(unittest.TestCase):
    """Proposal 0001 refusal vectors; a refused declaration leaves accepted state unchanged."""

    def refused(self, gate, frame, message):
        before = (gate.checkpoint(), gate.declaration, gate.head)
        with self.assertRaisesRegex(ValueError, message):
            gate.accept_declaration(frame["frame_hash"])
        self.assertEqual((gate.checkpoint(), gate.declaration, gate.head), before)

    def test_only_the_owner_signs_a_declaration(self):
        estate = Estate()
        gate = roster_gate(estate)
        for seconds, signer in ((50, "bob"), (51, "viewer"), (52, "outsider")):
            with self.subTest(signer=signer):
                frame = declare(estate, gate, admit(estate, gate, seconds, "outsider"), signer=signer)
                self.refused(gate, frame, "owner authorization mismatch")
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 60, "bob"))["frame_hash"])
        self.refused(gate, declare(estate, gate, admit(estate, gate, 70, "bob"), signer="bob"),
                     "owner authorization mismatch")

    def test_revoked_owner_key_cannot_declare(self):
        estate = Estate()
        registry = estate.registry()
        tombstone = {"type": "tombstone", "rappid": estate.identities["alice"], "revoked_utc": stamp(120)}
        tombstone["sig"] = estate.sign(tombstone)
        registry["entries"].append(tombstone)
        registry["sig"] = estate.sign({key: value for key, value in registry.items() if key != "sig"})
        gate = roster_gate(estate, registry)
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        self.refused(gate, declare(estate, gate, without(estate, gate, 150, "bob")), "signer is revoked")
        # RAPP/1 section 14: a tombstone gates on the artifact's own utc; the Mother head bounds it below.
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 110, "bob"))["frame_hash"])

    def test_hive_world_policy_and_schema_are_immutable(self):
        estate = Estate()
        gate = roster_gate(estate)
        foreign = roster(gate, 50)
        foreign["hive_rappid"] = R.mint_rappid("example", "other-hive", estate.spki["alice"])
        world = roster(gate, 51)
        world["world_id"] = "another-world"
        policy = roster(gate, 52)
        policy["policy"]["default_godd_scope"] = "hive-shared"
        schema = roster(gate, 53)
        schema["schema"] = "rapp-hive/2-declaration"
        extra = roster(gate, 54)
        extra["removed_members"] = []
        for payload, message in ((foreign, "stream binding mismatch"), (world, "world_id is immutable"),
                                 (policy, "must be local-only"), (schema, "unexpected payload schema"),
                                 (extra, "expected keys")):
            with self.subTest(message=message):
                self.refused(gate, declare(estate, gate, payload), message)

    def test_the_owner_is_unique_and_unchanged(self):
        estate = Estate()
        gate = roster_gate(estate)
        cases = (
            (with_roles(estate, gate, 50, alice="member", bob="owner"), "succession \\(gap G6\\)"),
            (with_roles(estate, gate, 51, alice="member"), "exactly one owner"),
            (with_roles(estate, gate, 52, bob="owner"), "exactly one owner"),
            (without(estate, gate, 53, "alice"), "exactly one owner"),
            (with_roles(estate, gate, 54, alice="viewer", carol="owner"), "succession \\(gap G6\\)"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                self.refused(gate, declare(estate, gate, payload), message)

    def test_the_roster_keeps_the_closed_declaration_grammar(self):
        estate = Estate()
        gate = roster_gate(estate)
        unsorted = roster(gate, 50)
        unsorted["members"].reverse()
        duplicate = roster(gate, 51)
        duplicate["members"].append(copy.deepcopy(duplicate["members"][-1]))
        stranger = without(estate, gate, 52, "bob")
        stranger["rooms"][0]["members"] = sorted(stranger["rooms"][0]["members"] + [estate.identities["bob"]])
        authorities = roster(gate, 53, channels=gate.declaration["channels"] + [dict(NAS, role="authority",
                                                                                     writeback=True)])
        channels = roster(gate, 54)
        channels["channels"] = [NAS] + channels["channels"]
        for payload, message in ((unsorted, "unique and sorted by rappid"), (duplicate, "unique and sorted by rappid"),
                                 (stranger, "contains a non-member"),
                                 (authorities, "exactly one named authority channel"),
                                 (channels, "unique and sorted by id")):
            with self.subTest(message=message):
                self.refused(gate, declare(estate, gate, payload), message)

    def test_declared_rooms_persist_with_their_area_and_access(self):
        estate = Estate(sealed_room=True)
        gate = roster_gate(estate)
        dropped = roster(gate, 50)
        dropped["rooms"] = [room for room in dropped["rooms"] if room["id"] != "sealed"]
        moved = roster(gate, 51)
        opened = roster(gate, 52)
        next(room for room in moved["rooms"] if room["id"] == "sealed")["area"] = "rooms/elsewhere"
        next(room for room in opened["rooms"] if room["id"] == "sealed")["access"] = "repository"
        for payload in (dropped, moved, opened):
            with self.subTest(rooms=[room["id"] for room in payload["rooms"]]):
                self.refused(gate, declare(estate, gate, payload), "persists with its area and access")
        retired = roster(gate, 53)
        next(room for room in retired["rooms"] if room["id"] == "sealed")["members"] = [estate.identities["alice"]]
        gate.accept_declaration(declare(estate, gate, retired)["frame_hash"])

    def test_a_declaration_is_the_single_next_mother_frame(self):
        estate = Estate()
        gate = roster_gate(estate)
        stale = declare(estate, gate, admit(estate, gate, 50, "outsider"))
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        self.refused(gate, stale, "stale base or competing")
        first = declare(estate, gate, admit(estate, gate, 150, "outsider"))
        second = declare(estate, gate, without(estate, gate, 151, "bob"))
        rival = estate.convergence(gate, propose(estate, gate, estate.b, seconds=152))
        gate.accept_declaration(first["frame_hash"])
        self.refused(gate, second, "stale base or competing")
        with self.assertRaisesRegex(ValueError, "stale base or competing"):
            gate.accept_convergence(rival["frame_hash"])
        self.refused(gate, first, "Mother Hive frame replay")
        estate.commit(gate, propose(estate, gate, estate.b, seconds=200))
        self.refused(gate, first, "stale base or competing")
        self.refused(gate, estate.mother, "stale base or competing")

    def test_an_old_declaration_payload_cannot_be_replayed(self):
        estate = Estate()
        gate = roster_gate(estate)
        first = declare(estate, gate, admit(estate, gate, 50, "outsider"))
        gate.accept_declaration(first["frame_hash"])
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        self.refused(gate, declare(estate, gate, first["payload"]), "utc < head utc")
        self.refused(gate, declare(estate, gate, estate.declaration), "utc < head utc")
        restamped = R.build_frame("hive.declaration", estate.hive, gate.head["seq"] + 1, stamp(150),
                                  first["payload"], gate.head["payload_hash"])
        restamped["sig"] = estate.sign({key: value for key, value in restamped.items() if key != "sig"})
        estate.chains[restamped["frame_hash"]] = estate.chains[gate.head["frame_hash"]] + [octets(restamped)]
        self.refused(gate, restamped, "payload/envelope time mismatch")

    def test_declaration_time_is_envelope_time_and_strictly_after_the_head(self):
        estate = Estate()
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        payload = admit(estate, gate, 150, "outsider")
        mismatch = R.build_frame("hive.declaration", estate.hive, gate.head["seq"] + 1, stamp(151), payload,
                                 gate.head["payload_hash"])
        mismatch["sig"] = estate.sign({key: value for key, value in mismatch.items() if key != "sig"})
        estate.chains[mismatch["frame_hash"]] = estate.chains[gate.head["frame_hash"]] + [octets(mismatch)]
        self.refused(gate, mismatch, "payload/envelope time mismatch")
        self.refused(gate, declare(estate, gate, admit(estate, gate, 90, "outsider")), "utc < head utc")
        self.refused(gate, declare(estate, gate, admit(estate, gate, 100, "outsider")), "strictly after")
        gate.accept_declaration(declare(estate, gate, admit(estate, gate, 101, "outsider"))["frame_hash"])

    def test_a_declaration_is_never_a_catalog_candidate(self):
        for proposal_mode in (False, True):
            with self.subTest(proposal_mode=proposal_mode):
                estate = Estate()
                stray = estate.frame("hive.declaration", estate.stream("alice", "stray"), estate.declaration)
                gate = roster_gate(estate) if proposal_mode else estate.gate()
                offered = [estate.a, estate.mother, stray]
                if proposal_mode:
                    later = declare(estate, gate, admit(estate, gate, 50, "outsider"))
                    gate.accept_declaration(later["frame_hash"])
                    offered.append(later)
                proposal = gate.preview_convergence(summaries(estate, *offered), stamp(100))
                self.assertEqual(decision_map(proposal), {
                    estate.a["frame_hash"]: "accepted",
                    **{frame["frame_hash"]: "quarantined" for frame in offered[1:]},
                })
                estate.commit(gate, proposal)
                self.assertEqual([item["frame_hash"] for item in gate.catalog["frames"]], [estate.a["frame_hash"]])
                if proposal_mode:
                    pending = declare(estate, gate, roster(gate, 150))
                    with self.assertRaisesRegex(ValueError, "wrong Mother Hive kind"):
                        gate.accept_convergence(pending["frame_hash"])
                    convergence = estate.convergence(gate, propose(estate, gate, estate.b, seconds=160))
                    with self.assertRaisesRegex(ValueError, "wrong Mother Hive kind"):
                        gate.accept_declaration(convergence["frame_hash"])


def admission_registries(estate):
    """An outsider's frame, and registries that leave out or register its key and dimension-stream genesis."""
    joined = estate.object("outsider", 20, ["outsider/key"])
    outsider = estate.identities["outsider"]

    def registry(sequence, *, admitted):
        document = estate.registry(sequence)
        if not admitted:
            document["entries"] = [
                entry for entry in document["entries"]
                if outsider != entry.get("rappid") and entry.get("stream_id") != joined["stream_id"]
            ]
            document["sig"] = estate.sign({key: value for key, value in document.items() if key != "sig"})
        return document

    return joined, registry


class RegistrySideOfRosterChanges(unittest.TestCase):
    """Proposal 0001: the roster names identities; the RAPP/1 section 13 registry verifies their keys and streams."""

    def test_registry_first_admission(self):
        estate = Estate()
        joined, registry = admission_registries(estate)
        # The owner's verifier already holds a registry with the identity's key and stream genesis (section 3 item 13).
        gate = roster_gate(estate, registry(9, admitted=True))
        estate.commit(gate, propose(estate, gate, estate.a, seconds=100))
        gate.accept_declaration(declare(estate, gate, admit(estate, gate, 150, "outsider"))["frame_hash"])
        proposal = propose(estate, gate, joined, seconds=200)
        self.assertEqual(reasons(proposal), {joined["frame_hash"]: ("accepted", "verified")})
        estate.commit(gate, proposal)
        restored = roster_gate(estate, registry(9, admitted=True)).restore(gate.head["frame_hash"])
        self.assertEqual(restored, gate.checkpoint())

    def test_registry_refresh_across_an_admission(self):
        estate = Estate()
        joined, registry = admission_registries(estate)
        before = roster_gate(estate, registry(8, admitted=False))
        estate.commit(before, propose(estate, before, estate.a, seconds=100))
        before.accept_declaration(declare(estate, before, admit(estate, before, 150, "outsider"))["frame_hash"])
        # The roster names the identity, but without its registry key and stream genesis its frames cannot verify.
        self.assertEqual(reasons(propose(estate, before, joined, seconds=200)),
                         {joined["frame_hash"]: ("quarantined", "invalid-candidate")})
        # No convergence records that quarantine, so a refresh still restores: a higher owner-signed registry, a
        # fresh gate, and restore() of the history with the declaration.
        authority = estate.authority(registry(9, admitted=True), minimum_registry_seq=before.registry.sequence)
        after = HiveAcceptance(authority, estate.hive, lambda address: estate.chains[address],
                               roster_declarations=True)
        restored = after.restore(before.head["frame_hash"])
        self.assertEqual(restored["registry_seq"], 9)
        self.assertEqual(without_registry(restored), without_registry(before.checkpoint()))
        self.assertEqual(after.declaration, before.declaration)
        proposal = propose(estate, after, joined, seconds=200)
        self.assertEqual(reasons(proposal), {joined["frame_hash"]: ("accepted", "verified")})
        estate.commit(after, proposal)

    def test_a_recorded_registry_quarantine_makes_a_later_refresh_fail_closed(self):
        estate = Estate()
        joined, registry = admission_registries(estate)
        before = roster_gate(estate, registry(8, admitted=False))
        estate.commit(before, propose(estate, before, estate.a, seconds=100))
        before.accept_declaration(declare(estate, before, admit(estate, before, 150, "outsider"))["frame_hash"])
        # The owner signs a convergence that records the quarantine caused only by the missing registry entries.
        recorded = propose(estate, before, joined, seconds=200)
        self.assertEqual(reasons(recorded), {joined["frame_hash"]: ("quarantined", "invalid-candidate")})
        estate.commit(before, recorded)
        # A registry that registers the key re-derives a different decision for that history: restore() fails
        # closed and latches, so the owner must never record such a quarantine (section 3 item 13).
        authority = estate.authority(registry(9, admitted=True), minimum_registry_seq=before.registry.sequence)
        after = HiveAcceptance(authority, estate.hive, lambda address: estate.chains[address],
                               roster_declarations=True)
        with self.assertRaisesRegex(ValueError, "decisions differ"):
            after.restore(before.head["frame_hash"])
        with self.assertRaisesRegex(ValueError, "failed history recovery"):
            after.checkpoint()
        # The verifier that recorded it, and any other verifier on the old registry, still restores the history.
        self.assertEqual(roster_gate(estate, registry(8, admitted=False)).restore(before.head["frame_hash"]),
                         before.checkpoint())

    def test_removal_keeps_the_removed_members_registry_key(self):
        estate = Estate()
        bob = estate.identities["bob"]
        late = estate.object("bob", 160, ["bob/late"], previous=estate.b)
        gate = roster_gate(estate)
        estate.commit(gate, propose(estate, gate, estate.a, estate.b, seconds=100))
        gate.accept_declaration(declare(estate, gate, without(estate, gate, 150, "bob"))["frame_hash"])
        head = gate.head["frame_hash"]

        def resigned(entry=None, *, deprecate=None):
            document = estate.registry(9)
            for item in document["entries"]:
                if item["type"] == "spki" and item["rappid"] == deprecate:
                    item["deprecated"] = True
            if entry is not None:
                document["entries"].append(entry)
            document["sig"] = estate.sign({key: value for key, value in document.items() if key != "sig"})
            return roster_gate(estate, document)

        # A deprecated key is retired for history too (RAPP/1 section 13.3): re-verification fails closed.
        retired = resigned(deprecate=bob)
        with self.assertRaisesRegex(ValueError, "decisions differ"):
            retired.restore(head)
        with self.assertRaisesRegex(ValueError, "failed history recovery"):
            retired.checkpoint()
        # A compromise tombstone keeps accepted history verifiable and refuses later signatures.
        tombstone = {"type": "tombstone", "rappid": bob, "revoked_utc": stamp(155)}
        tombstone["sig"] = estate.sign(tombstone)
        revoked = resigned(tombstone)
        self.assertEqual(without_registry(revoked.restore(head)), without_registry(gate.checkpoint()))
        self.assertEqual(reasons(propose(estate, gate, late, seconds=200)),
                         {late["frame_hash"]: ("quarantined", ROSTER_REVOKED)})
        self.assertEqual(reasons(propose(estate, revoked, late, seconds=200)),
                         {late["frame_hash"]: ("quarantined", "invalid-candidate")})


class _ProposalModeGate(HiveAcceptance):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, roster_declarations=True, **kwargs)


class ProposalModeReplaysAuthenticatedVectors(A.AuthenticatedVectors):
    """Conservative extension: every existing authenticated vector passes unchanged with the opt-in."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(A, "HiveAcceptance", _ProposalModeGate)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_vectors_really_run_in_proposal_mode(self):
        self.assertIs(A.Estate().gate()._roster_declarations, True)


def run():
    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(case)
        for case in (DefaultGateRefusesLaterDeclarations, RosterDeclarationVectors, RosterDeclarationRefusals,
                     RegistrySideOfRosterChanges, ProposalModeReplaysAuthenticatedVectors)
    ])
    return unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == "__main__":
    raise SystemExit(0 if run().wasSuccessful() else 1)
