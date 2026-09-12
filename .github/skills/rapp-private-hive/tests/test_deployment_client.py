from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from _deployment_fixtures import Fixture, FixtureTest, P, SKILL
from private_hive import client, release
from private_hive.bundle import index_bytes, index_path, verify_bundle
from private_hive.common import canonical, digest, parse, particle, read_file, relative, write_file
from private_hive.state import State


class IndependentClientTests(FixtureTest):
    def deployed(self, *, scripts=False):
        if scripts:
            self.fx.select("safe/tool.py", data_class="neutral")
        built = self.fx.first_release()
        self.fx.publish(built["plan_hash"])
        self.fx.init_client()
        return built

    def test_client_independent_of_workspace_private_keys_and_publisher_state(self):
        self.deployed(scripts=True)
        self.fx.workspace.rename(self.fx.root / "offline-workspace")
        self.fx.custody.rename(self.fx.root / "offline-custody")
        self.fx.publisher.rename(self.fx.root / "offline-publisher")
        self.assertEqual(client.pull(self.fx.client, self.fx.channels[0])["files"], 2)
        rendered = client.materialize(self.fx.client, self.fx.output)
        self.assertFalse(rendered["executed"])
        script = Path(rendered["generation"]) / "rooms/general/safe/tool.py"
        self.assertEqual(script.read_bytes(), self.fx.data["safe/tool.py"])
        self.assertEqual(script.stat().st_mode & 0o777, 0o600)
        self.assertEqual(client.verify(self.fx.client, self.fx.output)["status"], "verified")

    def test_anchor_install_requires_independent_fingerprint_and_no_replacement(self):
        self.fx.init()
        anchor = release.export_anchor(self.fx.publisher)
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            client.initialize(self.fx.client, canonical(anchor), expected_spki_sha256="0" * 64)
        self.assertFalse(self.fx.client.exists())
        self.fx.init_client()
        before = State.readonly_snapshot(self.fx.client)
        changed = dict(anchor)
        changed["world_id"] = "foreign-world"
        changed.pop("sig")
        changed = self.fx.key.signed(changed)
        with self.assertRaisesRegex(ValueError, "rotation"):
            client.initialize(self.fx.client, canonical(changed), expected_spki_sha256=digest(self.fx.key.spki))
        self.assertEqual(State.readonly_snapshot(self.fx.client), before)

    def test_pull_requires_client_anchor_and_never_accepts_channel_anchor(self):
        built = self.fx.first_release()
        self.fx.publish(built["plan_hash"])
        with self.assertRaises(ValueError):
            client.pull(self.fx.client, self.fx.channels[0])
        self.assertFalse(self.fx.client.exists())

    def test_repeated_pull_materialization_and_process_state_are_idempotent(self):
        self.deployed()
        first = client.pull(self.fx.client, self.fx.channels[0])
        checkpoint = State.readonly_snapshot(self.fx.client)["checkpoint"]
        self.assertEqual(client.pull(self.fx.client, self.fx.channels[0])["status"], "unchanged")
        rendered = client.materialize(self.fx.client, self.fx.output)
        repeated = client.materialize(self.fx.client, self.fx.output)
        self.assertEqual(rendered, repeated)
        self.assertEqual(State.readonly_snapshot(self.fx.client)["checkpoint"], checkpoint)
        self.assertEqual(len([path for path in (self.fx.output / "generations").iterdir() if not path.name.startswith(".")]), 1)
        self.assertEqual(first["pointer_sha256"], checkpoint["pointer_hash"])

    def test_remote_byte_tamper_does_not_advance_any_client_checkpoint(self):
        built = self.deployed()
        original = State.readonly_snapshot(self.fx.client)
        frozen = self.fx.frozen(built["plan_hash"])
        path = next(name for name in frozen["files"] if name.startswith("objects/particle/"))
        (self.fx.channel_root / path).write_bytes(b"corrupt remote artifact")
        with self.assertRaisesRegex(ValueError, "artifact verification"):
            client.pull(self.fx.client, self.fx.channels[0])
        self.assertEqual(State.readonly_snapshot(self.fx.client), original)
        self.assertFalse(self.fx.output.exists())

    def test_client_commit_crash_rolls_back_both_artifacts_and_checkpoint(self):
        self.deployed()
        def crash(stage):
            if stage == "before-client-commit":
                raise RuntimeError("fictional SQLite crash")
        with self.assertRaises(RuntimeError):
            client.pull(self.fx.client, self.fx.channels[0], fault=crash)
        self.assertNotIn("checkpoint", State.readonly_snapshot(self.fx.client))
        state = State(self.fx.client, "client")
        with state.transaction() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM release_files").fetchone()[0], 0)
        self.assertEqual(client.pull(self.fx.client, self.fx.channels[0])["status"], "pulled-and-verified")

    def test_abrupt_client_death_recovers_hot_sqlite_journal(self):
        self.deployed()
        channel_path = self.fx.root / "client-channel.json"
        channel_path.write_text(json.dumps(self.fx.channels[0]), encoding="utf-8")
        code = (
            "import json,os,sys; from pathlib import Path; "
            "from private_hive import client; "
            "channel=json.loads(Path(sys.argv[2]).read_text()); "
            "client.pull(Path(sys.argv[1]),channel,"
            "fault=lambda event: os._exit(99) if event=='before-client-commit' else None)"
        )
        environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(SKILL / "lib"),
        }
        result = subprocess.run(
            [sys.executable, "-c", code, str(self.fx.client), str(channel_path)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        self.assertEqual(result.returncode, 99, result.stderr.decode())
        self.assertTrue(Path(str(self.fx.client / "state.sqlite3") + "-journal").exists())
        self.assertNotIn("checkpoint", State.readonly_snapshot(self.fx.client))
        self.assertEqual(client.pull(self.fx.client, self.fx.channels[0])["status"], "pulled-and-verified")

    def test_cached_byte_tamper_is_not_materialized(self):
        self.deployed()
        client.pull(self.fx.client, self.fx.channels[0])
        state = State(self.fx.client, "client")
        with state.transaction() as db:
            db.execute("UPDATE release_files SET content=? WHERE path=(SELECT path FROM release_files ORDER BY path LIMIT 1)",
                       (b"modified cache",))
        with self.assertRaises(ValueError):
            client.materialize(self.fx.client, self.fx.output)
        self.assertFalse(self.fx.output.exists())

    def test_unmanaged_destination_symlink_and_path_escape_refused(self):
        self.deployed()
        client.pull(self.fx.client, self.fx.channels[0])
        self.fx.output.mkdir(mode=0o700)
        note = self.fx.output / "unmanaged.txt"
        note.write_bytes(b"Local user data stays untouched.")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            client.materialize(self.fx.client, self.fx.output)
        self.assertEqual(note.read_bytes(), b"Local user data stays untouched.")
        alias = self.fx.root / "alias"
        alias.symlink_to(self.fx.output, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            client.materialize(self.fx.client, alias)
        for path in ("../escape", "/absolute", "C:/escape", "safe//a", ".git/config", "a/.rapp-hive/state", "CON", "a\\b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                relative(path)

    def test_materialization_crash_before_and_after_pointer_recovers(self):
        self.deployed(scripts=True)
        client.pull(self.fx.client, self.fx.channels[0])
        stages = ("after-materialized-file", "after-materialized-cas")
        for stage in stages:
            with self.subTest(stage=stage):
                def crash(value):
                    if value == stage:
                        raise RuntimeError("fictional materialization crash")
                with self.assertRaises(RuntimeError):
                    client.materialize(self.fx.client, self.fx.output, fault=crash)
                if stage == "after-materialized-file":
                    self.assertFalse((self.fx.output / "current.json").exists())
        client.materialize(self.fx.client, self.fx.output)
        self.assertEqual(client.verify(self.fx.client, self.fx.output)["status"], "verified")

    def test_materialized_user_edits_are_preserved_and_refused_not_overwritten(self):
        self.deployed()
        client.pull(self.fx.client, self.fx.channels[0])
        result = client.materialize(self.fx.client, self.fx.output)
        target = Path(result["generation"]) / "rooms/general/safe/guide.txt"
        target.write_bytes(b"My local edits must not disappear.")
        with self.assertRaisesRegex(ValueError, "modified"):
            client.materialize(self.fx.client, self.fx.output)
        self.assertEqual(target.read_bytes(), b"My local edits must not disappear.")

    def test_withdrawal_updates_managed_view_without_deleting_history_or_source(self):
        first = self.deployed()
        client.pull(self.fx.client, self.fx.channels[0])
        old = Path(client.materialize(self.fx.client, self.fx.output)["generation"])
        P.command_unselect(self.fx.args(workspace=str(self.fx.workspace), path="safe/guide.txt"))
        self.fx.stage()
        second = self.fx.build()
        self.fx.publish(second["plan_hash"])
        client.pull(self.fx.client, self.fx.channels[0])
        new = Path(client.materialize(self.fx.client, self.fx.output)["generation"])
        self.assertNotEqual(old, new)
        self.assertTrue((old / "rooms/general/safe/guide.txt").exists())
        self.assertFalse((new / "rooms/general/safe/guide.txt").exists())
        self.assertEqual(self.fx.original_bytes(), self.fx.data)
        self.assertTrue(set(self.fx.frozen(first["plan_hash"])["files"]) <= set(self.fx.frozen(second["plan_hash"])["files"]))
        with self.assertRaisesRegex(ValueError, "obsolete"):
            release.publish(self.fx.publisher, self.fx.key, first["plan_hash"])

    def test_release_rollback_and_same_sequence_repackaging_fork_refused(self):
        first = self.deployed()
        client.pull(self.fx.client, self.fx.channels[0])
        initial = self.fx.frozen(first["plan_hash"])
        anchor = canonical(release.export_anchor(self.fx.publisher))
        checkpoint = State.readonly_snapshot(self.fx.client)["checkpoint"]
        files = dict(initial["files"])
        index = index_bytes(files)
        address = particle(parse(index))
        files[index_path(address)] = index
        pointer = parse(initial["pointer"])
        pointer["index_hash"] = address
        pointer.pop("sig")
        pointer = self.fx.key.signed(pointer)
        with self.assertRaisesRegex(ValueError, "same-sequence"):
            verify_bundle(anchor, canonical(pointer), files.__getitem__, checkpoint=checkpoint)
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"A new fictional safe revision.")
        self.fx.select()
        self.fx.stage()
        second = self.fx.build()
        self.fx.publish(second["plan_hash"])
        client.pull(self.fx.client, self.fx.channels[0])
        checkpoint = State.readonly_snapshot(self.fx.client)["checkpoint"]
        with self.assertRaisesRegex(ValueError, "rollback"):
            verify_bundle(anchor, initial["pointer"], initial["files"].__getitem__, checkpoint=checkpoint)

    def test_mother_competing_branch_cannot_fast_forward_a_persisted_client(self):
        first = self.deployed()
        rival = self.fx.root / "rival-state"
        shutil.copytree(self.fx.publisher, rival)
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Branch A, safe fictional revision.")
        self.fx.select()
        self.fx.stage()
        branch_a = self.fx.build()
        self.fx.publish(branch_a["plan_hash"])
        client.pull(self.fx.client, self.fx.channels[0])
        checkpoint = State.readonly_snapshot(self.fx.client)["checkpoint"]
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Branch B, safe fictional revision.")
        self.fx.select()
        self.fx.stage()
        branch_b = self.fx.build(rival)
        frozen_b = self.fx.frozen(branch_b["plan_hash"], rival)
        with self.assertRaisesRegex(ValueError, "fork"):
            verify_bundle(canonical(release.export_anchor(self.fx.publisher)), frozen_b["pointer"],
                          frozen_b["files"].__getitem__, checkpoint=checkpoint)

    def test_projection_head_rollback_and_channel_substitution_refused(self):
        first = self.deployed()
        frozen = self.fx.frozen(first["plan_hash"])
        anchor = canonical(release.export_anchor(self.fx.publisher))
        for change in ("seq", "channel"):
            pointer = parse(frozen["pointer"])
            if change == "seq":
                pointer["projections"][0]["seq"] = 0
            else:
                pointer["projections"][0]["channel_id"] = "unapproved-channel"
            pointer.pop("sig")
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_bundle(anchor, canonical(self.fx.key.signed(pointer)), frozen["files"].__getitem__)

    def test_existing_authority_import_reuses_identity_genesis_and_history(self):
        first = self.deployed()
        frozen = self.fx.frozen(first["plan_hash"])
        anchor = canonical(release.export_anchor(self.fx.publisher))
        existing = verify_bundle(anchor, frozen["pointer"], frozen["files"].__getitem__)
        imported_dir = self.fx.root / "imported-publisher"
        result = release.initialize(self.fx.workspace, imported_dir, self.fx.key, self.fx.channels, imported=existing)
        self.assertEqual(result["status"], "authority-imported")
        self.assertEqual(result["anchor"], existing.anchor)
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Safe fictional successor after importing authority.")
        self.fx.select()
        self.fx.stage()
        successor = self.fx.build(imported_dir)
        self.fx.publish(successor["plan_hash"], imported_dir)
        self.assertEqual(successor["plan"]["pointer"]["mother"]["seq"], 2)
        self.assertEqual(successor["plan"]["pointer"]["hive_rappid"], self.fx.prepared["hive_rappid"])
        self.assertTrue(set(frozen["files"]) <= set(self.fx.frozen(successor["plan_hash"], imported_dir)["files"]))

    def test_foreign_owner_or_prepared_identity_import_refuses_before_effects(self):
        first = self.deployed()
        frozen = self.fx.frozen(first["plan_hash"])
        existing = verify_bundle(canonical(release.export_anchor(self.fx.publisher)), frozen["pointer"], frozen["files"].__getitem__)
        other = Fixture()
        self.addCleanup(other.close)
        with self.assertRaisesRegex(ValueError, "owner key"):
            release.initialize(other.workspace, other.publisher, other.key, other.channels, imported=existing)
        self.assertFalse(other.publisher.exists())
        with self.assertRaisesRegex(ValueError, "prepared identity"):
            release.initialize(other.workspace, other.publisher, self.fx.key, self.fx.channels,
                               imported=existing, adopt_prepared_owner=other.member)
        self.assertFalse(other.publisher.exists())


if __name__ == "__main__":
    unittest.main()
