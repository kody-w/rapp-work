from __future__ import annotations

import copy
import re
from pathlib import Path

from .common import H, R, RegistryAuthority, artifact_path, b64, canonical, chain_path, digest, exact_keys, hex64, no_symlinks, parse, particle, paths_disjoint, preparation, read_file, relative, require, timestamp, unb64
from .keys import OwnerKey, verify_anchor


SPEC_PATH = Path(__file__).resolve().parents[2] / "vendor" / "hive" / "SPEC.md"
FILE_KIND = "private-hive.file"
INVENTORY_KIND = "private-hive.inventory"
INVENTORY_TARGET = "rooms/general/.hive-inventory.json"
AUTHORITY_PATHS = ("registry.json", "rapp/registry.json", ".rapp/registry.json",
                   ".rapp-hive/registry.json", ".rapp-hive/authority.json",
                   ".rapp-hive/owner-anchor.json", "owner-anchor.json")


def validate_channels(channels: list[dict]) -> list[dict]:
    require(isinstance(channels, list) and 1 <= len(channels) <= 8, "one to eight explicit channels required")
    checked = []
    for item in channels:
        require(isinstance(item, dict), "channel must be an object")
        kind = item.get("kind")
        require(kind in {"filesystem", "github"}, "unsupported channel; SharePoint/public Git/federation refused")
        shared = {"id", "kind", "role"}
        if kind == "filesystem":
            exact_keys(item, shared | {"path"}, "filesystem channel")
            path = no_symlinks(Path(item["path"]))
            require(path.is_absolute() and path.parent.is_dir(), "filesystem channel parent must exist")
            value = {**item, "path": str(path)}
        else:
            exact_keys(item, shared | {"repository", "repository_id", "owner_id", "actor_id",
                                      "actor_login", "ref"}, "GitHub channel")
            require(isinstance(item["repository"], str)
                    and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}", item["repository"])
                    and not item["repository"].endswith(".git"), "explicit GitHub owner/repository required")
            require(all(type(item[key]) is int and item[key] > 0
                        for key in ("repository_id", "owner_id", "actor_id")), "positive immutable GitHub IDs required")
            require(isinstance(item["actor_login"], str)
                    and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", item["actor_login"]), "expected actor login required")
            ref = item["ref"]
            require(isinstance(ref, str) and re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9_/-]{0,100}", ref)
                    and not ref.endswith("/") and "//" not in ref, "explicit safe branch ref required")
            value = dict(item)
        H.label(item["id"], "channel id")
        require(item["role"] in {"authority", "mirror"}, "MVP channels are authority or read-only projection mirrors")
        checked.append(value)
    require(len({item["id"] for item in checked}) == len(checked), "duplicate channel id")
    require(sum(item["role"] == "authority" for item in checked) == 1, "exactly one authority channel required")
    return sorted(checked, key=lambda item: item["id"])


def channel_declaration(channel):
    return {"id": channel["id"], "kind": "local" if channel["kind"] == "filesystem" else "github",
            "role": channel["role"], "writeback": channel["role"] == "authority",
            "locator": ("private-filesystem:" + channel["id"] if channel["kind"] == "filesystem"
                        else "https://github.com/" + channel["repository"])}


def check_workspace(workspace: Path, key: OwnerKey, channels, publisher: Path, *,
                    adopt_prepared_owner=None, importing=False):
    p = preparation()
    root = p.workspace_root(str(workspace))
    state, draft, selection = p.control_files(root)
    H.validate_declaration(draft)
    require(len(draft["members"]) == 1 and draft["members"][0]["role"] == "owner",
            "multi-owner/member deployment and topology changes are unsupported")
    old_owner = state["member_rappid"]
    require(all(room["members"] == [old_owner] for room in draft["rooms"]), "non-owner room members are unsupported")
    require(old_owner == key.rappid or adopt_prepared_owner == old_owner,
            "prepared owner differs: explicitly bind --adopt-prepared-owner before first authority; no rotation")
    require(any(room["id"] == "general" and room["access"] == "repository"
                and room["area"] == "rooms/general" for room in draft["rooms"]), "general repository room required")
    if not importing:
        require(not any((root / path).exists() or (root / path).is_symlink() for path in AUTHORITY_PATHS),
                "existing authority detected; import its complete authenticated publication, never replace it")
    locations = [root, publisher.absolute()]
    locations += [Path(item["path"]) for item in channels if item["kind"] == "filesystem"]
    paths_disjoint(*locations)
    return root, state, draft, selection


def signed_frame(key: OwnerKey, kind: str, stream: str, payload: dict, previous=None) -> dict:
    stamp = payload.get("created_utc", payload.get("projected_utc"))
    timestamp(stamp)
    if previous is not None:
        require(stamp >= previous["utc"], "frame clock rollback")
    frame = R.build_frame(kind, stream, 0 if previous is None else previous["seq"] + 1,
                          stamp, payload, None if previous is None else previous["payload_hash"])
    frame["sig"] = key.sign({name: value for name, value in frame.items() if name != "sig"})
    return frame


def store_frame(files: dict[str, bytes], frame: dict, previous=None):
    address = frame["frame_hash"]
    if previous is None:
        ancestry = []
    else:
        ancestry = parse(files[chain_path(previous["frame_hash"])])["frames"]
    files[artifact_path("rapp/1:wave", address)] = canonical(frame)
    files[chain_path(address)] = canonical({"schema": "rapp-private-hive-chain/1",
                                          "stream_id": frame["stream_id"], "frames": [*ancestry, address]})


def object_payload(key, state, draft, stamp, address, target, kind, *, data_class="neutral",
                   pii_evidence_hash=None, room="general"):
    room_value = next(item for item in draft["rooms"] if item["id"] == room)
    require(room_value["access"] == "repository", "sealing/key release is not supported")
    slug = "inventory" if kind == INVENTORY_KIND else "file-" + digest(target.encode())[:32]
    owner = R.rappid_parts(key.rappid)["owner"]
    return {
        "schema": H.OBJECT_SCHEMA, "hive_rappid": state["hive_rappid"],
        "object_rappid": R.mint_rappid(owner, slug, key.spki), "producer_rappid": key.rappid,
        "world_id": draft["world_id"], "created_utc": stamp, "room_id": room, "audience": [key.rappid],
        "object": {"space": "rapp/1:particle", "hash": address, "kind": kind,
                   "data_class": data_class, "pii_status": "not-applicable" if kind == INVENTORY_KIND else "none",
                   "pii_evidence_hash": pii_evidence_hash, "protection": "member-visible", "target_path": target},
        "source_frames": [], "mutation_keys": ["inventory" if kind == INVENTORY_KIND else "file/" + target],
    }


def registry(key: OwnerKey, hive: str, genesis: dict[str, str], sequence=1) -> dict:
    entries = [{"type": "estate_owner", "rappid": key.rappid},
               {"type": "protocol", "name": "rapp-hive/1", "spec_repo": "https://github.com/kody-w/RAPP",
                "spec_path": "protocols/rapp-hive/1/SPEC.md", "spec_hash": digest(read_file(SPEC_PATH)),
                "deprecated": False}]
    entries += [{"type": "kind", "kind": kind, "family": "body", "deprecated": False}
                for kind in sorted(H.KIND_SCHEMAS)]
    entries += [{"type": "spki", "rappid": key.rappid, "spki_der_b64": b64(key.spki), "deprecated": False}]
    entries += [{"type": "genesis", "stream_id": stream, "frame_hash": value, "deprecated": False}
                for stream, value in sorted(genesis.items())]
    return key.signed({"schema": "rapp/1-registry", "registry_seq": sequence,
                       "canonical_source": "urn:rapp:private-hive:" + R.rappid_parts(hive)["hash"] + ":registry-history",
                       "entries": entries})


def authenticated_registry(raw: bytes, anchor: dict, checkpoint=None):
    value = parse(raw, "registry")
    exact_keys(value, {"schema", "registry_seq", "canonical_source", "entries", "sig"}, "registry")
    for entry in value["entries"]:
        require(entry.get("type") in {"estate_owner", "protocol", "kind", "spki", "genesis"}
                and entry.get("deprecated", False) is False,
                "registry succession, revocation, federation and other authority changes are unsupported")
        if entry["type"] == "genesis":
            exact_keys(entry, {"type", "stream_id", "frame_hash", "deprecated"}, "registry genesis")
    require(len([item for item in value["entries"] if item["type"] == "protocol"]) == 1,
            "only the pinned Hive profile is supported")
    require(len([item for item in value["entries"] if item["type"] == "spki"]) == 1,
            "single direct-owner SPKI required; rotation is unsupported")
    require({item["kind"] for item in value["entries"] if item["type"] == "kind"} == set(H.KIND_SCHEMAS),
            "registry kind set must equal the eight pinned Hive kinds")
    floor = checkpoint or {"registry_seq": anchor["registry_seq"], "registry_hash": anchor["registry_hash"]}
    authority = RegistryAuthority(raw, owner_rappid=anchor["owner_rappid"],
                                  owner_spki_der=unb64(anchor["spki_der_b64"]),
                                  minimum_registry_seq=floor["registry_seq"],
                                  same_sequence_hash=floor["registry_hash"])
    require(authority._genesis.get(anchor["hive_rappid"]) == anchor["genesis_frame_hash"],
            "registered Mother genesis differs from the out-of-band anchor")
    return authority


def bootstrap(key: OwnerKey, state, draft, channels, stamp):
    declaration = copy.deepcopy(draft)
    declaration["created_utc"] = timestamp(stamp)
    declaration["members"][0]["rappid"] = key.rappid
    for room in declaration["rooms"]:
        room["members"] = [key.rappid]
    declaration["channels"] = [channel_declaration(item) for item in channels]
    declaration["authority_channel_id"] = next(item["id"] for item in channels if item["role"] == "authority")
    H.validate_declaration(declaration)
    files, genesis, projection_streams = {}, {}, {}
    mother = signed_frame(key, "hive.declaration", state["hive_rappid"], declaration)
    store_frame(files, mother)
    genesis[mother["stream_id"]] = mother["frame_hash"]
    empty_inventory = {"schema": "rapp-private-hive-inventory/1", "files": []}
    address = particle(empty_inventory)
    files[artifact_path("rapp/1:particle", address)] = canonical(empty_inventory)
    marker = signed_frame(key, "hive.object", state["dimension_rappid"],
                          object_payload(key, state, declaration, stamp, address, INVENTORY_TARGET, INVENTORY_KIND))
    store_frame(files, marker)
    genesis[marker["stream_id"]] = marker["frame_hash"]
    for channel in channels:
        owner = R.rappid_parts(key.rappid)["owner"]
        stream = R.mint_rappid(owner, "projection-" + channel["id"], key.spki)
        require(stream not in genesis, "projection stream collides with an existing identity")
        receipt = signed_frame(key, "hive.projection", stream, {
            "schema": H.PROJECTION_SCHEMA, "hive_rappid": state["hive_rappid"],
            "convergence_payload_hash": "0" * 64, "channel_id": channel["id"], "projected_utc": stamp,
            "registry_seq": 0, "catalog_hash": particle(H.catalog_payload(declaration, {})),
            "frame_head": mother["frame_hash"], "artifact_manifest_hash": "0" * 64, "status": "stale"})
        store_frame(files, receipt)
        genesis[stream] = receipt["frame_hash"]
        projection_streams[channel["id"]] = stream
    document = registry(key, state["hive_rappid"], genesis)
    raw = canonical(document)
    registry_hash = particle({name: value for name, value in document.items() if name != "sig"})
    anchor = key.signed({"schema": "rapp-private-hive-owner-anchor/1", "owner_rappid": key.rappid,
                         "spki_der_b64": b64(key.spki), "spki_sha256": digest(key.spki),
                         "hive_rappid": state["hive_rappid"], "world_id": declaration["world_id"],
                         "genesis_frame_hash": mother["frame_hash"], "registry_seq": 1, "registry_hash": registry_hash})
    verify_anchor(canonical(anchor))
    authenticated_registry(raw, anchor)
    files[artifact_path("rapp/1:particle", particle(document))] = raw
    files[f"registry-history/1-{particle(document)}.json"] = raw
    return {"anchor": anchor, "registry": document, "declaration": declaration,
            "projection_streams": projection_streams, "dimension_head": marker["frame_hash"]}, files
