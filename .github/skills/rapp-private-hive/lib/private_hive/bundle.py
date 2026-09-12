from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .authority import FILE_KIND, INVENTORY_KIND, INVENTORY_TARGET, authenticated_registry
from .common import H, R, HiveAcceptance, MAX_ARTIFACTS, MAX_BUNDLE_BYTES, MAX_FILE_BYTES, MAX_FILES, artifact_path, canonical, chain_path, digest, exact_keys, hex64, parse, particle, relative, require, safe_path_set, timestamp, unb64
from .keys import verify_anchor, verify_signed
from .adapters.filesystem import publication_path


def pii_receipt(receipt, content_hash, at_utc, trusted_scanners=None):
    exact_keys(receipt, {"schema", "file_sha256", "result", "scanner_rappid", "scanner_version",
                         "scanned_utc", "spki_der_b64", "sig"}, "PII receipt")
    require(receipt["schema"] == "rapp-pii-scan/1" and receipt["result"] == "none"
            and receipt["file_sha256"] == content_hash, "PII receipt does not clear these exact bytes")
    require(isinstance(receipt["scanner_version"], str) and 0 < len(receipt["scanner_version"]) <= 128,
            "invalid scanner version")
    spki = unb64(receipt["spki_der_b64"])
    ok, why = R.verify_detached_jws({key: value for key, value in receipt.items() if key != "sig"},
                                   receipt["sig"], spki, receipt["scanner_rappid"])
    require(ok, "PII receipt signature refused: " + why)
    if trusted_scanners is not None:
        require(trusted_scanners.get(receipt["scanner_rappid"]) == digest(spki), "PII scanner is not explicitly trusted")
    def date(value):
        return datetime.strptime(timestamp(value), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    require(0 <= (date(at_utc) - date(receipt["scanned_utc"])).total_seconds() <= 86400,
            "PII scan must precede its signed publication by at most 24 hours")
    return digest(canonical(receipt))


def decode_file(value, descriptor, stamp):
    exact_keys(value, {"schema", "encoding", "bytes", "sha256", "content_base64", "pii_receipt"}, "file particle")
    require(value["schema"] == "rapp-private-hive-file/1" and value["encoding"] == "base64",
            "unsupported file particle schema or encoding")
    require(type(value["bytes"]) is int and 0 <= value["bytes"] <= MAX_FILE_BYTES, "file particle byte limit")
    data = unb64(value["content_base64"])
    require(len(data) == value["bytes"] and digest(data) == value["sha256"], "file particle content mismatch")
    require(descriptor["data_class"] in {"dogg", "neutral"} and descriptor["pii_status"] == "none"
            and descriptor["protection"] == "member-visible", "plaintext GODD or uncleared content refused")
    require(pii_receipt(value["pii_receipt"], value["sha256"], stamp) == descriptor["pii_evidence_hash"],
            "signed PII evidence commitment mismatch")
    return data


def table(files: dict[str, bytes]) -> list[dict]:
    require(len(files) <= MAX_ARTIFACTS and sum(map(len, files.values())) <= MAX_BUNDLE_BYTES, "bundle limit")
    return [{"path": path, "bytes": len(raw), "sha256": digest(raw)} for path, raw in sorted(files.items())]


def validate_table(entries):
    require(isinstance(entries, list) and len(entries) <= MAX_ARTIFACTS, "release index entry limit")
    order, size = [], 0
    for entry in entries:
        exact_keys(entry, {"path", "bytes", "sha256"}, "release index entry")
        order.append(publication_path(entry["path"]))
        require(type(entry["bytes"]) is int and 0 <= entry["bytes"] <= R.MAX_CANONICAL_BYTES, "artifact byte limit")
        size += entry["bytes"]
        hex64(entry["sha256"])
    require(order == sorted(set(order)) and size <= MAX_BUNDLE_BYTES, "release index ordering or total byte limit")
    return entries


def index_bytes(files):
    return canonical({"schema": "rapp-private-hive-release-index/1", "files": table(files)})


def index_path(address):
    return "manifests/releases/" + hex64(address) + ".json"


class Resolver:
    def __init__(self, files):
        self.files = files
        self.chains = {}

    def artifact(self, space, address):
        return self.files[artifact_path(space, address)]

    def chain(self, address):
        if address not in self.chains:
            record = parse(self.files[chain_path(address)], "chain index")
            exact_keys(record, {"schema", "stream_id", "frames"}, "chain index")
            require(record["schema"] == "rapp-private-hive-chain/1" and R.rappid_valid(record["stream_id"]),
                    "wrong chain index schema or identity")
            hashes = record["frames"]
            require(isinstance(hashes, list) and 1 <= len(hashes) <= 4096
                    and len(hashes) == len(set(hashes)) and hashes[-1] == address, "chain index limit, cycle or wrong tip")
            frames = [self.artifact("rapp/1:wave", value) for value in hashes]
            require(all(parse(raw)["stream_id"] == record["stream_id"] for raw in frames), "chain stream mismatch")
            self.chains[address] = frames
        return self.chains[address]


@dataclass
class VerifiedBundle:
    pointer: dict
    pointer_bytes: bytes
    files: dict[str, bytes]
    anchor: dict
    gate: HiveAcceptance
    resolver: Resolver
    materialized: dict[str, bytes]
    inventory: list[dict]

    def checkpoint(self):
        return {**self.gate.checkpoint(), "pointer_hash": digest(self.pointer_bytes),
                "mother_seq": self.gate.head["seq"], "release_seq": self.pointer["release_seq"],
                "projections": self.pointer["projections"],
                "declaration_hash": self.anchor["genesis_frame_hash"]}


def verify_bundle(anchor_raw: bytes, pointer_raw: bytes, read, *, checkpoint=None) -> VerifiedBundle:
    anchor = verify_anchor(anchor_raw)
    pointer = parse(pointer_raw, "current pointer")
    exact_keys(pointer, {"schema", "hive_rappid", "workspace_rappid", "dimension_rappid", "created_utc", "release_seq", "previous",
                         "registry", "mother", "catalog_hash", "manifest_hash", "projections", "index_hash", "sig"},
               "current pointer")
    require(pointer["schema"] == "rapp-private-hive-current/1"
            and pointer["hive_rappid"] == anchor["hive_rappid"], "current pointer belongs to another Hive")
    verify_signed(pointer, anchor["owner_rappid"], unb64(anchor["spki_der_b64"]))
    timestamp(pointer["created_utc"])
    require(type(pointer["release_seq"]) is int and pointer["release_seq"] >= 1, "invalid release sequence")
    if pointer["previous"] is not None:
        hex64(pointer["previous"])
    require((pointer["previous"] is None) == (pointer["release_seq"] == 1), "wrong release predecessor")
    exact_keys(pointer["registry"], {"seq", "hash", "artifact_hash"}, "pointer registry")
    require(type(pointer["registry"]["seq"]) is int and 1 <= pointer["registry"]["seq"] <= H.UINT53_MAX,
            "invalid pointer registry sequence")
    exact_keys(pointer["mother"], {"seq", "frame_hash"}, "pointer Mother")
    require(type(pointer["mother"]["seq"]) is int and pointer["mother"]["seq"] == pointer["release_seq"],
            "release/Mother sequence mismatch")
    for value in (pointer["registry"]["hash"], pointer["registry"]["artifact_hash"], pointer["mother"]["frame_hash"],
                  pointer["catalog_hash"], pointer["manifest_hash"], pointer["index_hash"]):
        hex64(value)
    require(R.rappid_valid(pointer["dimension_rappid"]) and R.rappid_valid(pointer["workspace_rappid"]),
            "invalid prepared dimension/workspace identity")
    latest_index = index_path(pointer["index_hash"])
    raw_index = read(latest_index)
    index = parse(raw_index, "release index")
    exact_keys(index, {"schema", "files"}, "release index")
    require(index["schema"] == "rapp-private-hive-release-index/1" and particle(index) == pointer["index_hash"],
            "release index commitment mismatch")
    validate_table(index["files"])
    files = {latest_index: raw_index}
    for item in index["files"]:
        require(item["path"] != latest_index, "self-referencing release index")
        raw = read(item["path"])
        require(len(raw) == item["bytes"] and digest(raw) == item["sha256"], "exact release artifact verification failed")
        files[item["path"]] = raw
    require(len(files) <= MAX_ARTIFACTS and sum(map(len, files.values())) <= MAX_BUNDLE_BYTES, "bundle limit")
    recognized = {latest_index}
    histories = {}
    for path, raw in files.items():
        if not path.startswith("registry-history/"):
            continue
        document = parse(raw)
        authority = authenticated_registry(raw, anchor)
        require(path == f"registry-history/{authority.sequence}-{particle(document)}.json", "registry history address mismatch")
        require(authority.sequence not in histories, "registry history sequence fork")
        histories[authority.sequence] = authority
        recognized.update({path, artifact_path("rapp/1:particle", particle(document))})
        require(files[artifact_path("rapp/1:particle", particle(document))] == raw, "registry particle differs from history")
    initial = histories.get(anchor["registry_seq"])
    require(initial is not None and initial.commitment == anchor["registry_hash"], "anchored initial registry is missing")
    require(all(value._document["entries"] == initial._document["entries"]
                and value._document["canonical_source"] == initial._document["canonical_source"]
                for value in histories.values()), "registry topology/key/genesis changes are unsupported")
    authority = histories.get(pointer["registry"]["seq"])
    require(authority is not None and authority.sequence == max(histories)
            and authority.commitment == pointer["registry"]["hash"]
            and particle(authority._document) == pointer["registry"]["artifact_hash"], "pointer registry mismatch or rollback")
    authority = authenticated_registry(canonical(authority._document), anchor, checkpoint)
    resolver = Resolver(files)
    gate = HiveAcceptance(authority, anchor["hive_rappid"], resolver.chain)
    gate.restore(pointer["mother"]["frame_hash"])
    require(gate.head["seq"] == pointer["mother"]["seq"] and gate.head["utc"] == pointer["created_utc"],
            "current Mother position/time mismatch")
    declaration = gate._declaration
    require(declaration["world_id"] == anchor["world_id"] and len(declaration["members"]) == 1
            and declaration["members"][0]["rappid"] == anchor["owner_rappid"],
            "single-owner anchored world required")
    require(all(room["members"] == [anchor["owner_rappid"]] for room in declaration["rooms"]), "member topology unsupported")
    require(all(channel["kind"] in {"local", "github"} and channel["role"] in {"authority", "mirror"}
                for channel in declaration["channels"]), "unsupported declared channel")
    require(not gate._pending and all(frame["payload"]["status"] == "converged" for frame in gate._retained.values()
                                     if frame["kind"] == "hive.convergence"), "unresolved convergence is not deployable")
    require(particle(gate.catalog) == pointer["catalog_hash"], "current catalog mismatch")
    require(isinstance(pointer["projections"], list) and 1 <= len(pointer["projections"]) <= 8,
            "one to eight channel projections required")
    channel_ids = []
    projection_frames = {}
    for projection in pointer["projections"]:
        exact_keys(projection, {"channel_id", "stream_id", "seq", "frame_hash"}, "pointer projection")
        channel_ids.append(projection["channel_id"])
        chain = resolver.chain(projection["frame_hash"])
        frame = parse(chain[-1])
        require(frame["stream_id"] == projection["stream_id"] and frame["seq"] == projection["seq"]
                and type(projection["seq"]) is int, "projection head position mismatch")
        require(frame["payload"]["channel_id"] == projection["channel_id"]
                and frame["payload"]["artifact_manifest_hash"] == pointer["manifest_hash"], "projection channel/manifest mismatch")
        manifest = files["manifests/" + pointer["manifest_hash"] + ".json"]
        gate.accept_projection(frame["frame_hash"], manifest_bytes=manifest, artifact_resolver=resolver.artifact)
        for raw in chain:
            value = parse(raw)
            projection_frames[value["frame_hash"]] = value
    require(channel_ids == sorted({channel["id"] for channel in declaration["channels"]}), "missing or duplicate channel projection")
    streams = {anchor["hive_rappid"], pointer["dimension_rappid"]}
    streams.update(item["stream_id"] for item in pointer["projections"])
    require(len(streams) == 2 + len(pointer["projections"]) and streams == set(authority._genesis),
            "registry genesis set differs from the single-owner Hive/dimension/projection streams")
    materialized, inventory, file_frames, inventory_frames = {}, [], {}, []
    all_frames = {**gate._retained, **projection_frames}
    for address, frame in gate._retained.items():
        if frame["kind"] == "hive.declaration":
            require(frame["seq"] == 0, "topology replacement refused")
        elif frame["kind"] == "hive.convergence":
            require(all(item["status"] in {"accepted", "duplicate"} for item in frame["payload"]["decisions"]),
                    "MVP refuses quarantine, conflict, supersession and reconciliation activation")
        elif frame["kind"] == "hive.object":
            value = frame["payload"]
            descriptor = value["object"]
            require(frame["stream_id"] == pointer["dimension_rappid"] and value["producer_rappid"] == anchor["owner_rappid"]
                    and value["audience"] == [anchor["owner_rappid"]] and descriptor["space"] == "rapp/1:particle"
                    and descriptor["protection"] == "member-visible", "unsupported object authority or protection")
            raw = resolver.artifact("rapp/1:particle", descriptor["hash"])
            content = parse(raw)
            require(particle(content) == descriptor["hash"], "object particle mismatch")
            recognized.add(artifact_path("rapp/1:particle", descriptor["hash"]))
            if descriptor["kind"] == FILE_KIND:
                target = relative(descriptor["target_path"])
                data = decode_file(content, descriptor, frame["utc"])
                file_frames[address] = (target, data)
                evidence_path = "receipts/pii/" + descriptor["pii_evidence_hash"] + ".json"
                require(files[evidence_path] == canonical(content["pii_receipt"]), "PII receipt artifact mismatch")
                recognized.add(evidence_path)
            elif descriptor["kind"] == INVENTORY_KIND:
                exact_keys(content, {"schema", "files"}, "inventory")
                require(content["schema"] == "rapp-private-hive-inventory/1"
                        and descriptor["target_path"] == INVENTORY_TARGET and descriptor["data_class"] == "neutral"
                        and descriptor["pii_status"] == "not-applicable" and descriptor["pii_evidence_hash"] is None
                        and value["mutation_keys"] == ["inventory"], "invalid generated inventory marker")
                require(isinstance(content["files"], list) and len(content["files"]) <= MAX_FILES, "inventory byte/file limit")
                paths = []
                for item in content["files"]:
                    exact_keys(item, {"target_path", "object_frame_hash"}, "inventory file")
                    paths.append(relative(item["target_path"]))
                    hex64(item["object_frame_hash"])
                require(paths == safe_path_set(paths), "inventory must be path sorted")
                inventory_frames.append((frame, content["files"]))
            else:
                raise ValueError("unsupported object kind; unrecognized data is never executed")
        else:
            raise ValueError("sealing, GODD, federation, reconciliation and key release are unsupported")
    require(inventory_frames, "signed release inventory is missing")
    for marker, entries in inventory_frames:
        for item in entries:
            reference = item["object_frame_hash"]
            require(reference in file_frames and file_frames[reference][0] == item["target_path"]
                    and gate._retained[reference]["seq"] < marker["seq"], "inventory references an unaccepted or later object")
    latest_marker, inventory = max(inventory_frames, key=lambda item: item[0]["seq"])
    dimension_frames = [frame for frame in gate._retained.values() if frame["stream_id"] == pointer["dimension_rappid"]]
    require(latest_marker["seq"] == max(frame["seq"] for frame in dimension_frames), "inventory is not the approved dimension tip")
    for item in inventory:
        materialized[item["target_path"]] = file_frames[item["object_frame_hash"]][1]
    for address, catalog in gate._catalogs.items():
        path = artifact_path("rapp/1:particle", address)
        require(files[path] == canonical(catalog), "catalog artifact mismatch")
        recognized.add(path)
    for frame in projection_frames.values():
        payload = frame["payload"]
        if frame["seq"] == 0:
            require(payload["status"] == "stale" and payload["registry_seq"] == 0
                    and payload["artifact_manifest_hash"] == "0" * 64
                    and payload["convergence_payload_hash"] == "0" * 64, "invalid projection bootstrap")
            continue
        require(payload["status"] == "current" and payload["registry_seq"] in histories, "unsupported projection history")
        historical = HiveAcceptance(histories[payload["registry_seq"]], anchor["hive_rappid"], resolver.chain)
        historical.restore(payload["frame_head"])
        manifest_path = "manifests/" + payload["artifact_manifest_hash"] + ".json"
        raw_manifest = files[manifest_path]
        historical.accept_projection(frame["frame_hash"], manifest_bytes=raw_manifest, artifact_resolver=resolver.artifact)
        receipt_path = f"receipts/{payload['channel_id']}/{frame['frame_hash']}.json"
        require(files[receipt_path] == canonical(frame), "projection receipt copy differs")
        recognized.update({manifest_path, receipt_path})
    by_stream = {}
    for frame in all_frames.values():
        by_stream.setdefault(frame["stream_id"], []).append(frame)
    for stream, frames in by_stream.items():
        frames.sort(key=lambda frame: frame["seq"])
        require([frame["seq"] for frame in frames] == list(range(len(frames))), "incomplete retained stream")
        ancestry = []
        for frame in frames:
            ancestry.append(frame["frame_hash"])
            wave_path, index_file = artifact_path("rapp/1:wave", frame["frame_hash"]), chain_path(frame["frame_hash"])
            require(files[wave_path] == canonical(frame)
                    and files[index_file] == canonical({"schema": "rapp-private-hive-chain/1",
                                                       "stream_id": stream, "frames": list(ancestry)}),
                    "retained frame/chain index mismatch")
            recognized.update({wave_path, index_file})
    for path, raw in files.items():
        if path.startswith("manifests/releases/"):
            record = parse(raw)
            exact_keys(record, {"schema", "files"}, "historical release index")
            require(record["schema"] == "rapp-private-hive-release-index/1"
                    and path == index_path(particle(record)), "historical index address mismatch")
            for entry in validate_table(record["files"]):
                require(entry["path"] != path and entry["path"] in files
                        and len(files[entry["path"]]) == entry["bytes"]
                        and digest(files[entry["path"]]) == entry["sha256"], "historical index artifact mismatch")
            recognized.add(path)
    require(recognized == set(files), "release contains undeclared, unsupported or unapproved artifacts")
    if checkpoint is not None:
        require(pointer["release_seq"] >= checkpoint["release_seq"], "release rollback")
        if pointer["release_seq"] == checkpoint["release_seq"]:
            require(digest(pointer_raw) == checkpoint["pointer_hash"], "same-sequence release fork")
        mother_chain = [parse(raw) for raw in resolver.chain(gate.head["frame_hash"])]
        require(len(mother_chain) > checkpoint["mother_seq"]
                and mother_chain[checkpoint["mother_seq"]]["frame_hash"] == checkpoint["mother_head_frame_hash"],
                "Mother rollback or same-sequence fork")
        require({item["channel_id"] for item in checkpoint["projections"]} == set(channel_ids), "projection topology changed")
        for prior in checkpoint["projections"]:
            current = next(item for item in pointer["projections"] if item["channel_id"] == prior["channel_id"])
            chain = [parse(raw) for raw in resolver.chain(current["frame_hash"])]
            require(current["stream_id"] == prior["stream_id"] and current["seq"] >= prior["seq"]
                    and chain[prior["seq"]]["frame_hash"] == prior["frame_hash"], "projection rollback or fork")
    return VerifiedBundle(pointer, pointer_raw, files, anchor, gate, resolver, materialized, inventory)
