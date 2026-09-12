from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from _deployment_fixtures import FixtureTest, P, SKILL
from private_hive import client, release
from private_hive.adapters.filesystem import Filesystem, publication_path
from private_hive.bundle import verify_bundle
from private_hive.common import MAX_FILE_BYTES, artifact_path, b64, canonical, digest, parse, read_file, write_file
from private_hive.state import State


class FilesystemDeploymentTests(FixtureTest):
    def test_empty_release_uses_real_signed_inventory_candidate(self):
        result = self.fx.first_release(selected=False)
        frozen = self.fx.frozen(result["plan_hash"])
        verified = verify_bundle(canonical(release.export_anchor(self.fx.publisher)),
                                 frozen["pointer"], frozen["files"].__getitem__)
        self.assertEqual(verified.materialized, {})
        self.assertEqual(len(verified.gate.head["payload"]["candidates"]), 1)
        self.assertEqual(verified.gate.head["payload"]["decisions"][0]["status"], "accepted")
        self.fx.publish(result["plan_hash"])
        self.fx.init_client()
        self.assertEqual(client.pull(self.fx.client, self.fx.channels[0])["files"], 0)

    def test_approved_copy_has_no_godd_path_hash_content_or_controls(self):
        result = self.fx.first_release(pending=True)
        frozen = self.fx.frozen(result["plan_hash"])
        data = self.fx.data["private/GODD-secret.txt"]
        forbidden = [data, b64(data).encode(), b"private/GODD-secret.txt", digest(data).encode(),
                     digest(b"private/GODD-secret.txt").encode(), b"pending_sealed", b".rapp-hive",
                     b"baseline.json", b"migration-receipt", b"PRIVATE KEY",
                     (self.fx.custody / "owner.pk8.pem").read_bytes()]
        exposed = b"\n".join(path.encode() + b"\n" + raw for path, raw in frozen["files"].items()) + frozen["pointer"]
        for needle in forbidden:
            self.assertNotIn(needle, exposed)
        self.assertEqual(result["plan"]["excluded_pending_count"], 1)
        self.assertEqual(len(result["plan"]["approved_files"]), 1)
        self.fx.publish(result["plan_hash"])
        self.assertEqual(self.fx.original_bytes(), self.fx.data)
        for path in self.fx.channel_root.rglob("*"):
            if path.is_file() and path.name not in {".store.lock", "current.json"}:
                publication_path(path.relative_to(self.fx.channel_root).as_posix())

    def test_build_approve_publish_and_retries_are_immutable(self):
        first = self.fx.first_release()
        duplicate = self.fx.build()
        self.assertEqual(duplicate["plan_hash"], first["plan_hash"])
        self.assertEqual(duplicate["plan"], first["plan"])
        with self.assertRaises(ValueError):
            release.publish(self.fx.publisher, self.fx.key, first["plan_hash"])
        self.assertFalse(self.fx.channel_root.exists())
        self.fx.publish(first["plan_hash"])
        prior = Filesystem(self.fx.channel_root).current()
        self.assertEqual(self.fx.build()["plan_hash"], first["plan_hash"])
        self.fx.publish(first["plan_hash"])
        self.assertEqual(Filesystem(self.fx.channel_root).current(), prior)
        self.assertEqual(len(release.status(self.fx.publisher)["releases"]), 1)

    def test_wrong_plan_hash_and_changed_frozen_bytes_refuse_before_publication(self):
        result = self.fx.first_release()
        with self.assertRaises(ValueError):
            release.approve(self.fx.publisher, self.fx.key, "1" * 64)
        state = State(self.fx.publisher, "publisher")
        with state.transaction() as db:
            db.execute("UPDATE release_files SET content=? WHERE plan_hash=? AND path=(SELECT path FROM release_files "
                       "WHERE plan_hash=? ORDER BY path LIMIT 1)",
                       (b"tampered", result["plan_hash"], result["plan_hash"]))
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            release.approve(self.fx.publisher, self.fx.key, result["plan_hash"])
        self.assertFalse(self.fx.channel_root.exists())

    def test_frozen_approval_not_live_workspace_is_the_publish_input(self):
        result = self.fx.first_release()
        release.approve(self.fx.publisher, self.fx.key, result["plan_hash"])
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Local evolution after approval.\n")
        release.publish(self.fx.publisher, self.fx.key, result["plan_hash"])
        self.fx.init_client()
        client.pull(self.fx.client, self.fx.channels[0])
        materialized = client.materialize(self.fx.client, self.fx.output)
        self.assertEqual((Path(materialized["generation"]) / "rooms/general/safe/guide.txt").read_bytes(),
                         self.fx.data["safe/guide.txt"])
        self.assertEqual((self.fx.workspace / "safe/guide.txt").read_bytes(), b"Local evolution after approval.\n")

    def test_changed_source_or_staged_content_refuses_a_build(self):
        self.fx.select()
        staged = self.fx.stage()
        self.fx.init()
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"modified source")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.fx.build()
        (self.fx.workspace / "safe/guide.txt").write_bytes(self.fx.data["safe/guide.txt"])
        staged_file = Path(staged["outbox"]) / "generations" / staged["generation"] / "objects/safe/guide.txt"
        staged_file.write_bytes(b"modified staging")
        with self.assertRaisesRegex(ValueError, "source changed"):
            self.fx.build()
        self.assertFalse(self.fx.channel_root.exists())
        self.assertEqual(release.status(self.fx.publisher)["releases"], [])

    def test_bounded_base64_particle_and_original_large_source_preserved(self):
        path = self.fx.workspace / "safe/guide.txt"
        data = b"x" * (MAX_FILE_BYTES + 1)
        path.write_bytes(data)
        self.fx.select()
        self.fx.stage()
        self.fx.init()
        with self.assertRaisesRegex(ValueError, "700 KiB"):
            self.fx.build()
        self.assertEqual(path.read_bytes(), data)
        self.assertFalse(self.fx.channel_root.exists())

    def test_maximum_supported_file_and_empty_file_round_trip(self):
        for size in (0, MAX_FILE_BYTES):
            with self.subTest(size=size):
                (self.fx.workspace / "safe/guide.txt").write_bytes(b"x" * size)
                self.fx.select(data_class="neutral")
                self.fx.stage()
                self.fx.init()
                result = self.fx.build()
                self.fx.publish(result["plan_hash"])
                self.fx.init_client()
                client.pull(self.fx.client, self.fx.channels[0])
                rendered = client.materialize(self.fx.client, self.fx.output)
                self.assertEqual((Path(rendered["generation"]) / "rooms/general/safe/guide.txt").read_bytes(), b"x" * size)

    def test_cas_and_immutable_adapter_refuse_collision_paths_and_links(self):
        store = Filesystem(self.fx.channel_root)
        address = "objects/particle/" + "1" * 64 + ".json"
        store.put_immutable(address, b"first")
        store.put_immutable(address, b"first")
        with self.assertRaisesRegex(ValueError, "collision"):
            store.put_immutable(address, b"different")
        with self.assertRaises(ValueError):
            store.put_immutable("../escape", b"no")
        store.compare_and_swap(None, b"first pointer")
        with self.assertRaisesRegex(ValueError, "CAS"):
            store.compare_and_swap(None, b"second pointer")
        self.assertEqual(store.current(), b"first pointer")
        target = self.fx.channel_root / address
        target.unlink()
        target.symlink_to(self.fx.workspace / "private/GODD-secret.txt")
        with self.assertRaisesRegex(ValueError, "symlink"):
            store.read(address)

    def test_private_channel_modes_and_unmanaged_root_are_enforced(self):
        self.fx.channel_root.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            Filesystem(self.fx.channel_root).put_immutable("objects/particle/" + "2" * 64 + ".json", b"data")
        self.fx.channel_root.chmod(0o700)
        (self.fx.channel_root / "unmanaged.txt").write_bytes(b"preserve me")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            Filesystem(self.fx.channel_root).put_immutable("objects/particle/" + "2" * 64 + ".json", b"data")
        self.assertEqual((self.fx.channel_root / "unmanaged.txt").read_bytes(), b"preserve me")

    def test_crash_before_current_keeps_only_unreachable_immutable_bytes(self):
        result = self.fx.first_release()
        release.approve(self.fx.publisher, self.fx.key, result["plan_hash"])
        def crash(stage):
            if stage == "before-cas":
                raise RuntimeError("fictional crash")
        with self.assertRaisesRegex(RuntimeError, "fictional crash"):
            release.publish(self.fx.publisher, self.fx.key, result["plan_hash"], fault=crash)
        self.assertIsNone(Filesystem(self.fx.channel_root).current())
        self.assertFalse(release.status(self.fx.publisher)["releases"][0]["complete"])
        self.fx.publish(result["plan_hash"])
        self.assertIsNotNone(Filesystem(self.fx.channel_root).current())

    def test_crash_after_current_recovers_without_resigning_or_advancing(self):
        result = self.fx.first_release()
        release.approve(self.fx.publisher, self.fx.key, result["plan_hash"])
        def crash(stage):
            if stage == "after-cas":
                raise RuntimeError("lost acknowledgement")
        with self.assertRaisesRegex(RuntimeError, "acknowledgement"):
            release.publish(self.fx.publisher, self.fx.key, result["plan_hash"], fault=crash)
        before = Filesystem(self.fx.channel_root).current()
        self.fx.publish(result["plan_hash"])
        self.assertEqual(Filesystem(self.fx.channel_root).current(), before)
        self.assertTrue(release.status(self.fx.publisher)["releases"][0]["complete"])

    def test_abrupt_immutable_link_crash_recovers_identical_retry(self):
        result = self.fx.first_release()
        release.approve(self.fx.publisher, self.fx.key, result["plan_hash"])
        code = """
import os
import sys
from pathlib import Path
from private_hive import common, keys, release

original = common.os.link

def crash(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(99)

common.os.link = crash
release.publish(Path(sys.argv[1]), keys.load(Path(sys.argv[2])), sys.argv[3])
"""
        environment = {
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(SKILL / "lib"),
        }
        process = subprocess.run(
            [sys.executable, "-c", code, str(self.fx.publisher), str(self.fx.custody), result["plan_hash"]],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        self.assertEqual(process.returncode, 99, process.stderr.decode())
        self.fx.publish(result["plan_hash"])
        self.assertIsNotNone(Filesystem(self.fx.channel_root).current())
        for path in self.fx.channel_root.rglob(".write-*"):
            self.fail(f"orphaned staging link remains: {path}")

    def test_two_competing_publisher_processes_have_one_cas_winner(self):
        self.fx.select()
        self.fx.stage()
        self.fx.init()
        rival = self.fx.root / "rival-publisher"
        shutil.copytree(self.fx.publisher, rival)
        first = self.fx.build()
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Competing fictional release.\n")
        self.fx.select()
        self.fx.stage()
        second = self.fx.build(rival)
        release.approve(self.fx.publisher, self.fx.key, first["plan_hash"])
        release.approve(rival, self.fx.key, second["plan_hash"])
        code = ("import sys; from pathlib import Path; from private_hive import keys,release; "
                "release.publish(Path(sys.argv[1]),keys.load(Path(sys.argv[2])),sys.argv[3])")
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(SKILL / "lib")}
        processes = [subprocess.Popen([sys.executable, "-c", code, str(directory), str(self.fx.custody), plan],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                     for directory, plan in ((self.fx.publisher, first["plan_hash"]), (rival, second["plan_hash"]))]
        outputs = [process.communicate(timeout=60) for process in processes]
        self.assertEqual(sorted(process.returncode for process in processes), [0, 1], outputs)
        frozen = [self.fx.frozen(first["plan_hash"]), self.fx.frozen(second["plan_hash"], rival)]
        self.assertIn(Filesystem(self.fx.channel_root).current(), [item["pointer"] for item in frozen])

    def test_expired_publication_scan_and_changed_topology_refuse(self):
        scanned = (datetime.now(timezone.utc) - timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        self.fx.select(stamp=scanned)
        self.fx.stage()
        self.fx.init()
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        with self.assertRaisesRegex(ValueError, "24 hours"):
            self.fx.build(created_utc=future)
        declaration = self.fx.workspace / ".rapp-hive/declaration.json"
        value = P.read_json(declaration)
        value["rooms"][0]["area"] = "rooms/changed"
        P.atomic_write(declaration, P.canonical_bytes(value))
        with self.assertRaisesRegex(ValueError, "topology changed"):
            self.fx.build()
        self.assertFalse(self.fx.channel_root.exists())

    def test_discard_preserves_unapproved_bytes_but_cannot_discard_approval(self):
        first = self.fx.first_release()
        release.discard(self.fx.publisher, first["plan_hash"])
        self.assertEqual(self.fx.frozen(first["plan_hash"])["files"],
                         self.fx.frozen(first["plan_hash"])["files"])
        second = self.fx.build()
        release.approve(self.fx.publisher, self.fx.key, second["plan_hash"])
        with self.assertRaises(ValueError):
            release.discard(self.fx.publisher, second["plan_hash"])


if __name__ == "__main__":
    unittest.main()
