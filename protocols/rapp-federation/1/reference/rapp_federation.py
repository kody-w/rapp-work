"""Receiver-local, durable acceptance for the bounded rapp-federation/1 profile."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import secrets
import sqlite3
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType

from jsonschema import Draft202012Validator

from schema_source import CONFORMANCE_CLASS, KINDS, PROFILE
from wire import (
    H, Hb, Refusal, canonical, chat_url, decrypt_sealed, https_locator, inspect_sealed, load_spki, loads,
    memory_owner, require,
    stamp_ms, unsigned, valid_rappid, verify_chain, verify_frame, verify_signature,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = loads((ROOT / "schema.json").read_bytes())
VALIDATORS = {
    name: Draft202012Validator({"$ref": "#/$defs/" + name, "$defs": SCHEMA["$defs"]})
    for name in ("frame", "registry", "terms", "party")
}
SORTED_FIELDS = frozenset({
    "depends_on", "actions", "modes", "allowed_peers", "allowed_actors",
    "controls", "capabilities", "missing",
})
OWNER_KINDS = frozenset({"peer", "policy", "grant", "control"})
FORK_CODES = frozenset({"stream-fork", "sovereign-fork"})
TRANSITIONS = {
    None: {"received"},
    "received": {"validated", "rejected"},
    "validated": {"accepted", "rejected"},
    "accepted": {"executing", "rejected"},
    "executing": {"completed", "failed"},
    "completed": set(), "failed": set(), "rejected": set(),
}


def validate(value, definition="frame"):
    canonical(value)
    error = next(VALIDATORS[definition].iter_errors(value), None)
    require(error is None, "schema", str(error.message)[:240] if error else "")

    def walk(item):
        if type(item) is dict:
            for key, child in item.items():
                if key in SORTED_FIELDS:
                    require(child == sorted(child), "set-order", key)
                if child is not None and (key == "utc" or key.endswith("_utc")
                                          or key in {"not_before", "not_after", "clock_lower", "clock_upper"}):
                    stamp_ms(child)
                if key == "endpoint":
                    require(chat_url(child), "endpoint")
                if key == "canonical_source":
                    require(https_locator(child), "registry-locator")
                walk(child)
        elif type(item) is list:
            for child in item:
                walk(child)
        elif type(item) is str and item.startswith("rappid:"):
            require(valid_rappid(item) or memory_owner(item) is not None, "rappid")
    walk(value)
    return value


@dataclass(frozen=True)
class Clock:
    """Trusted local UTC interval. Neither a frame timestamp nor transport time."""
    lower: str | None
    upper: str | None

    def bounds(self):
        require((self.lower is None) == (self.upper is None), "clock-shape")
        if self.lower is None:
            return None
        lower, upper = stamp_ms(self.lower), stamp_ms(self.upper)
        require(lower <= upper, "clock-shape")
        return lower, upper


@dataclass(frozen=True)
class CellAnchor:
    """Out-of-band per-cell trust; never constructed from a discovery document."""
    hive_rappid: str
    world_id: str
    owner_rappid: str
    owner_spki_der: bytes
    authority_stream: str

    def document(self):
        require(all(valid_rappid(value) for value in (self.hive_rappid, self.owner_rappid))
                and memory_owner(self.authority_stream) == self.owner_rappid, "anchor-identity")
        require(type(self.owner_spki_der) is bytes
                and Hb("rapp/1:rappid", self.owner_spki_der) == self.owner_rappid.rsplit(":", 1)[1],
                "anchor-key")
        validate({"hive_rappid": self.hive_rappid, "world_id": self.world_id,
                  "actor_rappid": self.owner_rappid}, "party")
        return {
            "hive_rappid": self.hive_rappid, "world_id": self.world_id,
            "owner_rappid": self.owner_rappid,
            "owner_spki_der_b64": base64.b64encode(self.owner_spki_der).decode("ascii"),
            "authority_stream": self.authority_stream,
        }


class Registry:
    """Direct-owner section-13 subset. Unsupported succession is not guessed."""

    def __init__(self, raw: bytes, anchor: CellAnchor):
        document = validate(loads(raw), "registry")
        owner_keys = {anchor.owner_rappid: anchor.owner_spki_der}
        verify_signature(unsigned(document), document["sig"], owner_keys, anchor.owner_rappid)
        self.sequence = document["registry_seq"]
        self.commitment = H("rapp/1:particle", unsigned(document))
        self.owner = anchor.owner_rappid
        self.raw = canonical(document)
        keys, active, genesis, kinds, owners, profiles, revoked = {}, set(), {}, {}, [], [], set()
        for entry in document["entries"]:
            kind = entry["type"]
            if kind == "estate_owner":
                owners.append(entry["rappid"])
            elif kind == "protocol":
                if entry["name"] == PROFILE and not entry["deprecated"]:
                    profiles.append(entry)
            elif kind == "kind":
                require(entry["kind"] not in kinds, "registry-kind-duplicate")
                kinds[entry["kind"]] = None if entry["deprecated"] else entry["family"]
            elif kind == "genesis":
                require(entry["stream_id"] not in genesis, "registry-competing-genesis")
                genesis[entry["stream_id"]] = entry["frame_hash"]
            elif kind == "spki":
                identity = entry["rappid"]
                require(identity not in keys, "registry-key-duplicate")
                try:
                    raw_key = base64.b64decode(entry["spki_der_b64"], validate=True)
                except (ValueError, TypeError) as error:
                    raise Refusal("registry-key-encoding") from error
                require(base64.b64encode(raw_key).decode("ascii") == entry["spki_der_b64"],
                        "registry-key-encoding")
                load_spki(raw_key)
                require(Hb("rapp/1:rappid", raw_key) == identity.rsplit(":", 1)[1], "registry-key-binding")
                keys[identity] = raw_key
                if not entry["deprecated"]:
                    active.add(identity)
            elif kind == "tombstone":
                require(entry["rappid"] not in revoked, "registry-tombstone-duplicate")
                verify_signature(unsigned(entry), entry["sig"], owner_keys, anchor.owner_rappid)
                revoked.add(entry["rappid"])
        require(owners == [anchor.owner_rappid], "registry-owner")
        require(keys.get(anchor.owner_rappid) == anchor.owner_spki_der
                and anchor.owner_rappid in active - revoked, "registry-owner-key")
        require(len(profiles) == 1, "registry-profile")
        require(profiles[0]["spec_path"] == "protocols/rapp-federation/1/SPEC.md"
                and profiles[0]["spec_hash"] == hashlib.sha256((ROOT / "SPEC.md").read_bytes()).hexdigest(),
                "registry-profile-hash")
        require(all(kinds.get("federation." + name) == "memory" for name in KINDS), "registry-kinds")
        require(anchor.authority_stream in genesis and anchor.hive_rappid in genesis, "registry-cell-root")
        self.keys = MappingProxyType(keys)
        self.active = frozenset(active - revoked)
        self.revoked = frozenset(revoked)
        self.genesis = MappingProxyType(genesis)


@dataclass(frozen=True)
class ReleasePermit:
    request_hash: str
    request_id: str
    grant_hash: str
    source_hive: str
    destination_hive: str
    destination_world: str
    recipient_rappid: str
    artifact_hash: str
    key_id: str
    key_service_rappid: str
    mode: str
    action: str
    units: int
    not_before: str
    not_after: str
    source_checkpoint: str
    destination_checkpoint: str
    source_registry_hash: str
    destination_registry_hash: str


class Federation:
    """One receiver's serialization domain, not a shared/global Hive Mind DB."""

    def __init__(self, database, *, local_hive: str, anchors, clock: Clock):
        anchor_map = {anchor.hive_rappid: anchor for anchor in anchors}
        require(len(anchor_map) == len(anchors) and local_hive in anchor_map, "anchors")
        require(len({anchor.authority_stream for anchor in anchors}) == len(anchors), "competing-authorities")
        self.anchors = MappingProxyType(anchor_map)
        self.local_hive = local_hive
        self._lock = threading.RLock()
        require(isinstance(database, (str, Path)) and bool(str(database))
                and not str(database).startswith("file:"), "database-path")
        self._persistent = str(database) != ":memory:"
        self.db = sqlite3.connect(database, isolation_level=None, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA temp_store=MEMORY")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS registries (
                hive TEXT PRIMARY KEY, sequence INTEGER NOT NULL, commitment TEXT NOT NULL, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS registry_history (
                commitment TEXT PRIMARY KEY, hive TEXT NOT NULL, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS frames (
                hash TEXT PRIMARY KEY, stream TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
                hive TEXT NOT NULL, raw BLOB NOT NULL, UNIQUE(stream, seq));
            CREATE TABLE IF NOT EXISTS authority (hive TEXT PRIMARY KEY, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS policies (hive TEXT PRIMARY KEY, hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS grants (
                hive TEXT NOT NULL, grant_id TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(hive, grant_id));
            CREATE TABLE IF NOT EXISTS approvals (
                scope TEXT NOT NULL, target TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(scope, target));
            CREATE TABLE IF NOT EXISTS controls (
                hive TEXT NOT NULL, sequence INTEGER NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(hive, sequence));
            CREATE TABLE IF NOT EXISTS revoked (
                kind TEXT NOT NULL, target TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(kind, target));
            CREATE TABLE IF NOT EXISTS blocked (
                hive TEXT NOT NULL, peer TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(hive, peer));
            CREATE TABLE IF NOT EXISTS requests (
                source TEXT NOT NULL, request_id TEXT NOT NULL, frame_hash TEXT NOT NULL,
                payload_hash TEXT NOT NULL, phase TEXT, receipt TEXT, reserved INTEGER NOT NULL DEFAULT 0,
                opened INTEGER NOT NULL DEFAULT 0, local_status TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY(source, request_id));
            CREATE TABLE IF NOT EXISTS usage (
                grant_hash TEXT PRIMARY KEY, uses INTEGER NOT NULL, units INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS execution_attempts (
                request_hash TEXT PRIMARY KEY, permit_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS challenges (
                nonce TEXT PRIMARY KEY, source TEXT NOT NULL, destination TEXT NOT NULL, actor TEXT NOT NULL,
                intent_hash TEXT NOT NULL, issued INTEGER NOT NULL, expires INTEGER NOT NULL, used_by TEXT);
            CREATE TABLE IF NOT EXISTS bundles (
                hive TEXT NOT NULL, bundle_id TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(hive, bundle_id));
            CREATE TABLE IF NOT EXISTS pending (hash TEXT PRIMARY KEY, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS quarantine (hash TEXT PRIMARY KEY, raw BLOB NOT NULL, code TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS authority_faults (
                hive TEXT PRIMARY KEY, evidence TEXT NOT NULL, code TEXT NOT NULL, raw BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS stream_faults (
                stream TEXT NOT NULL, sequence INTEGER NOT NULL, hive TEXT NOT NULL,
                original TEXT NOT NULL, evidence TEXT NOT NULL, raw BLOB NOT NULL,
                PRIMARY KEY(stream, sequence, evidence));
            CREATE TABLE IF NOT EXISTS dogg_approvals (
                content_hash TEXT NOT NULL, evidence_hash TEXT NOT NULL, PRIMARY KEY(content_hash, evidence_hash));
        """)
        try:
            configuration = canonical({"local_hive": local_hive, "conformance_class": CONFORMANCE_CLASS,
                                       "anchors": [anchor_map[key].document() for key in sorted(anchor_map)]})
            with self.transaction():
                old = self.db.execute("SELECT value FROM settings WHERE key='configuration'").fetchone()
                require(old is None or old[0] == configuration, "store-configuration-substitution")
                self.db.execute("INSERT OR IGNORE INTO settings VALUES ('configuration', ?)", (configuration,))
            self._check_recovery_state()
            self._clock = clock
            self.observe_clock(clock)
        except BaseException:
            self.db.close()
            raise

    @contextlib.contextmanager
    def transaction(self):
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def close(self):
        self.db.close()

    def _check_recovery_state(self):
        """Detect missing/contradictory consumption state; never reconstruct fresh rights."""
        with self.transaction():
            self._recover_stream_faults()
            request_frames, receipt_frames = {}, {}
            for row in self.db.execute("SELECT raw FROM frames WHERE kind IN ('federation.request', 'federation.receipt')"):
                frame = loads(row[0])
                payload = frame["payload"]
                if frame["kind"] == "federation.request":
                    key = (payload["issuer"]["hive_rappid"], payload["request_id"])
                    request_frames.setdefault(key, []).append(frame)
                else:
                    receipt_frames.setdefault(payload["request"], []).append(frame)
            ledger = {(row["source"], row["request_id"]): row for row in self.db.execute("SELECT * FROM requests")}
            require(set(ledger) == set(request_frames), "recovery-quarantine", "request ledger differs from retained frames")
            attempts = {row[0] for row in self.db.execute("SELECT request_hash FROM execution_attempts")}
            originals, expected_usage = set(), {}
            for key, row in ledger.items():
                candidates = request_frames[key]
                matching = [frame for frame in candidates if frame["frame_hash"] == row["frame_hash"]]
                require(len(matching) == 1
                        and all(frame["payload_hash"] == row["payload_hash"] for frame in candidates),
                        "recovery-quarantine", "original request commitment missing")
                request = matching[0]
                address = request["frame_hash"]
                originals.add(address)
                receipts = receipt_frames.get(address, [])
                by_hash = {frame["frame_hash"]: frame for frame in receipts}
                if receipts:
                    referenced = {frame["payload"]["prior"] for frame in receipts if frame["payload"]["prior"] is not None}
                    leaves = set(by_hash) - referenced
                    require(len(leaves) == 1 and referenced <= set(by_hash), "recovery-quarantine", "receipt chain incomplete")
                    tip = leaves.pop()
                    require(row["receipt"] == tip and row["phase"] == by_hash[tip]["payload"]["phase"],
                            "recovery-quarantine", "receipt frontier rolled back")
                    seen, cursor = set(), tip
                    while cursor is not None:
                        require(cursor in by_hash and cursor not in seen, "recovery-quarantine", "receipt chain invalid")
                        seen.add(cursor)
                        cursor = by_hash[cursor]["payload"]["prior"]
                    require(seen == set(by_hash), "recovery-quarantine", "unaccounted receipt")
                else:
                    require(row["phase"] is None and row["receipt"] is None, "recovery-quarantine", "receipt evidence missing")
                reserved = int(any(frame["payload"]["phase"] == "accepted" for frame in receipts))
                require(row["reserved"] == reserved and row["opened"] in (0, 1)
                        and row["opened"] == int(address in attempts), "recovery-quarantine", "execution state missing")
                require(row["local_status"] in ({"in-doubt", "opened"} if row["opened"] else {"pending"}),
                        "recovery-quarantine", "execution state inconsistent")
                if row["phase"] == "completed":
                    require(row["opened"] == 1 and row["local_status"] == "opened",
                            "recovery-quarantine", "completed effect lost")
                if reserved:
                    terms = request["payload"]["terms"]
                    total = expected_usage.setdefault(terms["grant"], [0, 0])
                    total[0] += 1
                    total[1] += terms["units"]
            require(set(receipt_frames) <= originals and attempts <= originals,
                    "recovery-quarantine", "orphan execution evidence")
            actual_usage = {row["grant_hash"]: [row["uses"], row["units"]] for row in self.db.execute("SELECT * FROM usage")}
            require(actual_usage == expected_usage, "recovery-quarantine", "consumption/allocation state lost")

    def observe_clock(self, clock: Clock):
        require(isinstance(clock, Clock), "clock-source")
        bounds = clock.bounds()
        with self.transaction():
            if bounds is not None:
                row = self.db.execute("SELECT value FROM settings WHERE key='clock_floor'").fetchone()
                floor = int(row[0]) if row else bounds[0]
                require(bounds[1] >= floor, "clock-rollback")
                self.db.execute("INSERT OR REPLACE INTO settings VALUES ('clock_floor', ?)",
                                (str(max(floor, bounds[0])),))
            self._clock = clock

    def _authority_fault(self, hive, evidence, code, raw):
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO authority_faults VALUES (?, ?, ?, ?)",
                            (hive, evidence, code, raw))

    def _record_stream_fork(self, frame, original, code):
        hive, actor = self.issuer(frame["payload"])
        raw = canonical(frame)
        self.db.execute("INSERT OR IGNORE INTO stream_faults VALUES (?, ?, ?, ?, ?, ?)",
                        (frame["stream_id"], frame["seq"], hive, original["frame_hash"], frame["frame_hash"], raw))
        if actor == self.anchors[hive].owner_rappid:
            self.db.execute("INSERT OR IGNORE INTO authority_faults VALUES (?, ?, ?, ?)",
                            (hive, frame["frame_hash"], code, raw))
        self.db.execute("INSERT OR IGNORE INTO quarantine VALUES (?, ?, ?)", (frame["frame_hash"], raw, code))
        self.db.execute("DELETE FROM pending WHERE hash=?", (frame["frame_hash"],))

    def _verify_stream_fork(self, frame, original):
        validate(frame)
        validate(original)
        hive, actor = self.issuer(frame["payload"])
        registry = self.registry(hive)
        require(memory_owner(frame["stream_id"]) == actor, "stream-key-binding")
        require(frame["stream_id"] == original["stream_id"] and frame["seq"] == original["seq"]
                and frame["frame_hash"] != original["frame_hash"], "stream-fork-evidence")
        require(frame["stream_id"] in registry.genesis, "stream-unregistered")
        if actor not in registry.active:
            # Revocation or key removal cannot erase a previously authenticated fork.
            genesis = registry.genesis[frame["stream_id"]]
            for row in self.db.execute("SELECT raw FROM registry_history WHERE hive=?", (hive,)):
                historical = Registry(row[0], self.anchors[hive])
                if actor in historical.active and historical.genesis.get(frame["stream_id"]) == genesis:
                    registry = historical
                    break
        require(actor in registry.active, "actor-inactive")
        for item in (original, frame):
            require(self.issuer(item["payload"]) == (hive, actor), "stream-issuer")
            require(verify_frame(item, registry.keys) == actor, "issuer-signature")
            require(item["stream_id"] in registry.genesis, "stream-unregistered")
            self._bind_stream(item, registry)
        return hive

    def _recover_stream_faults(self):
        proofs = []
        for row in self.db.execute("SELECT * FROM stream_faults"):
            try:
                frame = loads(row["raw"])
                original = self.frame(row["original"])
                hive = self._verify_stream_fork(frame, original)
                require(row["raw"] == canonical(frame) and row["stream"] == frame["stream_id"]
                        and row["sequence"] == frame["seq"] and row["hive"] == hive
                        and row["original"] == original["frame_hash"]
                        and row["evidence"] == frame["frame_hash"], "stream-fork-evidence")
                proofs.append((frame, original))
            except Refusal as error:
                raise Refusal("recovery-quarantine", "invalid retained stream fork proof") from error
        # Old stores may retain a signed fork only in quarantine or the owner-fault latch.
        evidence = list(self.db.execute("SELECT raw, code FROM quarantine"))
        evidence += list(self.db.execute("SELECT raw, code FROM authority_faults"))
        for row in evidence:
            if row["code"] not in FORK_CODES | {"stream-equivocation"}:
                continue
            try:
                frame = validate(loads(row["raw"]))
                require(row["raw"] == canonical(frame), "frame-noncanonical")
                original = self.db.execute("SELECT raw FROM frames WHERE stream=? AND seq=?",
                                           (frame["stream_id"], frame["seq"])).fetchone()
                require(original is not None, "dependency-missing")
                original = loads(original[0])
                self._verify_stream_fork(frame, original)
            except Refusal:
                continue
            proofs.append((frame, original))
        for frame, original in proofs:
            hive, _ = self.issuer(frame["payload"])
            code = "sovereign-fork" if frame["stream_id"] == self.anchors[hive].authority_stream else "stream-fork"
            self._record_stream_fork(frame, original, code)

    def install_registry(self, hive: str, raw: bytes):
        try:
            return self._install_registry(hive, raw)
        except Refusal as error:
            if error.code == "registry-equivocation":
                registry = Registry(raw, self.anchors[hive])
                self._authority_fault(hive, registry.commitment, error.code, registry.raw)
            raise

    def _install_registry(self, hive: str, raw: bytes):
        require(hive in self.anchors, "unknown-cell")
        registry = Registry(raw, self.anchors[hive])
        with self.transaction():
            old = self.db.execute("SELECT * FROM registries WHERE hive=?", (hive,)).fetchone()
            if old is not None:
                require(registry.sequence >= old["sequence"], "registry-rollback")
                if registry.sequence == old["sequence"]:
                    require(registry.commitment == old["commitment"], "registry-equivocation")
                previous = Registry(old["raw"], self.anchors[hive])
                require(previous.revoked <= registry.revoked, "registry-revocation-rollback")
                for stream, address in previous.genesis.items():
                    require(registry.genesis.get(stream) == address, "registry-genesis-substitution")
            self.db.execute("INSERT OR REPLACE INTO registries VALUES (?, ?, ?, ?)",
                            (hive, registry.sequence, registry.commitment, registry.raw))
            self.db.execute("INSERT OR IGNORE INTO registry_history VALUES (?, ?, ?)",
                            (registry.commitment, hive, registry.raw))
        return {"registry_seq": registry.sequence, "registry_hash": registry.commitment}

    def registry(self, hive):
        require(hive in self.anchors, "unknown-cell")
        row = self.db.execute("SELECT raw FROM registries WHERE hive=?", (hive,)).fetchone()
        require(row is not None, "registry-missing")
        return Registry(row[0], self.anchors[hive])

    def frame(self, address, kind=None):
        row = self.db.execute("SELECT raw FROM frames WHERE hash=?", (address,)).fetchone()
        require(row is not None, "dependency-missing", str(address))
        frame = loads(row[0])
        require(kind is None or frame["kind"] == "federation." + kind, "dependency-kind")
        return frame

    def payload(self, address, kind=None):
        return self.frame(address, kind)["payload"]

    def latest(self, table, hive):
        require(table in {"authority", "policies"}, "internal-table")
        row = self.db.execute(f"SELECT hash FROM {table} WHERE hive=?", (hive,)).fetchone()
        return row[0] if row else None

    @staticmethod
    def issuer(payload):
        if payload["schema"] == PROFILE + "-discovery":
            return payload["hive_rappid"], payload["advertiser_rappid"]
        if payload["schema"] == PROFILE + "-checkpoint" and payload["phase"] == "genesis":
            return payload["hive_rappid"], payload["actor_rappid"]
        return payload["issuer"]["hive_rappid"], payload["issuer"]["actor_rappid"]

    def _party(self, party):
        hive = party["hive_rappid"]
        require(hive in self.anchors, "unknown-cell")
        require(party["world_id"] == self.anchors[hive].world_id, "wrong-world")
        require(party["actor_rappid"] in self.registry(hive).active, "actor-inactive")
        return hive

    def _context(self, payload, *, allow_historical=False):
        hive = self._party(payload["issuer"])
        checkpoint = self.payload(payload["checkpoint"], "checkpoint")
        require(checkpoint["phase"] == "authority"
                and checkpoint["issuer"]["hive_rappid"] == hive, "checkpoint-cell")
        if allow_historical:
            row = self.db.execute(
                "SELECT raw FROM registry_history WHERE commitment=? AND hive=?",
                (checkpoint["registry_hash"], hive),
            ).fetchone()
            require(row is not None, "registry-stale")
            registry = Registry(row[0], self.anchors[hive])
        else:
            registry = self.registry(hive)
        require(checkpoint["registry_hash"] == registry.commitment
                and checkpoint["registry_seq"] == registry.sequence, "registry-stale")
        return checkpoint

    def _require_dependencies(self, payload, references):
        declared = set(payload["depends_on"])
        require({value for value in references if value is not None} <= declared, "dependency-undeclared")
        for value in declared:
            self.frame(value)

    def _require_unforked(self, frame, *, dependencies=True):
        frontiers = dict(self.db.execute("SELECT stream, MIN(sequence) FROM stream_faults GROUP BY stream"))
        if not frontiers:
            return

        def check(item):
            require(item["stream_id"] not in frontiers or item["seq"] < frontiers[item["stream_id"]],
                    "stream-equivocation")

        check(frame)
        if not dependencies:
            return
        references = set(frame["payload"].get("depends_on", []))
        if frame["seq"] > 0:
            previous = self.db.execute("SELECT hash FROM frames WHERE stream=? AND seq=?",
                                       (frame["stream_id"], frame["seq"] - 1)).fetchone()
            require(previous is not None, "dependency-missing")
            references.add(previous[0])
        closure = set()
        for value in references:
            closure.update(self._closure(value))
        for value in closure:
            check(self.frame(value))

    def _bind_stream(self, frame, registry):
        payload = frame["payload"]
        hive, actor = self.issuer(payload)
        kind = frame["kind"].split(".", 1)[1]
        require(payload["schema"] == PROFILE + "-" + kind, "payload-kind")
        if "issuer" in payload:
            require(payload["issuer"]["world_id"] == self.anchors[hive].world_id, "wrong-world")
            require(actor in registry.active, "actor-inactive")
        if frame["seq"] == 0:
            require(kind == "checkpoint" and payload["phase"] == "genesis", "stream-bootstrap")
            self._genesis(frame)
            return
        root = self.frame(registry.genesis[frame["stream_id"]], "checkpoint")
        require(root["stream_id"] == frame["stream_id"] and root["payload"]["phase"] == "genesis"
                and root["payload"]["hive_rappid"] == hive and root["payload"]["actor_rappid"] == actor,
                "stream-issuer")
        role = root["payload"]["stream_role"]
        if kind == "checkpoint":
            require(role == "authority" and payload["phase"] == "authority", "authority-stream")
        elif kind == "discovery":
            require(role == "discovery", "discovery-private-stream")
        else:
            require(role in {"actor", "relay"}, "foreign-dimension")
            require(role != "relay" or kind in {"custody", "observation"}, "relay-not-authority")
            if kind in OWNER_KINDS:
                require(actor == self.anchors[hive].owner_rappid, "owner-required")

    def accept(self, raw: bytes):
        try:
            return self._accept(raw)
        except Refusal as error:
            if error.code == "competing-sovereign-heads":
                frame = loads(raw)
                hive, actor = self.issuer(frame["payload"])
                anchor = self.anchors[hive]
                verify_signature(unsigned(frame), frame["sig"], {anchor.owner_rappid: anchor.owner_spki_der},
                                 anchor.owner_rappid)
                self._authority_fault(hive, frame["frame_hash"], error.code, canonical(frame))
            raise

    def _accept(self, raw: bytes):
        frame = validate(loads(raw))
        require(raw == canonical(frame), "frame-noncanonical")
        payload = frame["payload"]
        hive, actor = self.issuer(payload)
        kind = frame["kind"].split(".", 1)[1]
        historical = kind == "receipt" and payload["phase"] not in {"accepted", "executing"}
        fault = None
        with self.transaction():
            registry = self.registry(hive)
            signer = verify_frame(frame, registry.keys)
            require(signer == actor, "issuer-signature")
            self._require_unforked(frame, dependencies=False)
            existing = self.db.execute("SELECT raw FROM frames WHERE hash=?", (frame["frame_hash"],)).fetchone()
            if existing is not None:
                require(existing[0] == canonical(frame), "frame-substitution")
                self._require_unforked(frame, dependencies=not historical)
                self.db.execute("DELETE FROM pending WHERE hash=?", (frame["frame_hash"],))
                return {"status": "duplicate", "frame_hash": frame["frame_hash"]}
            require(actor in registry.active, "actor-inactive")
            require(frame["stream_id"] in registry.genesis, "stream-unregistered")
            if frame["stream_id"] == self.anchors[hive].authority_stream:
                require(actor == self.anchors[hive].owner_rappid, "owner-required")
            self._bind_stream(frame, registry)
            rival = self.db.execute("SELECT raw FROM frames WHERE stream=? AND seq=?",
                                    (frame["stream_id"], frame["seq"])).fetchone()
            if rival is not None:
                code = "sovereign-fork" if frame["stream_id"] == self.anchors[hive].authority_stream else "stream-fork"
                require(memory_owner(frame["stream_id"]) == actor, "stream-key-binding")
                self._record_stream_fork(frame, loads(rival[0]), code)
                fault = Refusal(code)
            else:
                head = self.db.execute("SELECT raw FROM frames WHERE stream=? ORDER BY seq DESC LIMIT 1",
                                       (frame["stream_id"],)).fetchone()
                verify_chain(frame, loads(head[0]) if head else None, registry.genesis[frame["stream_id"]])
                self._require_unforked(frame, dependencies=not historical)
                if frame["seq"] == 0:
                    status = "recorded"
                else:
                    if kind not in {"checkpoint", "discovery"}:
                        self._context(payload, allow_historical=kind == "receipt"
                                      and payload.get("phase") in {"completed", "failed"})
                    status = getattr(self, "_" + kind)(frame) or "recorded"
                self.db.execute("INSERT INTO frames VALUES (?, ?, ?, ?, ?, ?)",
                                (frame["frame_hash"], frame["stream_id"], frame["seq"], frame["kind"],
                                 hive, canonical(frame)))
                self.db.execute("DELETE FROM pending WHERE hash=?", (frame["frame_hash"],))
        if fault is not None:
            raise fault
        return {"status": status, "frame_hash": frame["frame_hash"]}

    def _genesis(self, frame):
        payload = frame["payload"]
        hive, actor = self.issuer(payload)
        require(memory_owner(frame["stream_id"]) == actor, "stream-key-binding")
        is_authority = frame["stream_id"] == self.anchors[hive].authority_stream
        require((payload["stream_role"] == "authority") == is_authority, "competing-authorities")
        if is_authority:
            require(actor == self.anchors[hive].owner_rappid, "owner-required")

    def _checkpoint(self, frame):
        payload = frame["payload"]
        hive = self._party(payload["issuer"])
        require(frame["stream_id"] == self.anchors[hive].authority_stream
                and payload["issuer"]["actor_rappid"] == self.anchors[hive].owner_rappid, "owner-required")
        self._require_dependencies(payload, [payload["previous_checkpoint"], *payload["controls"]])
        current = self.latest("authority", hive)
        require(payload["previous_checkpoint"] == current, "authority-rollback")
        previous = self.payload(current, "checkpoint") if current else None
        require(payload["authority_seq"] == (previous["authority_seq"] + 1 if previous else 1),
                "authority-sequence")
        registry = self.registry(hive)
        require(payload["registry_hash"] == registry.commitment
                and payload["registry_seq"] == registry.sequence, "registry-stale")
        head = payload["hive_head"]
        require(head["stream_id"] == hive, "foreign-dimension")
        if previous is None:
            require(head["seq"] == 0 and head["prev"] is None
                    and head["frame_hash"] == registry.genesis[hive], "hive-head-genesis")
        else:
            old = previous["hive_head"]
            if head["seq"] == old["seq"]:
                require(head == old, "competing-sovereign-heads")
            else:
                require(head["seq"] == old["seq"] + 1 and head["prev"] == old["payload_hash"]
                        and head["utc"] >= old["utc"], "hive-head-lineage")
        require(payload["issued_utc"] == frame["utc"], "checkpoint-time")
        start, end = stamp_ms(payload["issued_utc"]), stamp_ms(payload["valid_until_utc"])
        require(start < end, "checkpoint-window")
        require(payload["offline_horizon_ms"] <= end - start, "checkpoint-offline-horizon")
        known_controls = {row[0] for row in self.db.execute("SELECT hash FROM controls WHERE hive=?", (hive,))}
        require(set(payload["controls"]) == known_controls, "control-frontier")
        self.db.execute("INSERT OR REPLACE INTO authority VALUES (?, ?)", (hive, frame["frame_hash"]))

    def approve_dogg(self, content_hash: str, evidence_hash: str):
        """Local publisher/auditor decision over the entire unsigned public frame."""
        require(all(type(value) is str and len(value) == 64
                    and all(char in "0123456789abcdef" for char in value)
                    for value in (content_hash, evidence_hash)), "dogg-approval-hash")
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO dogg_approvals VALUES (?, ?)", (content_hash, evidence_hash))

    def _discovery(self, frame):
        payload = frame["payload"]
        require(chat_url(payload["endpoint"]), "discovery-endpoint")
        require(stamp_ms(payload["expires_utc"]) > stamp_ms(frame["utc"]), "discovery-expiry")
        approved = self.db.execute("SELECT 1 FROM dogg_approvals WHERE content_hash=? AND evidence_hash=?",
                                   (H("rapp/1:particle", unsigned(frame)),
                                    payload["publication_evidence_hash"])).fetchone()
        require(approved is not None, "dogg-unapproved")
        self._window(frame["utc"], payload["expires_utc"])
        return "discovery-only"

    def _peer(self, frame):
        payload = frame["payload"]
        hive = payload["issuer"]["hive_rappid"]
        peer = payload["peer"]
        require(peer["hive_rappid"] in self.anchors and peer["hive_rappid"] != hive, "peer-cell")
        require(peer["world_id"] == self.anchors[peer["hive_rappid"]].world_id, "wrong-world")
        self._require_dependencies(payload, [payload["checkpoint"]])
        require(stamp_ms(payload["not_before"]) < stamp_ms(payload["not_after"]), "peer-window")

    def _policy(self, frame):
        payload = frame["payload"]
        hive = payload["issuer"]["hive_rappid"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["previous_policy"]])
        current = self.latest("policies", hive)
        require(payload["previous_policy"] == current, "policy-rollback")
        previous = self.payload(current, "policy") if current else None
        require(payload["policy_seq"] == (previous["policy_seq"] + 1 if previous else 1), "policy-sequence")
        require(set(payload["allowed_actors"]) <= self.registry(hive).active, "policy-actors")
        require(hive not in payload["allowed_peers"]
                and set(payload["allowed_peers"]) <= set(self.anchors), "policy-peers")
        require(payload["max_units"] <= payload["max_total_units"], "policy-budget")
        if "offline-bounded" in payload["modes"]:
            require(payload["max_offline_ms"] > 0 and payload["offline_revocation"] == "lease-limited",
                    "offline-risk-policy")
        self.db.execute("INSERT OR REPLACE INTO policies VALUES (?, ?)", (hive, frame["frame_hash"]))

    def _grant(self, frame):
        payload = frame["payload"]
        hive = payload["issuer"]["hive_rappid"]
        target = self._party(payload["recipient"])
        require(target != hive, "grant-not-foreign")
        self._require_dependencies(payload, [payload["checkpoint"], payload["policy"]])
        policy = self.payload(payload["policy"], "policy")
        require(policy["issuer"]["hive_rappid"] == hive
                and payload["policy"] == self.latest("policies", hive), "grant-policy")
        require(target in policy["allowed_peers"], "grant-peer-policy")
        require(set(payload["actions"]) <= set(policy["actions"])
                and set(payload["modes"]) <= set(policy["modes"]), "grant-widened")
        for limit in ("max_units", "max_total_units", "max_uses", "max_offline_ms"):
            require(payload[limit] <= policy[limit], "grant-widened")
        require(payload["max_units"] <= payload["max_total_units"], "grant-budget")
        require(stamp_ms(payload["not_before"]) < stamp_ms(payload["not_after"]), "grant-window")
        require(payload["resource"]["artifact_rappid"] in self.registry(hive).active
                and payload["resource"]["key_service_rappid"] in self.registry(hive).active, "grant-resource-key")
        if "offline-bounded" in payload["modes"]:
            require(payload["max_offline_ms"] > 0 and payload["offline_revocation"] == "lease-limited"
                    and policy["offline_revocation"] == "lease-limited", "offline-risk-grant")
        existing = self.db.execute("SELECT hash FROM grants WHERE hive=? AND grant_id=?",
                                   (hive, payload["grant_id"])).fetchone()
        require(existing is None, "grant-id-reuse")
        self.db.execute("INSERT INTO grants VALUES (?, ?, ?)", (hive, payload["grant_id"], frame["frame_hash"]))

    def _terms(self, terms):
        source, destination = self._party(terms["source"]), self._party(terms["destination"])
        require(source != destination, "foreign-hive-required")
        grant = self.payload(terms["grant"], "grant")
        require(grant["issuer"]["hive_rappid"] == source
                and grant["recipient"] == terms["destination"], "grant-recipient")
        require(grant["resource"] == terms["resource"], "grant-resource")
        require(terms["source_policy"] == grant["policy"], "grant-policy")
        source_policy = self.payload(terms["source_policy"], "policy")
        destination_policy = self.payload(terms["destination_policy"], "policy")
        for hive, party, peer, policy, address in (
            (source, terms["source"], destination, source_policy, terms["source_policy"]),
            (destination, terms["destination"], source, destination_policy, terms["destination_policy"]),
        ):
            require(policy["issuer"]["hive_rappid"] == hive and address == self.latest("policies", hive),
                    "policy-stale")
            require(party["actor_rappid"] in policy["allowed_actors"]
                    and peer in policy["allowed_peers"], "party-policy")
            require(terms["action"] in policy["actions"] and terms["mode"] in policy["modes"],
                    "terms-policy")
            require(terms["units"] <= policy["max_units"], "terms-budget")
            require(not terms["irreversible"] or policy["allow_irreversible"], "irreversible-policy")
        require(terms["action"] in grant["actions"] and terms["mode"] in grant["modes"], "grant-widened")
        require(terms["units"] <= grant["max_units"], "grant-widened")
        require(stamp_ms(grant["not_before"]) <= stamp_ms(terms["not_before"])
                < stamp_ms(terms["not_after"]) <= stamp_ms(grant["not_after"]), "grant-window-widened")
        if terms["mode"] == "offline-bounded":
            require(terms["offline_risk_ack"] and grant["offline_revocation"] == "lease-limited"
                    and all(policy["offline_revocation"] == "lease-limited"
                            for policy in (source_policy, destination_policy)), "offline-risk-unacknowledged")
            require(not terms["irreversible"], "offline-irreversible")
        else:
            require(terms["offline_risk_ack"] is False, "offline-risk-mode")
        return grant, source_policy, destination_policy

    def _agreement(self, frame):
        payload = frame["payload"]
        terms = payload["terms"]
        self._require_dependencies(payload, [
            payload["checkpoint"], payload["source_peer"], payload["destination_peer"],
            terms["grant"], terms["source_policy"], terms["destination_policy"],
        ])
        require(payload["issuer"] == terms["source"], "agreement-proposer")
        require(payload["terms_hash"] == H("rapp/1:particle", terms), "terms-hash")
        self._terms(terms)
        source_peer = self.payload(payload["source_peer"], "peer")
        destination_peer = self.payload(payload["destination_peer"], "peer")
        for peer, here, there in ((source_peer, terms["source"], terms["destination"]),
                                  (destination_peer, terms["destination"], terms["source"])):
            require(peer["issuer"]["hive_rappid"] == here["hive_rappid"]
                    and peer["peer"] == {key: there[key] for key in ("hive_rappid", "world_id")},
                    "peer-consent-bilateral")
            require(stamp_ms(peer["not_before"]) <= stamp_ms(terms["not_before"])
                    and stamp_ms(terms["not_after"]) <= stamp_ms(peer["not_after"]), "peer-consent-window")

    def _approval(self, frame):
        payload = frame["payload"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["target"]])
        target = self.frame(payload["target"], payload["scope"])
        terms = target["payload"]["terms"]
        require(payload["issuer"] == terms["destination"], "approval-destination")
        expected = target["payload"]["terms_hash"] if payload["scope"] == "agreement" else target["payload_hash"]
        require(payload["commitment"] == expected, "approval-commitment")
        self._terms(terms)
        existing = self.db.execute("SELECT hash FROM approvals WHERE scope=? AND target=?",
                                   (payload["scope"], payload["target"])).fetchone()
        require(existing is None, "approval-conflict")
        self.db.execute("INSERT INTO approvals VALUES (?, ?, ?)",
                        (payload["scope"], payload["target"], frame["frame_hash"]))

    def _request(self, frame):
        payload = frame["payload"]
        terms = payload["terms"]
        self._require_dependencies(payload, [
            payload["checkpoint"], payload["destination_checkpoint"], payload["agreement"],
            payload["agreement_approval"], payload["supersedes"],
            terms["grant"], terms["source_policy"], terms["destination_policy"],
        ])
        require(payload["issuer"] == terms["source"], "request-proposer")
        require(terms["destination"]["hive_rappid"] == self.local_hive, "wrong-recipient-hive")
        self._terms(terms)
        agreement = self.payload(payload["agreement"], "agreement")
        require(terms == agreement["terms"], "request-terms-changed")
        approval = self.payload(payload["agreement_approval"], "approval")
        require(approval["scope"] == "agreement" and approval["target"] == payload["agreement"]
                and approval["decision"] == "accept" and approval["issuer"] == terms["destination"],
                "one-sided-agreement")
        destination_checkpoint = self.payload(payload["destination_checkpoint"], "checkpoint")
        require(destination_checkpoint["phase"] == "authority" and
                destination_checkpoint["issuer"]["hive_rappid"] == self.local_hive, "checkpoint-recipient")
        if terms["mode"] != "online-confirmed":
            require(payload["challenge"] is None, "challenge-mode")
        else:
            require(payload["challenge"] is not None, "challenge-required")
        if payload["supersedes"] is not None:
            previous = self.payload(payload["supersedes"], "request")
            require(previous["terms"]["mode"] == "deferred" and previous["issuer"] == payload["issuer"]
                    and previous["terms"]["destination"] == terms["destination"]
                    and previous["request_id"] != payload["request_id"], "deferred-supersession")
        row = self.db.execute("SELECT payload_hash FROM requests WHERE source=? AND request_id=?",
                              (terms["source"]["hive_rappid"], payload["request_id"])).fetchone()
        if row:
            require(row[0] == frame["payload_hash"], "request-id-payload-replay")
            return "duplicate-request"
        self.db.execute("INSERT INTO requests(source, request_id, frame_hash, payload_hash) VALUES (?, ?, ?, ?)",
                        (terms["source"]["hive_rappid"], payload["request_id"],
                         frame["frame_hash"], frame["payload_hash"]))
        return "deferred" if terms["mode"] == "deferred" else "request-pending-destination"

    def _window(self, start, end, max_uncertainty=None):
        bounds = self._clock.bounds()
        require(bounds is not None, "clock-uncertain")
        lower, upper = bounds
        if max_uncertainty is not None:
            require(upper - lower <= max_uncertainty, "clock-uncertain")
        start, end = stamp_ms(start), stamp_ms(end)
        require(lower < end, "expired")
        require(upper >= start, "not-yet-valid")
        require(start <= lower and upper < end, "clock-uncertain")
        return lower, upper

    def issue_challenge(self, terms, *, ttl_ms=60000, nonce=None):
        validate(terms, "terms")
        require(terms["destination"]["hive_rappid"] == self.local_hive
                and terms["mode"] == "online-confirmed", "challenge-destination")
        bounds = self._clock.bounds()
        require(bounds is not None and type(ttl_ms) is int and 0 < ttl_ms <= 300000, "challenge-clock")
        nonce = nonce or secrets.token_hex(32)
        require(type(nonce) is str and len(nonce) == 64
                and all(char in "0123456789abcdef" for char in nonce), "challenge-nonce")
        with self.transaction():
            require(not self.db.execute("SELECT 1 FROM challenges WHERE nonce=?", (nonce,)).fetchone(),
                    "challenge-reuse")
            self.db.execute("INSERT INTO challenges VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                            (nonce, terms["source"]["hive_rappid"], self.local_hive,
                             terms["destination"]["actor_rappid"], H("rapp/1:particle", terms),
                             bounds[1], bounds[1] + ttl_ms))
        return nonce

    def _not_revoked(self, request):
        payload, terms = request["payload"], request["payload"]["terms"]
        for kind, target in (("grant", terms["grant"]), ("agreement", payload["agreement"]),
                             ("request", request["frame_hash"])):
            require(not self.db.execute("SELECT 1 FROM revoked WHERE kind=? AND target=?", (kind, target)).fetchone(),
                    "revoked")
        source, destination = terms["source"]["hive_rappid"], terms["destination"]["hive_rappid"]
        require(not self.db.execute("SELECT 1 FROM blocked WHERE (hive=? AND peer=?) OR (hive=? AND peer=?)",
                                    (source, destination, destination, source)).fetchone(), "peer-blocked")

    def _ready(self, request):
        payload, terms = request["payload"], request["payload"]["terms"]
        require(terms["mode"] != "deferred", "deferred-no-execution")
        require(not self.db.execute("SELECT 1 FROM authority_faults WHERE hive IN (?, ?)",
                                    (terms["source"]["hive_rappid"], terms["destination"]["hive_rappid"])).fetchone(),
                "authority-equivocation")
        self._require_unforked(request)
        row = self._request_row(request)
        if row["receipt"] is not None:
            self._require_unforked(self.frame(row["receipt"], "receipt"))
        self._not_revoked(request)
        grant, source_policy, destination_policy = self._terms(terms)
        source_checkpoint = self._context(payload)
        destination_checkpoint = self.payload(payload["destination_checkpoint"], "checkpoint")
        source, destination = terms["source"]["hive_rappid"], terms["destination"]["hive_rappid"]
        for hive, checkpoint in ((source, source_checkpoint), (destination, destination_checkpoint)):
            registry = self.registry(hive)
            require(checkpoint["phase"] == "authority" and checkpoint["issuer"]["hive_rappid"] == hive
                    and checkpoint["registry_hash"] == registry.commitment
                    and checkpoint["registry_seq"] == registry.sequence, "registry-stale")
        max_uncertainty = min(source_policy["max_clock_uncertainty_ms"], destination_policy["max_clock_uncertainty_ms"],
                              source_checkpoint["max_clock_uncertainty_ms"],
                              destination_checkpoint["max_clock_uncertainty_ms"])
        lower, upper = self._window(terms["not_before"], terms["not_after"], max_uncertainty)
        for checkpoint in (source_checkpoint, destination_checkpoint):
            self._window(checkpoint["issued_utc"], checkpoint["valid_until_utc"], max_uncertainty)
        if terms["mode"] == "offline-bounded":
            horizon = min(grant["max_offline_ms"], source_policy["max_offline_ms"],
                          destination_policy["max_offline_ms"], source_checkpoint["offline_horizon_ms"],
                          destination_checkpoint["offline_horizon_ms"])
            require(horizon > 0 and all(upper - stamp_ms(checkpoint["issued_utc"]) <= horizon
                    for checkpoint in (source_checkpoint, destination_checkpoint)), "offline-authority-stale")
        else:
            require(self.latest("authority", source) == payload["checkpoint"]
                    and self.latest("authority", destination) == payload["destination_checkpoint"],
                    "online-checkpoint-stale")
            nonce = payload["challenge"]
            challenge = self.db.execute("SELECT * FROM challenges WHERE nonce=?", (nonce,)).fetchone()
            require(challenge is not None and challenge["source"] == source
                    and challenge["destination"] == destination
                    and challenge["actor"] == terms["destination"]["actor_rappid"]
                    and challenge["intent_hash"] == H("rapp/1:particle", terms), "online-unconfirmed")
            require(challenge["issued"] <= lower <= upper < challenge["expires"], "online-challenge-expired")
            require(challenge["used_by"] in (None, request["frame_hash"]), "challenge-replay")
            require(all(checkpoint["challenge"] == nonce
                        and stamp_ms(checkpoint["issued_utc"]) >= challenge["issued"]
                        for checkpoint in (source_checkpoint, destination_checkpoint)), "online-unconfirmed")
        effective = dict(grant)
        for limit in ("max_uses", "max_total_units"):
            effective[limit] = min(grant[limit], source_policy[limit], destination_policy[limit])
        return effective

    def _request_row(self, request):
        payload = request["payload"]
        row = self.db.execute("SELECT * FROM requests WHERE source=? AND request_id=?",
                              (payload["issuer"]["hive_rappid"], payload["request_id"])).fetchone()
        require(row is not None and row["frame_hash"] == request["frame_hash"], "request-original-required")
        return row

    def _receipt(self, frame):
        payload = frame["payload"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["request"], payload["prior"],
                                             payload["approval"], payload["source_checkpoint"]])
        request = self.frame(payload["request"], "request")
        terms = request["payload"]["terms"]
        require(payload["issuer"] == terms["destination"] and
                payload["request_id"] == request["payload"]["request_id"], "receipt-recipient")
        require(payload["checkpoint"] == request["payload"]["destination_checkpoint"]
                and payload["source_checkpoint"] == request["payload"]["checkpoint"], "receipt-authority-context")
        row = self._request_row(request)
        require(payload["prior"] == row["receipt"] and payload["phase"] in TRANSITIONS[row["phase"]],
                "receipt-phase")
        phase = payload["phase"]
        Clock(payload["clock_basis"]["lower_utc"], payload["clock_basis"]["upper_utc"]).bounds()
        if phase in {"accepted", "executing", "completed", "failed"}:
            require(payload["approval"] is not None, "destination-acceptance-required")
            approval = self.payload(payload["approval"], "approval")
            require(approval["scope"] == "request" and approval["target"] == request["frame_hash"]
                    and approval["decision"] == "accept" and approval["issuer"] == terms["destination"],
                    "destination-acceptance-required")
        else:
            require(payload["approval"] is None, "receipt-unexpected-approval")
        if phase in {"accepted", "executing"}:
            require(self._persistent, "durable-store-required")
            grant = self._ready(request)
            require(payload["clock_basis"] == {"lower_utc": self._clock.lower, "upper_utc": self._clock.upper},
                    "receipt-clock-basis")
            if phase == "accepted":
                require(not row["reserved"], "execution-already-reserved")
                usage = self.db.execute("SELECT uses, units FROM usage WHERE grant_hash=?",
                                        (terms["grant"],)).fetchone()
                uses, units = (usage[0], usage[1]) if usage else (0, 0)
                require(uses + 1 <= grant["max_uses"] and units + terms["units"] <= grant["max_total_units"],
                        "grant-budget-exhausted")
                self.db.execute("INSERT OR REPLACE INTO usage VALUES (?, ?, ?)",
                                (terms["grant"], uses + 1, units + terms["units"]))
                self.db.execute("UPDATE requests SET reserved=1 WHERE source=? AND request_id=?",
                                (row["source"], row["request_id"]))
                if terms["mode"] == "online-confirmed":
                    self.db.execute("UPDATE challenges SET used_by=? WHERE nonce=?",
                                    (request["frame_hash"], request["payload"]["challenge"]))
        expected_assurance = ("online-confirmed" if terms["mode"] == "online-confirmed" else "offline-authorized"
                              ) if phase in {"accepted", "executing"} else (
            "indeterminate" if phase == "failed" else "known-revoked" if payload["reason"] == "revoked"
            else "authority-unavailable" if payload["reason"] in {"clock", "dependency"} else "historical-snapshot")
        require(payload["assurance"] == expected_assurance, "receipt-assurance")
        if payload["assurance"] == "known-revoked":
            known = False
            try:
                self._not_revoked(request)
            except Refusal:
                known = True
            source_registry = self.registry(terms["source"]["hive_rappid"])
            destination_registry = self.registry(terms["destination"]["hive_rappid"])
            known = known or bool(source_registry.revoked & {
                terms["source"]["actor_rappid"], terms["resource"]["artifact_rappid"],
                terms["resource"]["key_service_rappid"],
            }) or terms["destination"]["actor_rappid"] in destination_registry.revoked
            require(known, "receipt-assurance")
        require(payload["units"] <= terms["units"], "receipt-budget")
        if phase not in {"completed", "failed"}:
            require(payload["units"] == 0 and payload["result"] is None, "receipt-premature-result")
        if phase == "completed":
            require(row["opened"] == 1 and row["local_status"] == "opened", "execution-not-observed")
        require((payload["reason"] != "none") == (phase in {"rejected", "failed"}), "receipt-reason")
        self.db.execute("UPDATE requests SET phase=?, receipt=? WHERE source=? AND request_id=?",
                        (phase, frame["frame_hash"], row["source"], row["request_id"]))
        return "business-" + phase

    def _control(self, frame):
        payload = frame["payload"]
        hive = payload["issuer"]["hive_rappid"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["target_hash"]])
        row = self.db.execute("SELECT MAX(sequence) FROM controls WHERE hive=?", (hive,)).fetchone()
        require(payload["control_seq"] == (row[0] or 0) + 1, "control-sequence")
        if payload["action"] == "block":
            require(payload["target_kind"] == "peer" and payload["target_hash"] is None
                    and payload["peer_hive"] in self.anchors and payload["peer_hive"] != hive, "block-scope")
            self.db.execute("INSERT OR IGNORE INTO blocked VALUES (?, ?, ?)",
                            (hive, payload["peer_hive"], frame["frame_hash"]))
        else:
            require(payload["target_hash"] is not None and payload["peer_hive"] is None, "control-scope")
            target = self.payload(payload["target_hash"], payload["target_kind"])
            if payload["action"] == "revoke":
                require(payload["target_kind"] in {"grant", "agreement"}
                        and target["issuer"]["hive_rappid"] == hive, "revocation-authority")
            else:
                require(payload["action"] == "cancel" and payload["target_kind"] == "request"
                        and hive in {target["terms"]["source"]["hive_rappid"],
                                     target["terms"]["destination"]["hive_rappid"]}, "cancel-authority")
            self.db.execute("INSERT OR IGNORE INTO revoked VALUES (?, ?, ?)",
                            (payload["target_kind"], payload["target_hash"], frame["frame_hash"]))
        self.db.execute("INSERT INTO controls VALUES (?, ?, ?)", (hive, payload["control_seq"], frame["frame_hash"]))
        return "control-recorded"

    def open_request(self, request_hash: str, egg: bytes, key_service):
        """Use authorized local material once; native ECDH key acquisition is outside this reference."""
        require(self._persistent, "durable-store-required")
        require(callable(key_service), "key-service-required")
        with self.transaction():
            request = self.frame(request_hash, "request")
            row = self._request_row(request)
            require(row["phase"] == "executing" and row["reserved"] == 1, "execution-not-authorized")
            require(row["opened"] == 0, "execution-already-opened")
            self._ready(request)
            terms = request["payload"]["terms"]
            registry = self.registry(terms["source"]["hive_rappid"])
            resource = terms["resource"]
            require(resource["artifact_rappid"] in registry.active
                    and resource["key_service_rappid"] in registry.active, "resource-key-revoked")
            manifest, ciphertext = inspect_sealed(egg, resource["hash"], registry.keys)
            require(manifest["rappid"] == resource["artifact_rappid"]
                    and manifest["payload"]["key_service_rappid"] == resource["key_service_rappid"],
                    "resource-key-service")
            permit = ReleasePermit(
                request_hash, request["payload"]["request_id"], terms["grant"],
                terms["source"]["hive_rappid"], terms["destination"]["hive_rappid"],
                terms["destination"]["world_id"], terms["destination"]["actor_rappid"],
                resource["hash"], manifest["payload"]["key_id"], resource["key_service_rappid"], terms["mode"],
                terms["action"], terms["units"], terms["not_before"], terms["not_after"],
                request["payload"]["checkpoint"], request["payload"]["destination_checkpoint"],
                registry.commitment, self.registry(terms["destination"]["hive_rappid"]).commitment,
            )
            self.db.execute("UPDATE requests SET opened=1, local_status='in-doubt' WHERE source=? AND request_id=?",
                            (row["source"], row["request_id"]))
            self.db.execute("INSERT INTO execution_attempts VALUES (?, ?)",
                            (request_hash, H("rapp/1:particle", asdict(permit))))
        plaintext = decrypt_sealed(manifest, ciphertext, key_service(permit))
        with self.transaction():
            self.db.execute("UPDATE requests SET local_status='opened' WHERE source=? AND request_id=?",
                            (row["source"], row["request_id"]))
        return plaintext

    def _closure(self, address):
        result, stack = set(), [address]
        while stack:
            current = stack.pop()
            if current in result:
                continue
            result.add(current)
            frame = self.frame(current)
            stack.extend(frame["payload"].get("depends_on", []))
            if frame["seq"] > 0:
                row = self.db.execute("SELECT hash FROM frames WHERE stream=? AND seq=?",
                                      (frame["stream_id"], frame["seq"] - 1)).fetchone()
                require(row is not None, "dependency-missing")
                stack.append(row[0])
        return result

    def _bundle(self, frame):
        payload = frame["payload"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["request"]])
        request = self.payload(payload["request"], "request")
        require(payload["issuer"] == request["issuer"]
                and payload["destination"] == request["terms"]["destination"], "bundle-destination")
        require(stamp_ms(frame["utc"]) < stamp_ms(payload["expires_utc"])
                <= stamp_ms(request["terms"]["not_after"]), "bundle-expiry")
        items = payload["items"]
        require(items == sorted(items, key=lambda item: (item["space"], item["hash"])), "bundle-item-order")
        addresses = {(item["space"], item["hash"]) for item in items}
        require(len(addresses) == len(items) and sum(item["bytes"] for item in items) <= 8 * (1 << 20),
                "bundle-size")
        required = {("rapp/1:wave", payload["request"]),
                    ("rapp/1:egg-manifest", request["terms"]["resource"]["hash"])}
        require(required <= addresses
                and all(item["essential"] for item in items if (item["space"], item["hash"]) in required),
                "bundle-essential")
        allowed = {("rapp/1:wave", value) for value in self._closure(payload["request"])} | required
        require(addresses <= allowed, "bundle-unrelated-content")
        hive = payload["issuer"]["hive_rappid"]
        old = self.db.execute("SELECT hash FROM bundles WHERE hive=? AND bundle_id=?",
                              (hive, payload["bundle_id"])).fetchone()
        require(old is None, "bundle-id-replay")
        self.db.execute("INSERT INTO bundles VALUES (?, ?, ?)", (hive, payload["bundle_id"], frame["frame_hash"]))
        return "bundle-manifest-only"

    def verify_bundle_contents(self, bundle_hash, artifacts):
        with self._lock:
            bundle = self.payload(bundle_hash, "bundle")
            expected = {(item["space"], item["hash"]) for item in bundle["items"]}
            require(set(artifacts) == expected, "bundle-inventory")
            request = self.payload(bundle["request"], "request")
            for item in bundle["items"]:
                raw = artifacts[(item["space"], item["hash"])]
                require(type(raw) is bytes and len(raw) == item["bytes"], "bundle-bytes")
                require(hashlib.sha256(raw).hexdigest() == item["octets_sha256"], "bundle-octets")
                if item["space"] == "rapp/1:wave":
                    candidate = validate(loads(raw))
                    require(raw == canonical(candidate), "frame-noncanonical")
                    hive, actor = self.issuer(candidate["payload"])
                    require(verify_frame(candidate, self.registry(hive).keys) == actor, "bundle-signer")
                    require(candidate["frame_hash"] == item["hash"], "bundle-address")
                    require(canonical(candidate) == canonical(self.frame(item["hash"])), "bundle-frame-substitution")
                else:
                    manifest, _ = inspect_sealed(raw, item["hash"],
                                                self.registry(request["terms"]["source"]["hive_rappid"]).keys)
                    require(manifest["rappid"] == request["terms"]["resource"]["artifact_rappid"],
                            "bundle-artifact")
        return {"status": "content-verified", "execution_authorized": False}

    def _custody(self, frame):
        payload = frame["payload"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["bundle"], payload["previous_custody"]])
        bundle = self.payload(payload["bundle"], "bundle")
        require(payload["hop"] <= bundle["max_hops"], "custody-hop-limit")
        require((payload["status"] == "forwarded") == (payload["next_custodian"] is not None), "custody-next")
        if payload["previous_custody"] is None:
            require(payload["hop"] == 0 and payload["status"] in {"stored", "refused", "expired"},
                    "custody-genesis")
        else:
            previous = self.payload(payload["previous_custody"], "custody")
            require(previous["bundle"] == payload["bundle"], "custody-bundle")
            if previous["status"] == "stored":
                require(previous["issuer"] == payload["issuer"] and payload["hop"] == previous["hop"]
                        and payload["status"] in {"forwarded", "expired"}, "custody-transition")
            else:
                require(previous["status"] == "forwarded" and payload["hop"] == previous["hop"] + 1
                        and previous["next_custodian"] == payload["issuer"]["actor_rappid"]
                        and payload["status"] in {"stored", "refused", "expired"}, "custody-transition")
        return "custody-only"

    def _observation(self, frame):
        payload = frame["payload"]
        self._require_dependencies(payload, [payload["checkpoint"], payload["subject"]])
        self.frame(payload["subject"])
        Clock(payload["clock_lower"], payload["clock_upper"]).bounds()
        require((payload["status"] == "pending-dependencies") == bool(payload["missing"]), "observation-missing")
        return "observation-only"

    def stage(self, raw: bytes):
        """Durable dependency waiting; no policy, ledger, or sovereign-head effect."""
        frame = validate(loads(raw))
        require(raw == canonical(frame), "frame-noncanonical")
        hive, actor = self.issuer(frame["payload"])
        with self.transaction():
            require(verify_frame(frame, self.registry(hive).keys) == actor, "issuer-signature")
            old = self.db.execute("SELECT raw FROM pending WHERE hash=?", (frame["frame_hash"],)).fetchone()
            require(old is None or old[0] == canonical(frame), "frame-substitution")
            self.db.execute("INSERT OR IGNORE INTO pending VALUES (?, ?)", (frame["frame_hash"], canonical(frame)))
        return {"status": "staged-unaccepted", "frame_hash": frame["frame_hash"]}

    def drain(self):
        progress, accepted, quarantined = True, [], []
        while progress:
            progress = False
            rows = [loads(row[0]) for row in self.db.execute("SELECT raw FROM pending")]
            for frame in sorted(rows, key=lambda item: (item["utc"], item["frame_hash"])):
                try:
                    result = self.accept(canonical(frame))
                except Refusal as error:
                    if error.code not in {"dependency-missing", "frame-chain", "frame-genesis"}:
                        with self.transaction():
                            self.db.execute("INSERT OR REPLACE INTO quarantine VALUES (?, ?, ?)",
                                            (frame["frame_hash"], canonical(frame), error.code))
                            self.db.execute("DELETE FROM pending WHERE hash=?", (frame["frame_hash"],))
                        quarantined.append({"frame_hash": frame["frame_hash"], "refusal": error.code})
                        progress = True
                else:
                    accepted.append(result["frame_hash"])
                    progress = True
        return {"accepted": accepted, "quarantined": quarantined,
                "pending": self.db.execute("SELECT COUNT(*) FROM pending").fetchone()[0]}

    def history(self):
        frames = [loads(row[0]) for row in self.db.execute("SELECT raw FROM frames")]
        return sorted(frames, key=lambda frame: (frame["utc"], frame["frame_hash"]))

    def status(self, request_hash):
        with self._lock:
            row = self._request_row(self.frame(request_hash, "request"))
            return {key: row[key] for key in ("frame_hash", "phase", "receipt", "reserved", "opened", "local_status")}
