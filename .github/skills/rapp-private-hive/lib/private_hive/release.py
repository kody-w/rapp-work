from __future__ import annotations

import copy
from pathlib import Path

from .authority import FILE_KIND, INVENTORY_KIND, INVENTORY_TARGET, authenticated_registry, bootstrap, channel_declaration, check_workspace, object_payload, signed_frame, store_frame, validate_channels
from .bundle import Resolver, index_bytes, index_path, pii_receipt, table, verify_bundle
from .common import H, HiveAcceptance, MAX_FILE_BYTES, MAX_FILES, R, artifact_path, b64, canonical, chain_path, digest, exact_keys, hex64, locked, no_symlinks, now, parse, particle, paths_disjoint, preparation, private_directory, read_file, relative, require, safe_path_set, timestamp, unb64, write_file
from .keys import OwnerKey, verify_anchor, verify_signed
from .state import State
from .adapters.filesystem import Filesystem
from .adapters.github_git import GitHubGit, OID


def _configuration(root, state, draft, key, channels):
    return {"schema": "rapp-private-hive-publisher/1", "workspace": str(root),
            "workspace_rappid": state["workspace_rappid"], "hive_rappid": state["hive_rappid"],
            "dimension_rappid": state["dimension_rappid"], "prepared_owner_rappid": state["member_rappid"],
            "world_id": draft["world_id"], "owner_rappid": key.rappid, "channels": channels,
            "prepared_declaration_sha256": digest(canonical(draft))}


def initialize(workspace: Path, directory: Path, key: OwnerKey, channels: list[dict], *,
               adopt_prepared_owner=None, created_utc=None, imported=None):
    channels = validate_channels(channels)
    root, prepared, draft, _ = check_workspace(workspace, key, channels, directory,
                                             adopt_prepared_owner=adopt_prepared_owner, importing=imported is not None)
    if key.directory is not None:
        paths_disjoint(key.directory, root, Path(directory), *[Path(item["path"]) for item in channels if item["kind"] == "filesystem"])
    config = _configuration(root, prepared, draft, key, channels)
    directory = no_symlinks(Path(directory))
    if (directory / "state.sqlite3").exists():
        snapshot = State.readonly_snapshot(directory)
        require(snapshot.get("config") == config, "publisher configuration/topology differs; changes and rotation are unsupported")
        require(snapshot.get("authority") is not None, "incomplete authority state; no automatic remint")
        return {"status": "already-initialized", "anchor": snapshot["authority"]["anchor"]}
    if imported is None:
        for channel in channels:
            if channel["kind"] == "filesystem" and Path(channel["path"]).exists():
                store = private_directory(Path(channel["path"]))
                require(not (store / "refs/current.json").exists() and not (store / "registry-history").exists(),
                        "existing channel authority detected; import it rather than bootstrap a competing owner")
    stamp = timestamp(created_utc or now())
    if imported is None:
        authority, files = bootstrap(key, prepared, draft, channels, stamp)
    else:
        require(imported.anchor["owner_rappid"] == key.rappid and unb64(imported.anchor["spki_der_b64"]) == key.spki,
                "imported authority requires its existing owner key; rotation is unsupported")
        require(imported.pointer["hive_rappid"] == prepared["hive_rappid"]
                and imported.pointer["dimension_rappid"] == prepared["dimension_rappid"]
                and imported.pointer["workspace_rappid"] == prepared["workspace_rappid"],
                "import would replace a prepared identity")
        require(imported.gate._declaration["world_id"] == draft["world_id"]
                and imported.gate._declaration["channels"] == [channel_declaration(item) for item in channels],
                "imported topology/locator mismatch")
        expected = copy.deepcopy(draft)
        expected["members"][0]["rappid"] = key.rappid
        for room in expected["rooms"]:
            room["members"] = [key.rappid]
        for field in ("members", "rooms", "policy"):
            require(imported.gate._declaration[field] == expected[field], "imported prepared topology mismatch")
        frames = [frame for frame in imported.gate._retained.values()
                  if frame["stream_id"] == prepared["dimension_rappid"]]
        authority = {"anchor": imported.anchor, "registry": imported.gate.registry._document,
                     "declaration": imported.gate._declaration,
                     "projection_streams": {item["channel_id"]: item["stream_id"] for item in imported.pointer["projections"]},
                     "dimension_head": max(frames, key=lambda frame: frame["seq"])["frame_hash"]}
        files = imported.files
    state = State(directory, "publisher", create=True)
    with state.transaction() as db:
        require(State.get(db, "config") is None, "concurrent authority initialization refused")
        State.set(db, "config", config)
        State.set(db, "authority", authority)
        for path, raw in sorted(files.items()):
            db.execute("INSERT INTO release_files(plan_hash,path,content) VALUES('bootstrap',?,?)", (path, raw))
        if imported is not None:
            identity = digest(imported.pointer_bytes)
            plan = {"schema": "rapp-private-hive-import/1", "pointer_sha256": identity}
            db.execute("INSERT INTO releases(plan_hash,input_hash,plan,pointer,complete) VALUES(?,?,?,?,1)",
                       (identity, "import:" + identity, canonical(plan), imported.pointer_bytes))
            for path, raw in sorted(files.items()):
                db.execute("INSERT INTO release_files(plan_hash,path,content) VALUES(?,?,?)", (identity, path, raw))
            State.set(db, "active", {"plan_hash": identity, "pointer_sha256": identity})
    return {"status": "authority-imported" if imported is not None else "initialized", "anchor": authority["anchor"]}


def export_anchor(directory: Path, destination: Path | None = None):
    snapshot = State.readonly_snapshot(directory)
    anchor = snapshot["authority"]["anchor"]
    raw = canonical(anchor)
    verify_anchor(raw)
    if destination is not None:
        destination = no_symlinks(Path(destination))
        require(destination.parent.is_dir(), "anchor output parent must exist")
        write_file(destination, raw, immutable=True)
    return anchor


def _selected(config, stage_root):
    p = preparation()
    root = p.workspace_root(config["workspace"])
    stage_root = private_directory(Path(stage_root))
    paths_disjoint(root, stage_root)
    with p.workspace_lock(root):
        state, draft, selection = p.control_files(root)
        require(state["workspace_rappid"] == config["workspace_rappid"]
                and state["hive_rappid"] == config["hive_rappid"]
                and state["dimension_rappid"] == config["dimension_rappid"]
                and state["member_rappid"] == config["prepared_owner_rappid"]
                and digest(canonical(draft)) == config["prepared_declaration_sha256"],
                "prepared identity or topology changed")
        current = parse(read_file(stage_root / "current.json", private=True))
        exact_keys(current, {"schema", "generation", "manifest_sha256"}, "stage pointer")
        require(current["schema"] == "rapp-private-hive-current-stage/1"
                and current["generation"] == current["manifest_sha256"], "invalid stage pointer")
        generation = stage_root / "generations" / hex64(current["generation"])
        private_directory(generation)
        raw_manifest = read_file(generation / "manifest.json", private=True)
        require(digest(raw_manifest) == current["generation"], "stage manifest commitment mismatch")
        stage = parse(raw_manifest)
        exact_keys(stage, {"schema", "hive_rappid", "dimension_rappid", "selection_generation", "objects",
                           "pending_sealed", "local_sources_preserved"}, "stage manifest")
        require(stage["schema"] == "rapp-private-hive-stage/2" and stage["hive_rappid"] == state["hive_rappid"]
                and stage["dimension_rappid"] == state["dimension_rappid"]
                and stage["selection_generation"] == selection["generation"]
                and stage["local_sources_preserved"] is True, "stale or foreign staging generation")
        safe = [entry for entry in selection["entries"] if entry["protection"] == "member-visible"]
        require(len(safe) <= MAX_FILES, "approved file count limit")
        fields = ("path", "sha256", "bytes", "data_class", "pii_status", "pii_evidence_hash", "room_id")
        require(stage["objects"] == [{name: item[name] for name in fields} for item in safe],
                "staging does not exactly match approved plaintext selection")
        scanners = p.trusted_scanners(root)
        selected = []
        for entry in safe:
            require(entry["data_class"] in {"dogg", "neutral"} and entry["status"] == "selected",
                    "GODD/plaintext or pending content cannot enter a release")
            relative(entry["path"])
            require(entry["bytes"] <= MAX_FILE_BYTES, "selected file exceeds the 700 KiB raw / 1 MiB canonical limit")
            data = read_file(generation / "objects" / entry["path"], private=True, limit=MAX_FILE_BYTES)
            source = read_file(root / entry["path"], limit=MAX_FILE_BYTES)
            require(data == source and len(data) == entry["bytes"] and digest(data) == entry["sha256"],
                    "selected/staged source changed; reselect and restage")
            evidence = pii_receipt(entry["pii_evidence"], entry["sha256"],
                                   entry["pii_evidence"]["scanned_utc"], scanners)
            require(evidence == entry["pii_evidence_hash"], "PII evidence commitment changed")
            room = next(item for item in draft["rooms"] if item["id"] == entry["room_id"])
            target = relative(room["area"] + "/" + entry["path"])
            content = {"schema": "rapp-private-hive-file/1", "encoding": "base64", "bytes": len(data),
                       "sha256": digest(data), "content_base64": b64(data), "pii_receipt": entry["pii_evidence"]}
            canonical(content)
            selected.append({"target_path": target, "data_class": entry["data_class"], "room_id": entry["room_id"],
                             "pii_evidence_hash": evidence, "particle_hash": particle(content), "content": content})
        selected.sort(key=lambda item: item["target_path"])
        safe_path_set(item["target_path"] for item in selected)
        return selected, len(selection["entries"]) - len(safe), scanners


def _candidate(frame, source):
    return {"dimension_rappid": frame["stream_id"], "source_channel_ids": [source],
            **{name: frame[name] for name in ("stream_id", "seq", "utc", "payload_hash", "frame_hash")},
            "mutation_keys": frame["payload"]["mutation_keys"]}


def build(directory: Path, key: OwnerKey, stage_root: Path, *, expected_refs=None, created_utc=None):
    snapshot = State.readonly_snapshot(directory)
    config, authority = snapshot["config"], snapshot["authority"]
    require(key.rappid == config["owner_rappid"] and key.spki == unb64(authority["anchor"]["spki_der_b64"]),
            "wrong owner key; rotation is unsupported")
    expected_refs = expected_refs or {}
    git_channels = {item["id"] for item in config["channels"] if item["kind"] == "github"}
    require(set(expected_refs) == git_channels, "provide one explicit expected old ref for every GitHub channel")
    require(all(value == "absent" or (isinstance(value, str) and OID.fullmatch(value)) for value in expected_refs.values()),
            "expected ref must be an old Git SHA-1 OID or 'absent'")
    selected, excluded, scanners = _selected(config, stage_root)
    selection_hash = particle({"schema": "rapp-private-hive-approved-files/1",
                               "files": [{name: value for name, value in item.items() if name != "content"} for item in selected]})
    state = State(directory, "publisher")
    with locked(state.root / ".publisher.lock"), state.transaction() as db:
        active = State.get(db, "active")
        base_release = State.release(db, active["plan_hash"]) if active else None
        if base_release and base_release["plan"].get("selection_commitment") == selection_hash:
            return {"status": "unchanged", "plan_hash": active["plan_hash"], "plan": base_release["plan"]}
        base_pointer = active["pointer_sha256"] if active else None
        input_hash = particle({"selection": selection_hash, "base": base_pointer, "expected_refs": expected_refs,
                               "config": particle(config)})
        existing = db.execute("SELECT plan_hash,plan FROM releases WHERE input_hash=? AND complete>=0", (input_hash,)).fetchone()
        if existing:
            return {"status": "already-built", "plan_hash": existing[0], "plan": parse(bytes(existing[1]))}
        require(not db.execute("SELECT 1 FROM releases WHERE complete=0").fetchone(),
                "an unfinished frozen release exists; publish it or explicitly discard an unapproved plan")
        stamp = timestamp(created_utc or now())
        if base_release:
            verified = verify_bundle(canonical(authority["anchor"]), base_release["pointer"], base_release["files"].__getitem__)
            files = dict(verified.files)
            gate = verified.gate
            resolver = verified.resolver
            previous_inventory = {item["target_path"]: item["object_frame_hash"] for item in verified.inventory}
            dimension_frames = [frame for frame in gate._retained.values() if frame["stream_id"] == config["dimension_rappid"]]
            dimension = max(dimension_frames, key=lambda frame: frame["seq"])
            projection_heads = {item["channel_id"]: parse(files[artifact_path("rapp/1:wave", item["frame_hash"])])
                                for item in verified.pointer["projections"]}
            # The resolver must see additions to this frozen successor, not the preceding bundle's copy.
            resolver.files = files
            candidates = []
        else:
            files = {path: bytes(raw) for path, raw in db.execute(
                "SELECT path,content FROM release_files WHERE plan_hash='bootstrap' ORDER BY path")}
            resolver = Resolver(files)
            registry_authority = authenticated_registry(canonical(authority["registry"]), authority["anchor"])
            gate = HiveAcceptance(registry_authority, config["hive_rappid"], resolver.chain)
            dimension = parse(files[artifact_path("rapp/1:wave", authority["dimension_head"])])
            previous_inventory = {}
            projection_heads = {channel: parse(files[artifact_path("rapp/1:wave", registry_authority._genesis[stream])])
                                for channel, stream in authority["projection_streams"].items()}
            candidates = [dimension]
        require(stamp >= gate.head["utc"] and stamp >= dimension["utc"], "release clock rollback")
        inventory = []
        for item in selected:
            descriptor_frame = None
            prior_hash = previous_inventory.get(item["target_path"])
            if prior_hash:
                previous = parse(files[artifact_path("rapp/1:wave", prior_hash)])
                descriptor = previous["payload"]["object"]
                if (descriptor["hash"] == item["particle_hash"] and descriptor["data_class"] == item["data_class"]
                        and previous["payload"]["room_id"] == item["room_id"]):
                    descriptor_frame = previous
            if descriptor_frame is None:
                content = item["content"]
                pii_receipt(content["pii_receipt"], content["sha256"], stamp, scanners)
                files[artifact_path("rapp/1:particle", item["particle_hash"])] = canonical(content)
                files["receipts/pii/" + item["pii_evidence_hash"] + ".json"] = canonical(content["pii_receipt"])
                payload = object_payload(key, config, authority["declaration"], stamp, item["particle_hash"],
                                         item["target_path"], FILE_KIND, data_class=item["data_class"],
                                         pii_evidence_hash=item["pii_evidence_hash"], room=item["room_id"])
                descriptor_frame = signed_frame(key, "hive.object", config["dimension_rappid"], payload, dimension)
                store_frame(files, descriptor_frame, dimension)
                dimension = descriptor_frame
                candidates.append(descriptor_frame)
            inventory.append({"target_path": item["target_path"], "object_frame_hash": descriptor_frame["frame_hash"]})
        if selected or base_release:
            content = {"schema": "rapp-private-hive-inventory/1", "files": inventory}
            address = particle(content)
            files[artifact_path("rapp/1:particle", address)] = canonical(content)
            marker = signed_frame(key, "hive.object", config["dimension_rappid"],
                                  object_payload(key, config, authority["declaration"], stamp, address,
                                                 INVENTORY_TARGET, INVENTORY_KIND), dimension)
            store_frame(files, marker, dimension)
            candidates.append(marker)
        source = authority["declaration"]["authority_channel_id"]
        proposed = sorted([_candidate(frame, source) for frame in candidates], key=lambda item: (item["utc"], item["frame_hash"]))
        payload = gate.preview_convergence(proposed, stamp)
        require(all(item["status"] == "accepted" for item in payload["decisions"]), "release has unapproved convergence decisions")
        mother = signed_frame(key, "hive.convergence", config["hive_rappid"], payload, gate.head)
        store_frame(files, mother, gate.head)
        gate.accept_convergence(mother["frame_hash"])
        for address, catalog in gate._catalogs.items():
            files[artifact_path("rapp/1:particle", address)] = canonical(catalog)
        manifest = gate.artifact_manifest()
        manifest_hash = particle(manifest)
        files["manifests/" + manifest_hash + ".json"] = canonical(manifest)
        projections = []
        for channel in config["channels"]:
            previous = projection_heads[channel["id"]]
            projection = signed_frame(key, "hive.projection", previous["stream_id"], {
                "schema": H.PROJECTION_SCHEMA, "hive_rappid": config["hive_rappid"],
                "convergence_payload_hash": mother["payload_hash"], "channel_id": channel["id"],
                "projected_utc": stamp, "registry_seq": gate.registry.sequence, "catalog_hash": particle(gate.catalog),
                "frame_head": mother["frame_hash"], "artifact_manifest_hash": manifest_hash, "status": "current"}, previous)
            store_frame(files, projection, previous)
            files[f"receipts/{channel['id']}/{projection['frame_hash']}.json"] = canonical(projection)
            projections.append({"channel_id": channel["id"], "stream_id": projection["stream_id"],
                                "seq": projection["seq"], "frame_hash": projection["frame_hash"]})
        index_raw = index_bytes(files)
        index_hash = particle(parse(index_raw))
        files[index_path(index_hash)] = index_raw
        pointer = key.signed({"schema": "rapp-private-hive-current/1", "hive_rappid": config["hive_rappid"],
                              "workspace_rappid": config["workspace_rappid"], "dimension_rappid": config["dimension_rappid"],
                              "created_utc": stamp, "release_seq": mother["seq"], "previous": base_pointer,
                              "registry": {"seq": gate.registry.sequence, "hash": gate.registry.commitment,
                                           "artifact_hash": particle(gate.registry._document)},
                              "mother": {"seq": mother["seq"], "frame_hash": mother["frame_hash"]},
                              "catalog_hash": particle(gate.catalog), "manifest_hash": manifest_hash,
                              "projections": projections, "index_hash": index_hash})
        pointer_raw = canonical(pointer)
        verify_bundle(canonical(authority["anchor"]), pointer_raw, files.__getitem__,
                      checkpoint=verified.checkpoint() if base_release else None)
        channels = [{"id": channel["id"], "config_sha256": digest(canonical(channel)),
                     "expected_pointer_sha256": base_pointer, "expected_ref": expected_refs.get(channel["id"])}
                    for channel in config["channels"]]
        plan = {"schema": "rapp-private-hive-release-plan/1", "hive_rappid": config["hive_rappid"],
                "owner_rappid": key.rappid, "selection_commitment": selection_hash, "created_utc": stamp,
                "base_pointer_sha256": base_pointer, "excluded_pending_count": excluded,
                "approved_files": [{"target_path": item["target_path"], "data_class": item["data_class"],
                                    "sha256": item["content"]["sha256"], "bytes": item["content"]["bytes"],
                                    "particle_hash": item["particle_hash"]} for item in selected],
                "channels": channels, "artifacts": table(files), "pointer_sha256": digest(pointer_raw), "pointer": pointer}
        plan_raw = canonical(plan)
        plan_hash = digest(plan_raw)
        discarded = db.execute("SELECT plan,pointer,complete FROM releases WHERE plan_hash=?", (plan_hash,)).fetchone()
        if discarded:
            require(discarded[2] == -1 and bytes(discarded[0]) == plan_raw and bytes(discarded[1]) == pointer_raw,
                    "existing immutable plan differs")
            db.execute("UPDATE releases SET complete=0,input_hash=? WHERE plan_hash=?", (input_hash, plan_hash))
            return {"status": "built-not-approved", "plan_hash": plan_hash, "plan": plan}
        db.execute("INSERT INTO releases(plan_hash,input_hash,plan,pointer) VALUES(?,?,?,?)", (plan_hash, input_hash, plan_raw, pointer_raw))
        db.executemany("INSERT INTO release_files(plan_hash,path,content) VALUES(?,?,?)",
                       [(plan_hash, path, raw) for path, raw in sorted(files.items())])
        return {"status": "built-not-approved", "plan_hash": plan_hash, "plan": plan}


def frozen(snapshot, plan_hash, release, key=None, *, approved=False):
    hex64(plan_hash, "plan hash")
    plan = release["plan"]
    exact_keys(plan, {"schema", "hive_rappid", "owner_rappid", "selection_commitment", "created_utc",
                      "base_pointer_sha256", "excluded_pending_count", "approved_files", "channels", "artifacts", "pointer_sha256", "pointer"},
               "frozen release plan")
    require(plan["schema"] == "rapp-private-hive-release-plan/1" and digest(canonical(plan)) == plan_hash,
            "frozen release plan was modified")
    config, anchor = snapshot["config"], snapshot["authority"]["anchor"]
    require(plan["owner_rappid"] == config["owner_rappid"] and plan["hive_rappid"] == config["hive_rappid"],
            "release identity mismatch")
    require(table(release["files"]) == plan["artifacts"] and canonical(plan["pointer"]) == release["pointer"]
            and digest(release["pointer"]) == plan["pointer_sha256"], "frozen release bytes changed")
    require(plan["channels"] == [{"id": channel["id"], "config_sha256": digest(canonical(channel)),
                                  "expected_pointer_sha256": plan["base_pointer_sha256"],
                                  "expected_ref": next((item["expected_ref"] for item in plan["channels"]
                                                        if item["id"] == channel["id"]), None)}
                                 for channel in config["channels"]], "approved topology changed")
    if key is not None:
        require(key.rappid == anchor["owner_rappid"] and key.spki == unb64(anchor["spki_der_b64"]), "owner key mismatch")
    verified = verify_bundle(canonical(anchor), release["pointer"], release["files"].__getitem__)
    require(plan["approved_files"] == [
        {"target_path": item["target_path"],
         "data_class": verified.gate._retained[item["object_frame_hash"]]["payload"]["object"]["data_class"],
         "sha256": digest(verified.materialized[item["target_path"]]),
         "bytes": len(verified.materialized[item["target_path"]]),
         "particle_hash": verified.gate._retained[item["object_frame_hash"]]["payload"]["object"]["hash"]}
        for item in verified.inventory], "reviewed file list differs from the authenticated inventory")
    if approved:
        approval = release["approval"]
        exact_keys(approval, {"schema", "plan_hash", "owner_rappid", "sig"}, "release approval")
        require(approval["schema"] == "rapp-private-hive-release-approval/1" and approval["plan_hash"] == plan_hash
                and approval["owner_rappid"] == anchor["owner_rappid"], "exact owner approval is missing")
        verify_signed(approval, anchor["owner_rappid"], unb64(anchor["spki_der_b64"]))
    return verified


def approve(directory: Path, key: OwnerKey, plan_hash: str):
    snapshot = State.readonly_snapshot(directory)
    state = State(directory, "publisher")
    with state.transaction() as db:
        release = State.release(db, plan_hash)
        frozen(snapshot, plan_hash, release, key)
        approval = key.signed({"schema": "rapp-private-hive-release-approval/1", "plan_hash": plan_hash,
                               "owner_rappid": key.rappid})
        require(release["approval"] is None or release["approval"] == approval, "existing approval differs")
        db.execute("UPDATE releases SET approval=? WHERE plan_hash=?", (canonical(approval), plan_hash))
    return {"status": "approved", "plan_hash": plan_hash}


def publish(directory: Path, key: OwnerKey, plan_hash: str, *, adapters=None, evidence_provider=None, fault=None):
    snapshot = State.readonly_snapshot(directory)
    state = State(directory, "publisher")
    with locked(state.root / ".publisher.lock"):
        with state.transaction() as db:
            release = State.release(db, plan_hash)
            frozen(snapshot, plan_hash, release, key, approved=True)
            active = State.get(db, "active")
            require(active is None or active["plan_hash"] == plan_hash
                    or active["pointer_sha256"] == release["plan"]["base_pointer_sha256"],
                    "obsolete release cannot overwrite a newer publication")
        config = snapshot["config"]
        receipts = []
        for channel in sorted(config["channels"], key=lambda item: (item["role"] != "authority", item["id"])):
            approved_channel = next(item for item in release["plan"]["channels"] if item["id"] == channel["id"])
            if adapters and channel["id"] in adapters:
                adapter = adapters[channel["id"]]
            elif channel["kind"] == "filesystem":
                adapter = Filesystem(Path(channel["path"]))
            else:
                adapter = GitHubGit(channel, state.root / ("git-" + channel["id"]), evidence_provider=evidence_provider)
            with state.transaction() as db:
                row = db.execute("SELECT value FROM intents WHERE plan_hash=? AND channel=?", (plan_hash, channel["id"])).fetchone()
                intent = parse(bytes(row[0])) if row else None

            def save_intent(value):
                with state.transaction() as db:
                    row = db.execute("SELECT value FROM intents WHERE plan_hash=? AND channel=?",
                                     (plan_hash, channel["id"])).fetchone()
                    require(row is None or bytes(row[0]) == canonical(value), "Git publish intent changed")
                    db.execute("INSERT OR IGNORE INTO intents(plan_hash,channel,value) VALUES(?,?,?)",
                               (plan_hash, channel["id"], canonical(value)))

            receipt = adapter.publish(release["files"], release["pointer"],
                                      expected_pointer=approved_channel["expected_pointer_sha256"],
                                      expected_ref=approved_channel["expected_ref"], intent=intent, save_intent=save_intent,
                                      fault=fault, created_utc=release["plan"]["created_utc"])
            require(receipt["pointer_sha256"] == release["plan"]["pointer_sha256"], "adapter returned a different publication")
            with state.transaction() as db:
                db.execute("INSERT INTO publications(plan_hash,channel,receipt) VALUES(?,?,?) "
                           "ON CONFLICT(plan_hash,channel) DO UPDATE SET receipt=excluded.receipt",
                           (plan_hash, channel["id"], canonical(receipt)))
            receipts.append({"channel_id": channel["id"], **receipt})
        with state.transaction() as db:
            db.execute("UPDATE releases SET complete=1 WHERE plan_hash=?", (plan_hash,))
            State.set(db, "active", {"plan_hash": plan_hash, "pointer_sha256": release["plan"]["pointer_sha256"]})
        return {"status": "published", "plan_hash": plan_hash, "channels": receipts}


def discard(directory: Path, plan_hash: str):
    state = State(directory, "publisher")
    with state.transaction() as db:
        release = State.release(db, plan_hash)
        require(release["approval"] is None and not release["complete"], "approved/published releases cannot be discarded")
        db.execute("UPDATE releases SET complete=-1,input_hash=? WHERE plan_hash=?", ("discarded:" + plan_hash, plan_hash))
    return {"status": "discarded-locally", "plan_hash": plan_hash, "immutable_bytes_retained": True}


def status(directory: Path):
    state = State(directory, "publisher")
    with state.transaction() as db:
        rows = db.execute("SELECT plan_hash,approval IS NOT NULL,complete FROM releases ORDER BY rowid").fetchall()
        return {"status": "local-publisher-state", "active": State.get(db, "active"),
                "releases": [{"plan_hash": row[0], "approved": bool(row[1]), "complete": row[2] == 1,
                              "discarded": row[2] == -1} for row in rows]}
