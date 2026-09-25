"""Authenticated, serialized rapp-hive/1 acceptance over immutable frame bytes.

The caller supplies a fresh section-13 registry, an out-of-band owner anchor,
and a resolver returning the complete registered-genesis-to-tip byte sequence.
No candidate summary, shape-validation result, or caller-supplied catalog is a
trust input. Persist checkpoint() atomically with the accepted artifacts.

The default registry authority is direct-owner and fails closed on succession.
RAPP/1 section 13.2 owner tenure is verified only when the caller explicitly
selects succession="rapp1-13.2" and supplies a trusted tombstone issuance
resolver; the pinned RAPP/1 registry reference (imported only then) decides
every section-13 entry, lifecycle signature, and time-scoped key retirement.
Under succession, checkpoint() also carries the retained registry state that
the caller passes back as retained_registry.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import threading
from pathlib import Path

import rapp as R
import rapp_hive as H
from rapp_profile import bounded_int, canonical_object, exact_keys, hex64, particle_hash, require, utc


CATALOG_KINDS = {"hive.object", "hive.godd-slice", "hive.reconciliation"}
FORK_REASONS = {"stream-fork", "fork-ancestor"}
SUCCESSION = "rapp1-13.2"
OWNER_SUCCESSION_CASES = {"rotation", "compromise"}
LIFECYCLE_TYPES = {"re-anchor", "tombstone"}
RETAINED_REGISTRY_KEYS = {"registry_seq", "registry_hash", "owner_lineage", "registry_lifecycle"}
RETAINED_LIMIT = 65536
LIVE_UNTIL = "9999-12-31T23:59:59.999Z"


def _retained_registry(value) -> dict:
    """A consumer's persisted registry state: the registry members of a succession checkpoint()."""
    exact_keys(value, RETAINED_REGISTRY_KEYS, "retained registry state")
    lineage, lifecycle = value["owner_lineage"], value["registry_lifecycle"]
    require(isinstance(lineage, (list, tuple)) and 1 <= len(lineage) <= RETAINED_LIMIT,
            "retained registry state.owner_lineage: expected a nonempty bounded array")
    require(isinstance(lifecycle, (list, tuple)) and len(lifecycle) <= RETAINED_LIMIT,
            "retained registry state.registry_lifecycle: expected a bounded array")
    owners = tuple(H.rappid(item, "retained registry state.owner_lineage") for item in lineage)
    require(len(set(owners)) == len(owners), "retained registry state.owner_lineage: repeated owner")
    hashes = tuple(hex64(item, "retained registry state.registry_lifecycle") for item in lifecycle)
    require(list(hashes) == sorted(set(hashes)),
            "retained registry state.registry_lifecycle: expected sorted unique hashes")
    return {
        "registry_seq": bounded_int(value["registry_seq"], "retained registry state.registry_seq", 0, H.UINT53_MAX),
        "registry_hash": hex64(value["registry_hash"], "retained registry state.registry_hash"),
        "owner_lineage": owners,
        "registry_lifecycle": hashes,
    }


class RegistryAuthority:
    """Direct-owner section-13 verification; succession fails closed unless explicitly enabled."""

    def __init__(
        self,
        registry_bytes: bytes,
        *,
        owner_rappid: str,
        owner_spki_der: bytes,
        minimum_registry_seq: int = 0,
        same_sequence_hash: str | None = None,
        succession: str | None = None,
        tombstone_issued_at=None,
        retained_registry=None,
    ):
        require(succession is None or succession == SUCCESSION, "registry: unsupported succession mode")
        retained = None
        if succession is None:
            require(tombstone_issued_at is None and retained_registry is None,
                    "registry: tombstone issuance and retained registry state require explicit succession verification")
        else:
            require(callable(tombstone_issued_at),
                    "registry: succession verification requires a trusted tombstone issuance resolver")
            # One persisted state: the floor, its commitment, the owner lineage, and the lifecycle travel together.
            require(type(minimum_registry_seq) is int and minimum_registry_seq == 0 and same_sequence_hash is None,
                    "registry: under succession the persisted floor and hash travel only in retained_registry")
            if retained_registry is not None:
                retained = _retained_registry(retained_registry)
                minimum_registry_seq, same_sequence_hash = retained["registry_seq"], retained["registry_hash"]
        self.succession = succession
        self._reference = None
        self._lifecycle = None
        require(isinstance(registry_bytes, bytes), "registry: expected bytes")
        document = canonical_object(R._strict_json(registry_bytes), "registry")
        require(document.get("schema") == "rapp/1-registry", "registry: wrong schema")
        self.sequence = bounded_int(document.get("registry_seq"), "registry.registry_seq", 0, H.UINT53_MAX)
        bounded_int(minimum_registry_seq, "registry minimum sequence", 0, H.UINT53_MAX)
        require(self.sequence >= minimum_registry_seq, "registry: rollback")
        H.rappid(owner_rappid, "out-of-band owner")
        unsigned = {key: value for key, value in document.items() if key != "sig"}
        if succession is None:
            ok, why = R.verify_detached_jws(unsigned, document.get("sig"), owner_spki_der, owner_rappid)
            require(ok, f"registry: signature refused: {why}")
        else:
            reference, lineage, issued = self._verify_succession(document, owner_rappid, owner_spki_der,
                                                                 minimum_registry_seq, tombstone_issued_at)
        self.commitment = particle_hash(unsigned)
        if self.sequence == minimum_registry_seq:
            require(minimum_registry_seq == 0 or same_sequence_hash is not None,
                    "registry: persisted same-sequence hash is required")
            if same_sequence_hash is not None:
                require(self.commitment == hex64(same_sequence_hash, "registry checkpoint"),
                        "registry: same-sequence fork")
        self.owner = owner_rappid
        self.anchor = owner_rappid
        self.owner_lineage = (owner_rappid,)
        self._document = document
        self._keys = {}
        self._genesis = {}
        self._kinds = {}
        self._revoked = {}
        entries = document.get("entries")
        require(isinstance(entries, list), "registry.entries: expected array")
        if succession is not None:
            self._index_succession(reference, lineage, issued, retained)
            return
        owners, profiles = [], []
        for entry in entries:
            require(isinstance(entry, dict), "registry.entries: expected object")
            entry_type = entry.get("type")
            if "deprecated" in entry:
                H.boolean(entry["deprecated"], "registry deprecated flag")
            if entry_type == "re-anchor":
                raise ValueError("registry: succession requires a full section-13 tenure verifier")
            if entry_type == "tombstone":
                exact_keys(entry, {"type", "rappid", "revoked_utc", "sig"}, "registry tombstone")
                identity = H.rappid(entry["rappid"], "registry tombstone.rappid")
                utc(entry["revoked_utc"], "registry tombstone.revoked_utc")
                ok, why = R.verify_detached_jws(
                    {key: value for key, value in entry.items() if key != "sig"},
                    entry["sig"], owner_spki_der, owner_rappid,
                )
                require(ok, f"registry: tombstone signature refused: {why}")
                self._revoked[identity] = min(entry["revoked_utc"], self._revoked.get(identity, entry["revoked_utc"]))
                continue
            if entry.get("deprecated") is True:
                continue
            if entry_type == "estate_owner":
                exact_keys(entry, {"type", "rappid"}, "registry owner")
                owners.append(entry["rappid"])
            elif entry_type == "protocol" and entry.get("name") == "rapp-hive/1":
                exact_keys(entry, {"type", "name", "spec_repo", "spec_path", "spec_hash", "deprecated"},
                           "registry profile")
                profiles.append(entry)
            elif entry_type == "kind":
                exact_keys(entry, {"type", "kind", "family", "deprecated"}, "registry kind")
                H.text(entry["kind"], "registry kind.kind", maximum=128)
                H.text(entry["family"], "registry kind.family", maximum=128)
                require(entry["kind"] not in self._kinds, "registry: ambiguous kind")
                self._kinds[entry["kind"]] = entry["family"]
            elif entry_type == "genesis":
                require({"type", "stream_id", "frame_hash", "deprecated"} <= set(entry),
                        "registry: incomplete genesis entry")
                stream_id = H.text(entry["stream_id"], "registry stream", maximum=512)
                require(stream_id not in self._genesis, "registry: ambiguous active genesis")
                self._genesis[stream_id] = hex64(entry["frame_hash"], "registry genesis")
            elif entry_type == "spki":
                exact_keys(entry, {"type", "rappid", "spki_der_b64", "deprecated"}, "registry spki")
                identity = H.rappid(entry["rappid"], "registry spki.rappid")
                require(identity not in self._keys, "registry: ambiguous active key")
                try:
                    key = base64.b64decode(entry["spki_der_b64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise ValueError("registry: invalid SPKI encoding") from error
                require(R.Hb("rapp/1:rappid", key) == R.rappid_parts(identity)["hash"],
                        "registry: SPKI/RAPPID binding mismatch")
                self._keys[identity] = key
        require(owners == [owner_rappid], "registry: estate owner differs from out-of-band anchor")
        require(self._keys.get(owner_rappid) == owner_spki_der, "registry: owner SPKI is not active")
        require(len(profiles) == 1, "registry: exactly one active Hive profile is required")
        spec_hash = hashlib.sha256((Path(__file__).resolve().parents[1] / "SPEC.md").read_bytes()).hexdigest()
        require(profiles[0]["spec_hash"] == spec_hash, "registry: Hive profile specification hash mismatch")
        require(all(self._kinds.get(kind) == "body" for kind in H.KIND_SCHEMAS),
                "registry: exact Hive kinds must be registered in the body family")

    def _verify_succession(self, document, anchor, anchor_spki_der, minimum_registry_seq, tombstone_issued_at):
        """RAPP/1 section 13.2 tenure through the pinned reference; an anchor extends only by rotation."""
        # Imported only here, so the default direct-owner path runs without the registry reference.
        import rapp_registry as REG

        require(isinstance(anchor_spki_der, bytes)
                and R.Hb("rapp/1:rappid", anchor_spki_der) == R.rappid_parts(anchor)["hash"],
                "registry: out-of-band anchor SPKI does not bind the anchor RAPPID")
        try:
            reference = REG.Registry(document.get("entries"))
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"registry: section-13 entry refused: {error}") from error
        predecessors = {record["new_rappid"]: record for record in reference.reanchors}
        lineage, transitions = [reference.estate_owner], []
        while lineage[-1] in predecessors:
            require(len(transitions) < len(reference.reanchors), "registry: re-anchor succession cycle")
            record = predecessors[lineage[-1]]
            require(record["case"] in OWNER_SUCCESSION_CASES,
                    "registry: owner succession case is not verifiable by this reference")
            transitions.append(record)
            lineage.append(record["old_rappid"])
        require(anchor in lineage, "registry: estate owner does not descend from the out-of-band anchor")
        # RAPP/1 sections 13.1-13.2: root-key compromise cannot be expressed inside the registry it signs.
        require(all(record["case"] == "rotation" for record in transitions[:lineage.index(anchor)]),
                "registry: an out-of-band anchor extends only through signed rotation; "
                "compromise recovery requires a new out-of-band anchor")
        require(reference.spki_der(anchor) == anchor_spki_der,
                "registry: out-of-band anchor SPKI is not the registered anchor key")
        issued = {}

        def issued_at(entry_hash):
            try:
                issued[entry_hash] = tombstone_issued_at(entry_hash)
            except (LookupError, OSError, TypeError, ValueError) as error:
                raise ValueError(f"trusted issuance resolver refused: {error}") from error
            return issued[entry_hash]

        status, loaded, why = REG.load_document(
            document, entries_member="entries", trust_anchor=reference.estate_owner,
            persisted_seq=minimum_registry_seq, tombstone_issued_at=issued_at,
        )
        require(status == "verified" and loaded is not None, f"registry: section-13 refusal: {why}")
        ok, why = loaded._signer_acceptable(loaded.estate_owner, LIVE_UNTIL, match_key_aliases=True)
        require(ok, f"registry: current estate owner key is not live: {why}")
        return loaded, tuple(reversed(lineage)), issued

    def _index_succession(self, reference, lineage, issued, retained):
        entries = reference.entries
        lifecycle = {particle_hash(entry) for entry in entries if entry["type"] in LIFECYCLE_TYPES}
        if retained is None:
            # A predecessor anchor is exactly what a leaked retired key could replay: require remembered state.
            require(reference.estate_owner == self.anchor,
                    "registry: an out-of-band anchor that is not the current estate owner "
                    "requires the retained registry state")
        else:
            require(lineage[:len(retained["owner_lineage"])] == retained["owner_lineage"],
                    "registry: owner succession rewrites retained history")
            require(set(retained["registry_lifecycle"]) <= lifecycle,
                    "registry: a retained succession or revocation record was dropped or rewritten")
            appended = lifecycle - set(retained["registry_lifecycle"])
            compromises = [record for record in reference.reanchors
                           if record["case"] == "compromise" and particle_hash(record) in appended]
            if compromises:
                # RAPP/1 section 6.3: a snapshot cannot prove one append; the retained state can, one step at a time.
                require(self.sequence == retained["registry_seq"] + 1,
                        "registry: a new compromise re-anchor needs same-append evidence; "
                        "verify each intermediate registry in sequence")
                for record in compromises:
                    require(any(entry["type"] == "tombstone" and entry["rappid"] == record["old_rappid"]
                                and particle_hash(entry) in appended for entry in entries),
                            "registry: a compromise re-anchor and its tombstone must be registered in the same append")
        times = [record["utc"] for record in reference.reanchors] + list(issued.values())
        self.epoch = max(times) if times else None
        self._lifecycle = tuple(sorted(lifecycle))
        self.owner_lineage = lineage
        self._reference = reference
        self.owner = reference.estate_owner
        for entry in reference.entries:
            if entry["type"] == "spki":
                self._keys[entry["rappid"]] = reference.spki_der(entry["rappid"])
        self._revoked = dict(reference.tombstones)
        self._kinds = {kind: entry["family"] for kind, entry in reference.kinds.items() if not entry["deprecated"]}
        for stream_id in reference.genesis:
            registered = reference.registered_genesis(stream_id)
            if registered is not None:
                self._genesis[stream_id] = registered["frame_hash"]
        profiles = [entry for entry in reference.entries
                    if entry["type"] == "protocol" and entry["name"] == "rapp-hive/1" and not entry["deprecated"]]
        require(len(profiles) == 1, "registry: exactly one active Hive profile is required")
        spec_hash = hashlib.sha256((Path(__file__).resolve().parents[1] / "SPEC.md").read_bytes()).hexdigest()
        require(profiles[0]["spec_hash"] == spec_hash, "registry: Hive profile specification hash mismatch")
        require(all(self._kinds.get(kind) == "body" for kind in H.KIND_SCHEMAS),
                "registry: exact Hive kinds must be registered in the body family")

    def owner_at(self, stamp: str) -> str:
        """The estate owner in effect at an artifact's authenticated time (RAPP/1 section 13.2)."""
        if self._reference is None:
            return self.owner
        utc(stamp, "owner tenure time")
        return self._reference.owner_at(stamp)

    @property
    def lifecycle(self) -> tuple:
        """Sorted particle hashes of every re-anchor and tombstone entry in this registry."""
        if self._lifecycle is None:
            self._lifecycle = tuple(sorted({particle_hash(entry) for entry in self._document["entries"]
                                            if entry.get("type") in LIFECYCLE_TYPES}))
        return self._lifecycle

    @property
    def retained_registry(self) -> dict:
        """The registry state a consumer persists and passes back as retained_registry under succession."""
        return {"registry_seq": self.sequence, "registry_hash": self.commitment,
                "owner_lineage": list(self.owner_lineage), "registry_lifecycle": list(self.lifecycle)}

    def _verify_tenured_signature(self, unsigned: dict, signature: str, expected_signer: str | None):
        try:
            signer = R.parse_detached_jws(signature)[0]["kid"]
            stamp = unsigned.get("utc", unsigned.get("created_utc"))
            utc(stamp, "signed artifact time")
            # Retirement is matched by key tail, so renaming a RAPPID cannot revive a retired SPKI.
            ok, why = self._reference._signer_acceptable(signer, stamp, match_key_aliases=True)
            require(ok, f"signer refused: {why}")
            return R.verify_detached_jws(unsigned, signature, self._reference.spki_der(signer), expected_signer)
        except (ValueError, TypeError) as error:
            return False, str(error)

    def verify_signature(self, unsigned: dict, signature: str, expected_signer: str | None = None):
        if self._reference is not None:
            return self._verify_tenured_signature(unsigned, signature, expected_signer)
        try:
            signer = R.parse_detached_jws(signature)[0]["kid"]
            require(signer in self._keys, "signer has no active registry SPKI")
            stamp = unsigned.get("utc", unsigned.get("created_utc"))
            utc(stamp, "signed artifact time")
            require(signer not in self._revoked or stamp < self._revoked[signer], "signer is revoked")
            return R.verify_detached_jws(unsigned, signature, self._keys[signer], expected_signer)
        except (ValueError, TypeError) as error:
            return False, str(error)


class HiveAcceptance:
    """One local Mother Hive compare-and-swap gate, not a payload-shape validator."""

    def __init__(self, registry: RegistryAuthority, hive_rappid: str, resolve_chain):
        require(isinstance(registry, RegistryAuthority), "authenticated registry authority is required")
        require(callable(resolve_chain), "frame byte resolver is required")
        self.registry = registry
        self._resolve = resolve_chain
        self._lock = threading.RLock()
        self._hive = H.rappid(hive_rappid, "Mother Hive")
        self._declaration = None
        self._chains = {}
        self._frames = {}
        self._ancestry = {}
        self._accepted = {}
        self._settled = set()
        self._pending = {}
        self._retained = {}
        self._stream_heads = {}
        self._forks = {}
        self._receipt_heads = {}
        self._convergences = {}
        self._catalogs = {}
        self._restore_failed = False
        require(self._hive in registry._genesis, "Mother Hive: no registered genesis")
        genesis = self._chain(registry._genesis[self._hive])
        require(len(genesis) == 1 and genesis[0]["kind"] == "hive.declaration",
                "Mother Hive: registered genesis must be a declaration")
        self._head = genesis[0]
        self._mother = [self._head["frame_hash"]]
        self._retained[self._head["frame_hash"]] = self._head
        self._catalog = H.catalog_payload(self._declaration, self._accepted)
        self._catalogs[particle_hash(self._catalog)] = self._catalog

    @property
    def head(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._head)

    @property
    def catalog(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._catalog)

    def checkpoint(self) -> dict:
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            state = {
                "registry_seq": self.registry.sequence,
                "registry_hash": self.registry.commitment,
                "hive_rappid": self._hive,
                "mother_head_frame_hash": self._head["frame_hash"],
                "catalog_hash": particle_hash(self._catalog),
            }
            if self.registry.succession is not None:
                # Persisted atomically with the head, so a later registry cannot roll back succession.
                state.update(owner_lineage=list(self.registry.owner_lineage),
                             registry_lifecycle=list(self.registry.lifecycle))
            return state

    def _authorized(self, frame: dict, purpose: str) -> bool:
        signer = R.parse_detached_jws(frame["sig"])[0]["kid"]
        payload, kind = frame["payload"], frame["kind"]
        stamp_key = "projected_utc" if kind == "hive.projection" else "created_utc"
        require(payload.get(stamp_key) == frame["utc"], "frame: payload/envelope time mismatch")
        tenured = self.registry.owner_at(frame["utc"])
        if kind == "hive.declaration":
            H.validate_declaration(payload)
            require(frame["stream_id"] == payload["hive_rappid"] == self._hive,
                    "declaration: Mother Hive stream binding mismatch")
            owner = next(member["rappid"] for member in payload["members"] if member["role"] == "owner")
            require(owner == tenured == signer, "declaration: owner authorization mismatch")
            if self._declaration is not None:
                require(payload == self._declaration, "declaration: unaccepted policy replacement")
            return True
        require(self._declaration is not None, "Hive declaration must be authenticated first")
        declaration = self._declaration
        require(payload.get("hive_rappid", payload.get("source_hive_rappid")) == self._hive,
                "frame: foreign Hive")
        members = {member["rappid"]: member for member in declaration["members"]}
        if kind in {"hive.object", "hive.godd-slice"}:
            validator = H.validate_shared_object if kind == "hive.object" else H.validate_godd_slice
            validator(payload, declaration)
            require(signer == payload["producer_rappid"], "frame: signer/producer mismatch")
            require(signer in members and members[signer]["role"] in {"owner", "member"},
                    "frame: producer is not authorized to mutate")
            room = next(room for room in declaration["rooms"] if room["id"] == payload["room_id"])
            require(signer in room["members"], "frame: producer is outside the room")
            if kind == "hive.object":
                if room["access"] == "sealed":
                    require(
                        payload["object"]["protection"] == "sealed-room"
                        and payload["object"]["space"] == "rapp/1:egg-manifest",
                        "frame: sealed room object is not encrypted",
                    )
                path = payload["object"]["target_path"]
                areas = [members[signer]["area"], room["area"]]
                if members[signer]["role"] == "owner":
                    areas.extend(member["area"] for member in declaration["members"])
                require(any(path.startswith(area + "/") for area in areas),
                        "frame: producer cannot mutate the target area")
        elif kind == "hive.reconciliation":
            H.validate_reconciliation(payload, declaration)
            require(signer == payload["resolver_rappid"] == tenured,
                    "reconciliation: resolver is not authorized")
        elif kind == "hive.convergence":
            H.validate_convergence(payload, declaration)
            require(frame["stream_id"] == self._hive and signer == tenured,
                    "convergence: Mother Hive signer/stream authorization mismatch")
            if self.registry.succession is not None:
                # A back-dated owner act cannot reach state created after its own time (or its key's retirement).
                require(all(candidate["utc"] <= frame["utc"] for candidate in payload["candidates"]),
                        "convergence: a candidate is later than its convergence")
        elif kind == "hive.projection":
            require(signer == tenured and frame["stream_id"] != self._hive,
                    "projection: receipt signer/stream is not authorized")
            convergence = self._convergences.get(payload.get("convergence_payload_hash"))
            require(convergence is not None or (frame["seq"] == 0 and payload.get("status") in {"stale", "failed"}),
                    "projection: unaccepted convergence")
            H.validate_projection(payload, declaration, convergence)
            if self.registry.succession is not None and convergence is not None:
                require(frame["utc"] >= convergence["created_utc"], "projection: receipt is earlier than its convergence")
        else:
            raise ValueError("frame: this acceptance gate only consumes declarations, catalog mutations and receipts")
        return True

    def _chain(self, frame_hash: str) -> list[dict]:
        hex64(frame_hash, "frame address")
        if frame_hash in self._chains:
            return self._chains[frame_hash]
        try:
            records = self._resolve(frame_hash)
        except (LookupError, OSError, ValueError) as error:
            raise ValueError("frame: missing ancestor or frame bytes") from error
        require(isinstance(records, (list, tuple)) and records, "frame: complete ancestry bytes are required")
        chain, head = [], None
        for raw in records:
            require(isinstance(raw, bytes), "frame resolver must return bytes, not trusted summaries")
            frame = canonical_object(R._strict_json(raw), "frame")
            exact_keys(frame, R.FRAME_KEYS, "RAPP/1 frame")
            stream_id = frame["stream_id"]
            H.rappid(stream_id, "Hive body stream")
            require(stream_id in self.registry._genesis, "frame: stream has no registered genesis")
            if head is None:
                require(frame["frame_hash"] == self.registry._genesis[stream_id],
                        "frame: missing ancestor or wrong registered genesis")
            else:
                require(stream_id == head["stream_id"], "frame: cross-stream ancestry")
            schema = H.KIND_SCHEMAS.get(frame["kind"])
            require(schema is not None, "frame: unsupported Hive kind")
            H.authorize_hive_frame(
                frame, expected_schema=schema, head=head, stream_id=stream_id,
                registered_kinds=set(self.registry._kinds),
                signature_verifier=self.registry.verify_signature,
                authorization_verifier=self._authorized,
            )
            chain.append(frame)
            head = frame
            if self._declaration is None and frame["kind"] == "hive.declaration":
                self._declaration = copy.deepcopy(frame["payload"])
        require(head["frame_hash"] == frame_hash, "frame resolver returned a different wave address")
        for index, frame in enumerate(chain):
            self._frames[frame["frame_hash"]] = frame
            self._chains[frame["frame_hash"]] = chain[:index + 1]
        return chain

    def _ancestors(self, frame_hash: str, visiting: frozenset[str] = frozenset()) -> set[str]:
        require(frame_hash not in visiting, "frame: cyclic causal ancestry")
        if frame_hash in self._ancestry:
            return self._ancestry[frame_hash]
        chain = self._chain(frame_hash)
        frame = chain[-1]
        require(all(item["kind"] in CATALOG_KINDS for item in chain), "candidate: non-catalog stream ancestry")
        dependencies = set()
        direct = [chain[-2]["frame_hash"]] if len(chain) > 1 else []
        for source in frame["payload"].get("source_frames", []):
            source_frame = self._chain(source["frame_hash"])[-1]
            require(all(source[key] == source_frame[key] for key in source),
                    "candidate: source summary differs from signed bytes")
            direct.append(source["frame_hash"])
        direct.extend(frame["payload"].get("parents", []))
        for parent in direct:
            ancestor = self._chain(parent)[-1]
            require(ancestor["utc"] <= frame["utc"], "candidate: ancestor is later than descendant")
            dependencies.add(parent)
            dependencies.update(self._ancestors(parent, visiting | {frame_hash}))
        self._ancestry[frame_hash] = dependencies
        return dependencies

    def _candidate(self, candidate: dict) -> dict:
        chain = self._chain(candidate["frame_hash"])
        frame = chain[-1]
        require(frame["kind"] in CATALOG_KINDS, "candidate: not a catalog mutation")
        require(candidate["dimension_rappid"] == candidate["stream_id"] == frame["stream_id"] != self._hive,
                "candidate: dimension/stream binding mismatch")
        for key in ("stream_id", "seq", "utc", "payload_hash", "frame_hash"):
            require(candidate[key] == frame[key], "candidate: summary differs from signed frame bytes")
        require(candidate["mutation_keys"] == frame["payload"]["mutation_keys"],
                "candidate: mutation keys differ from signed payload")
        channels = {channel["id"] for channel in self._declaration["channels"]}
        require(candidate["source_channel_ids"] and set(candidate["source_channel_ids"]) <= channels,
                "candidate: unknown source channel")
        self._ancestors(frame["frame_hash"])
        return frame

    def _components(self, frames: dict[str, dict]) -> list[set[str]]:
        remaining, components = set(frames), []
        keys = {value: set(frame["payload"]["mutation_keys"]) for value, frame in frames.items()}
        while remaining:
            group, todo = set(), [min(remaining)]
            while todo:
                value = todo.pop()
                if value in group:
                    continue
                group.add(value)
                todo.extend(other for other in remaining - group if keys[value] & keys[other])
            remaining -= group
            concurrent = any(
                keys[left] & keys[right]
                and left not in self._ancestors(right)
                and right not in self._ancestors(left)
                for left in group for right in group if left < right
            )
            if concurrent:
                components.append(group)
        return components

    def _fork_reason(self, value: str, forks: dict) -> str | None:
        frontiers = {}
        for stream, sequence in forks:
            frontiers[stream] = min(sequence, frontiers.get(stream, sequence))

        def faulted(frame):
            return frame["stream_id"] in frontiers and frame["seq"] >= frontiers[frame["stream_id"]]

        if faulted(self._frames[value]):
            return "stream-fork"
        if any(faulted(self._frames[parent]) for parent in self._ancestors(value)):
            return "fork-ancestor"
        return None

    def _active(self, forks=None) -> dict[str, dict]:
        forks = self._forks if forks is None else forks
        eligible = {value: frame for value, frame in self._accepted.items()
                    if self._fork_reason(value, forks) is None}
        active = {}
        for value, frame in eligible.items():
            for key in frame["payload"]["mutation_keys"]:
                if not any(
                    key in other["payload"]["mutation_keys"] and value in self._ancestors(other_hash)
                    for other_hash, other in eligible.items() if other_hash != value
                ):
                    active[value] = frame
                    break
        return active

    def _evaluate(self, candidates: list[dict]):
        by_hash = {candidate["frame_hash"]: candidate for candidate in candidates}
        require(set(self._pending) <= set(by_hash), "convergence: must retain every unresolved candidate")
        valid, quarantine = {}, {}
        for value, candidate in by_hash.items():
            try:
                valid[value] = self._candidate(candidate)
            except (ValueError, TypeError, KeyError, IndexError, RecursionError):
                quarantine[value] = "invalid-candidate"
        for value in set(self._pending) & set(quarantine):
            raise ValueError("convergence: unresolved candidate bytes or metadata changed")
        prior = self._settled
        positions = {}
        observed = {value for value, frame in self._retained.items() if frame["kind"] in CATALOG_KINDS}
        for value in valid:
            observed.update(self._ancestors(value) | {value})
        for value in observed:
            frame = self._frames[value]
            positions.setdefault((frame["stream_id"], frame["seq"]), set()).add(value)
        forks = dict(self._forks)
        for position, hashes in positions.items():
            if len(hashes) > 1:
                forks[position] = frozenset(hashes) | forks.get(position, frozenset())
        for value, frame in valid.items():
            reason = self._fork_reason(value, forks)
            if reason is not None:
                quarantine[value] = reason
                continue
            pinned = self._stream_heads.get(frame["stream_id"])
            if pinned is not None and value not in prior:
                chain = self._chain(value)
                if frame["seq"] < pinned["seq"] or chain[pinned["seq"]]["frame_hash"] != pinned["frame_hash"]:
                    quarantine[value] = "invalid-candidate"
        for value in quarantine:
            valid.pop(value, None)
        active = self._active(forks)
        while True:
            missing = {
                value for value in set(valid) - prior
                if self._ancestors(value) - prior - set(valid)
            }
            if missing:
                for value in missing:
                    quarantine[value] = "unaccepted-ancestor"
                    del valid[value]
                continue
            resolvers = {value: frame for value, frame in valid.items()
                         if frame["kind"] == "hive.reconciliation" and value not in prior}
            normal = {value: frame for value, frame in valid.items() if value not in resolvers and value not in prior}
            groups = self._components({**active, **normal})
            group_for = {value: index for index, group in enumerate(groups) for value in group}
            matches, newly_quarantined = {}, {}
            for value, frame in resolvers.items():
                payload = frame["payload"]
                parents = set(payload["parents"])
                match = next((index for index, group in enumerate(groups) if parents == group), None)
                keys = sorted({key for parent in parents for key in self._frames[parent]["payload"]["mutation_keys"]})
                # Under succession a reconciliation may not predate the Mother head it resolves against.
                backdated = self.registry.succession is not None and frame["utc"] < self._head["utc"]
                if (match is None or payload["base_head_frame_hash"] != self._head["frame_hash"]
                        or payload["mutation_keys"] != keys or backdated):
                    newly_quarantined[value] = "invalid-reconciliation"
                    continue
                matches.setdefault(match, []).append(value)
            resolved, resolutions = {}, []
            for index, values in matches.items():
                if len(values) != 1:
                    newly_quarantined.update({value: "competing-reconciliation" for value in values})
                    continue
                resolver = values[0]
                resolved[index] = resolver
                for key in self._frames[resolver]["payload"]["mutation_keys"]:
                    parents = sorted(value for value in groups[index] if key in self._frames[value]["payload"]["mutation_keys"])
                    if len(parents) >= 2:
                        resolutions.append({"mutation_key": key, "frame_hashes": parents, "resolution_frame_hash": resolver})
            statuses = {}
            for value in by_hash:
                if value in quarantine or value in newly_quarantined:
                    statuses[value] = ("quarantined", newly_quarantined.get(value, quarantine.get(value)))
                elif value in prior:
                    statuses[value] = ("duplicate", "already-accepted")
                elif value in resolvers:
                    statuses[value] = ("accepted", "signed-reconciliation")
                elif value in group_for:
                    if group_for[value] in resolved:
                        statuses[value] = ("superseded", "reconciled")
                    else:
                        statuses[value] = ("conflict", "mutation-conflict")
                else:
                    statuses[value] = ("accepted", "verified")
            for value in set(valid) - prior:
                status = statuses[value][0]
                if status == "quarantined":
                    continue
                for parent in self._ancestors(value) - prior:
                    parent_status = statuses.get(parent, ("quarantined",))[0]
                    if parent_status in {"accepted", "duplicate"}:
                        continue
                    if value in resolvers and parent_status == "superseded":
                        continue
                    if (status in {"conflict", "superseded"} and parent_status in {"conflict", "superseded"}
                            and group_for.get(value) == group_for.get(parent) and value in group_for):
                        continue
                    newly_quarantined[value] = "blocked-ancestor"
                    break
            if not newly_quarantined:
                break
            quarantine.update(newly_quarantined)
            for value in newly_quarantined:
                valid.pop(value, None)
        decisions = [{"frame_hash": value, "status": status, "reason_code": reason}
                     for value, (status, reason) in sorted(statuses.items())]
        accepted = dict(self._accepted)
        accepted.update({value: valid[value] for value, (status, _) in statuses.items() if status == "accepted"})
        catalog = H.catalog_payload(self._declaration, accepted)
        return decisions, sorted(resolutions, key=lambda item: item["mutation_key"]), catalog, accepted, valid, forks

    def preview_convergence(self, candidates: list[dict], created_utc: str) -> dict:
        """A signing proposal only; this does not advance any accepted state."""
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            candidates = copy.deepcopy(candidates)
            payload = {
                "schema": H.CONVERGENCE_SCHEMA, "hive_rappid": self._hive, "created_utc": created_utc,
                "base_head_frame_hash": self._head["frame_hash"],
                "base_convergence_payload_hash": self._head["payload_hash"] if self._head["kind"] == "hive.convergence" else None,
                "base_catalog_hash": particle_hash(self._catalog),
                "candidates": candidates,
                "decisions": [{"frame_hash": candidate["frame_hash"], "status": "accepted", "reason_code": "proposal"}
                              for candidate in sorted(candidates, key=lambda item: item["frame_hash"])],
                "resolutions": [], "resulting_catalog_hash": particle_hash(self._catalog), "status": "converged",
            }
            H.validate_convergence(payload, self._declaration)
            decisions, resolutions, catalog, _, _, _ = self._evaluate(candidates)
            payload.update(decisions=decisions, resolutions=resolutions, resulting_catalog_hash=particle_hash(catalog),
                           status="partial" if any(item["status"] == "conflict" for item in decisions) else "converged")
            H.validate_convergence(payload, self._declaration)
            return payload

    def accept_convergence(self, frame_hash: str) -> dict:
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            require(frame_hash != self._head["frame_hash"], "convergence: Mother Hive frame replay")
            chain = self._chain(frame_hash)
            frame = chain[-1]
            require(frame["kind"] == "hive.convergence" and frame["stream_id"] == self._hive,
                    "convergence: wrong Mother Hive kind or stream")
            require([item["frame_hash"] for item in chain[:-1]] == self._mother,
                    "convergence: stale base or competing Mother Hive successor")
            payload = frame["payload"]
            require(payload["base_head_frame_hash"] == self._head["frame_hash"],
                    "convergence: stale base head")
            if self.registry.succession is not None:
                # Strictly later than the head it extends, so a retired key cannot append at that instant.
                require(frame["utc"] > self._head["utc"], "convergence: not later than the Mother head it extends")
            base_convergence = self._head["payload_hash"] if self._head["kind"] == "hive.convergence" else None
            require(payload["base_convergence_payload_hash"] == base_convergence, "convergence: stale base convergence")
            require(payload["base_catalog_hash"] == particle_hash(self._catalog), "convergence: stale base catalog")
            decisions, resolutions, catalog, accepted, valid, forks = self._evaluate(payload["candidates"])
            if self.registry.succession is not None:
                # Also by authenticated bytes, so a false candidate summary cannot hide a later frame.
                require(all(self._frames[item["frame_hash"]]["utc"] <= frame["utc"] for item in payload["candidates"]
                            if item["frame_hash"] in self._frames),
                        "convergence: a candidate frame is later than its convergence")
            require([(item["frame_hash"], item["status"]) for item in payload["decisions"]]
                    == [(item["frame_hash"], item["status"]) for item in decisions],
                    "convergence: decisions differ from authenticated evaluation (including required duplicate decisions)")
            # A recorded fork must not become an ordinary quarantine when its bytes go missing on restore.
            require({(item["frame_hash"], item["reason_code"]) for item in payload["decisions"]
                     if item["reason_code"] in FORK_REASONS}
                    == {(item["frame_hash"], item["reason_code"]) for item in decisions
                        if item["reason_code"] in FORK_REASONS},
                    "convergence: fork evidence differs from authenticated evaluation or is unavailable")
            require(payload["resolutions"] == resolutions, "convergence: resolutions differ from signed complete parent sets")
            require(payload["resulting_catalog_hash"] == particle_hash(catalog),
                    "convergence: resulting catalog hash differs from accepted frames")
            self._accepted = accepted
            self._catalog = catalog
            self._catalogs[particle_hash(catalog)] = catalog
            self._pending = {item["frame_hash"]: valid[item["frame_hash"]]
                             for item in decisions if item["status"] == "conflict"}
            evidence = {value for hashes in forks.values() for value in hashes}
            evidence.update(item["frame_hash"] for item in decisions if item["reason_code"] in FORK_REASONS)
            for value in evidence:
                for retained in self._ancestors(value) | {value}:
                    self._retained[retained] = self._frames[retained]
            for item in decisions:
                if item["status"] == "quarantined":
                    continue
                value = item["frame_hash"]
                for retained in self._ancestors(value) | {value}:
                    self._retained[retained] = self._frames[retained]
                if item["status"] in {"accepted", "duplicate", "superseded"}:
                    self._settled.add(value)
                    candidate = valid[value]
                    previous = self._stream_heads.get(candidate["stream_id"])
                    if previous is None or candidate["seq"] > previous["seq"]:
                        self._stream_heads[candidate["stream_id"]] = candidate
            self._forks = forks
            self._head = frame
            self._mother.append(frame_hash)
            self._retained[frame_hash] = frame
            self._convergences[frame["payload_hash"]] = payload
            return {"status": "accepted", "authenticated": True, **self.checkpoint()}

    def restore(self, mother_head_frame_hash: str) -> dict:
        """Rebuild state from signed history, not a serialized accepted-frame list."""
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            require(len(self._mother) == 1, "restore requires a genesis-only verifier")
            try:
                chain = self._chain(mother_head_frame_hash)
                require(chain[0]["frame_hash"] == self._head["frame_hash"], "restore: foreign genesis")
                for frame in chain[1:]:
                    self.accept_convergence(frame["frame_hash"])
                return self.checkpoint()
            except Exception:
                self._restore_failed = True
                raise

    def artifact_manifest(self) -> dict:
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            require(self._head["kind"] == "hive.convergence", "manifest: no accepted convergence")
            addresses = {("rapp/1:wave", value) for value in self._retained}
            addresses.update(("rapp/1:particle", value) for value in self._catalogs)
            addresses.add(("rapp/1:particle", particle_hash(self.registry._document)))
            for frame in self._retained.values():
                payload = frame["payload"]
                if frame["kind"] == "hive.object":
                    addresses.add((payload["object"]["space"], payload["object"]["hash"]))
                elif frame["kind"] == "hive.godd-slice":
                    addresses.add(("rapp/1:egg-manifest", payload["content"]["sealed_egg_hash"]))
                elif frame["kind"] == "hive.reconciliation":
                    addresses.add((payload["result"]["space"], payload["result"]["hash"]))
            manifest = {
                "schema": H.MANIFEST_SCHEMA, "hive_rappid": self._hive,
                "world_id": self._declaration["world_id"], "registry_seq": self.registry.sequence,
                "registry_hash": self.registry.commitment, "frame_head": self._head["frame_hash"],
                "catalog_hash": particle_hash(self._catalog),
                "artifacts": [{"space": space, "hash": value} for space, value in sorted(addresses)],
            }
            H.validate_artifact_manifest(manifest)
            return manifest

    def accept_projection(self, frame_hash: str, *, manifest_bytes: bytes, artifact_resolver) -> dict:
        with self._lock:
            require(not self._restore_failed, "restore: failed history recovery")
            require(callable(artifact_resolver), "projection: artifact byte resolver is required")
            chain = self._chain(frame_hash)
            receipt = chain[-1]
            require(receipt["kind"] == "hive.projection", "projection: wrong receipt kind")
            payload = receipt["payload"]
            require(all(item["kind"] == "hive.projection" and item["payload"]["channel_id"] == payload["channel_id"]
                        for item in chain), "projection: receipt stream/channel binding mismatch")
            require(payload["status"] == "current", "projection: receipt is not current")
            require(payload["registry_seq"] == self.registry.sequence, "projection: authenticated registry sequence mismatch")
            if self.registry.succession is not None and self.registry.epoch is not None:
                # A current receipt names its registry; it cannot predate that registry's latest lifecycle record.
                require(receipt["utc"] >= self.registry.epoch,
                        "projection: receipt predates the latest succession or revocation in its registry")
            require(payload["frame_head"] == self._head["frame_hash"], "projection: actual Mother Hive head mismatch")
            require(payload["convergence_payload_hash"] == self._head["payload_hash"],
                    "projection: current convergence mismatch")
            require(payload["catalog_hash"] == particle_hash(self._catalog), "projection: actual catalog mismatch")
            manifest = canonical_object(R._strict_json(manifest_bytes), "projection artifact manifest")
            H.validate_artifact_manifest(manifest)
            require(manifest == self.artifact_manifest(), "projection: artifact manifest differs from accepted state")
            require(payload["artifact_manifest_hash"] == particle_hash(manifest), "projection: artifact manifest hash mismatch")
            for address in manifest["artifacts"]:
                space, value = address["space"], address["hash"]
                try:
                    raw = artifact_resolver(space, value)
                except (LookupError, OSError, ValueError) as error:
                    raise ValueError("projection: missing artifact bytes") from error
                require(isinstance(raw, bytes), "projection: expected artifact bytes")
                if space == "rapp/1:egg-manifest":
                    egg, _ = R.read_egg(raw)
                    created = egg.get("created_utc") if isinstance(egg, dict) else None
                    owner = self.registry.owner_at(created) if R.utc_valid(created) else self.registry.owner
                    ok, step, why = R.verify_egg(raw, signature_verifier=self.registry.verify_signature,
                                               estate_owner_rappid=owner)
                    require(ok and egg["sig"] is not None and R.egg_address(egg) == value,
                            f"projection: signed egg refusal {step}: {why}")
                    for frame in self._retained.values():
                        descriptor = frame["payload"]
                        if frame["kind"] == "hive.godd-slice" and descriptor["content"]["sealed_egg_hash"] == value:
                            require(egg["variant"] == "sealed"
                                    and egg["rappid"] == descriptor["content"]["artifact_rappid"],
                                    "projection: GODD sealed egg binding mismatch")
                        if frame["kind"] == "hive.object" and descriptor["object"]["hash"] == value:
                            require(descriptor["object"]["protection"] != "sealed-room" or egg["variant"] == "sealed",
                                    "projection: sealed-room object is not a sealed egg")
                else:
                    artifact = canonical_object(R._strict_json(raw), "projection artifact")
                    if space == "rapp/1:particle":
                        require(particle_hash(artifact) == value, "projection: particle artifact tamper")
                    else:
                        require(artifact == self._chain(value)[-1], "projection: signed frame artifact tamper")
            previous = self._receipt_heads.get(payload["channel_id"])
            if previous is not None:
                require(receipt["stream_id"] == previous["stream_id"]
                        and receipt["seq"] > previous["seq"]
                        and chain[previous["seq"]]["frame_hash"] == previous["frame_hash"],
                        "projection: receipt replay, rollback or fork")
            self._receipt_heads[payload["channel_id"]] = receipt
            return {"status": "current", "authenticated": True, "channel_id": payload["channel_id"],
                    "artifact_manifest_hash": particle_hash(manifest), **self.checkpoint()}
