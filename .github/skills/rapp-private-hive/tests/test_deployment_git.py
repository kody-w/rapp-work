from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from _deployment_fixtures import FixtureTest
from private_hive import client, release
from private_hive.adapters.github_git import GitHubGit, validate_evidence
from private_hive.bundle import verify_bundle
from private_hive.common import canonical, digest, now


class GitDeploymentTests(FixtureTest):
    def setUp(self):
        super().setUp()
        self.config = {"id": "fixture-github", "kind": "github", "role": "authority",
                       "repository": "fictional-owner/private-fixture", "repository_id": 12345,
                       "owner_id": 67890, "actor_id": 24680, "actor_login": "fictional-actor", "ref": "refs/heads/hive"}
        self.remote = self.fx.root / "synthetic-remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--template=", "--object-format=sha1", str(self.remote)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.remote.chmod(0o700)
        self.fx.channels = [self.config]
        self.git_state = self.fx.publisher / "git-fixture"
        self.evidence = {"schema": "rapp-private-hive-github-evidence/1", "checked_utc": now(),
                         "repository": {"id": 12345, "full_name": "fictional-owner/private-fixture", "owner_id": 67890,
                                        "private": True, "visibility": "private", "fork": False,
                                        "archived": False, "disabled": False},
                         "actor": {"id": 24680, "login": "fictional-actor"}}
        self.provider_calls = 0

    def provider(self, config):
        self.provider_calls += 1
        return copy.deepcopy(self.evidence)

    def adapter(self, provider=None, directory=None, config=None):
        return GitHubGit(config or self.config, directory or self.git_state,
                         evidence_provider=provider or self.provider, remote_override=self.remote)

    def first(self):
        self.fx.select()
        self.fx.stage()
        self.fx.init()
        return self.fx.build(expected_refs={self.config["id"]: "absent"})

    def publish(self, built, adapter=None, **kwargs):
        release.approve(self.fx.publisher, self.fx.key, built["plan_hash"])
        return release.publish(self.fx.publisher, self.fx.key, built["plan_hash"],
                               adapters={self.config["id"]: adapter or self.adapter()}, **kwargs)

    def ref(self):
        return subprocess.run(["git", "--git-dir=" + str(self.remote), "for-each-ref",
                               "--format=%(objectname)", self.config["ref"]], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip() or None

    def test_private_git_publication_and_independent_client_round_trip(self):
        built = self.first()
        published = self.publish(built)
        oid = published["channels"][0]["ref"]
        self.assertEqual(self.ref(), oid)
        self.assertGreaterEqual(self.provider_calls, 2)
        self.fx.init_client()
        adapter = self.adapter(directory=self.fx.client / "git-fixture")
        result = client.pull(self.fx.client, self.config, adapter=adapter)
        self.assertEqual(result["ref"], oid)
        rendered = client.materialize(self.fx.client, self.fx.output)
        self.assertEqual((Path(rendered["generation"]) / "rooms/general/safe/guide.txt").read_bytes(),
                         self.fx.data["safe/guide.txt"])
        self.assertFalse(list(self.git_state.glob("git-session-*")))
        self.assertEqual(self.fx.original_bytes(), self.fx.data)

    def test_existing_private_git_authority_import_uses_verified_snapshot(self):
        built = self.first()
        self.publish(built)
        parent = self.ref()
        anchor = canonical(release.export_anchor(self.fx.publisher))
        with self.adapter(directory=self.fx.root / "read-cache").snapshot() as (read, oid):
            self.assertEqual(oid, parent)
            imported = verify_bundle(anchor, read("refs/current.json"), read)
        destination = self.fx.root / "imported-publisher"
        result = release.initialize(self.fx.workspace, destination, self.fx.key, self.fx.channels, imported=imported)
        self.assertEqual(result["anchor"], imported.anchor)
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Safe successor from imported Git authority.")
        self.fx.select()
        self.fx.stage()
        successor = self.fx.build(destination, expected_refs={self.config["id"]: parent})
        release.approve(destination, self.fx.key, successor["plan_hash"])
        adapter = self.adapter(directory=destination / "git-fixture")
        release.publish(destination, self.fx.key, successor["plan_hash"], adapters={self.config["id"]: adapter})
        self.assertNotEqual(self.ref(), parent)

    def test_privacy_identity_actor_visibility_fork_archive_disabled_gates_precede_content(self):
        built = self.first()
        original = copy.deepcopy(self.evidence)
        cases = [("repository", "id", 999), ("repository", "owner_id", 999),
                 ("repository", "full_name", "another-owner/private-fixture"),
                 ("repository", "private", False), ("repository", "visibility", "public"),
                 ("repository", "fork", True), ("repository", "archived", True), ("repository", "disabled", True),
                 ("actor", "id", 999), ("actor", "login", "another-actor"), ("repository", "id", True)]
        for section, field, value in cases:
            with self.subTest(section=section, field=field):
                self.evidence = copy.deepcopy(original)
                self.evidence[section][field] = value
                with self.assertRaises(ValueError):
                    self.publish(built)
                self.assertIsNone(self.ref())
                self.assertFalse(self.git_state.exists())
        self.evidence = original
        self.publish(built)
        self.assertIsNotNone(self.ref())

    def test_unavailable_stale_or_future_privacy_evidence_refused(self):
        built = self.first()
        for offset in (-3600, 3600):
            self.evidence["checked_utc"] = (datetime.now(timezone.utc) + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "stale or from"):
                self.publish(built)
            self.assertFalse(self.git_state.exists())
        def unavailable(config):
            raise ValueError("privacy API unavailable")
        with self.assertRaisesRegex(ValueError, "unavailable"):
            self.publish(built, self.adapter(provider=unavailable))
        self.assertIsNone(self.ref())

    def test_privacy_rechecked_immediately_before_push(self):
        built = self.first()
        def provider(config):
            value = copy.deepcopy(self.evidence)
            self.provider_calls += 1
            if self.provider_calls >= 2:
                value["repository"]["private"] = False
                value["repository"]["visibility"] = "public"
            return value
        with self.assertRaisesRegex(ValueError, "must be private"):
            self.publish(built, self.adapter(provider=provider))
        self.assertIsNone(self.ref())
        self.assertFalse(list(self.git_state.glob("git-session-*")))

    def test_explicit_expected_old_ref_required_before_a_plan_is_written(self):
        self.fx.select()
        self.fx.stage()
        self.fx.init()
        for refs in ({}, {"fixture-github": "main"}, {"different": "absent"}):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                self.fx.build(expected_refs=refs)
        self.assertEqual(release.status(self.fx.publisher)["releases"], [])
        self.assertFalse(self.git_state.exists())

    def test_git_repeat_build_publish_pull_creates_no_extra_commit(self):
        built = self.first()
        self.assertEqual(self.fx.build(expected_refs={self.config["id"]: "absent"})["plan_hash"], built["plan_hash"])
        first = self.publish(built)
        second = self.publish(built)
        self.assertEqual(first, second)
        self.assertEqual(self.ref(), first["channels"][0]["ref"])
        self.fx.init_client()
        adapter = self.adapter(directory=self.fx.client / "git-fixture")
        client.pull(self.fx.client, self.config, adapter=adapter)
        self.assertEqual(client.pull(self.fx.client, self.config, adapter=adapter)["status"], "unchanged")
        self.assertEqual(self.fx.build(expected_refs={self.config["id"]: self.ref()})["plan_hash"], built["plan_hash"])

    def test_new_release_uses_explicit_parent_oid_and_keeps_all_prior_blobs(self):
        first = self.first()
        self.publish(first)
        parent = self.ref()
        original_tree = subprocess.check_output(["git", "--git-dir=" + str(self.remote), "ls-tree", "-r", parent])
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Second safe Git fixture revision.\n")
        self.fx.select()
        self.fx.stage()
        second = self.fx.build(expected_refs={self.config["id"]: parent})
        self.publish(second)
        current = self.ref()
        self.assertNotEqual(parent, current)
        actual_parent = subprocess.check_output(["git", "--git-dir=" + str(self.remote), "rev-parse", current + "^"]).decode().strip()
        self.assertEqual(actual_parent, parent)
        current_tree = subprocess.check_output(["git", "--git-dir=" + str(self.remote), "ls-tree", "-r", current])
        for line in original_tree.splitlines():
            if not line.endswith(b"\trefs/current.json"):
                self.assertIn(line, current_tree.splitlines())

    def test_stale_expected_ref_never_overwrites_remote_branch(self):
        first = self.first()
        self.publish(first)
        parent = self.ref()
        (self.fx.workspace / "safe/guide.txt").write_bytes(b"Safe but incorrectly based candidate.")
        self.fx.select()
        self.fx.stage()
        second = self.fx.build(expected_refs={self.config["id"]: "absent"})
        with self.assertRaisesRegex(ValueError, "CAS conflict"):
            self.publish(second)
        self.assertEqual(self.ref(), parent)

    def test_force_with_lease_loses_to_a_real_competing_remote_ref(self):
        built = self.first()
        tree = subprocess.check_output(["git", "--git-dir=" + str(self.remote), "mktree"], input=b"").decode().strip()
        env = {**os.environ, "GIT_AUTHOR_NAME": "Fictional competitor", "GIT_AUTHOR_EMAIL": "competitor@example.invalid",
               "GIT_COMMITTER_NAME": "Fictional competitor", "GIT_COMMITTER_EMAIL": "competitor@example.invalid"}
        competitor = subprocess.check_output(["git", "--git-dir=" + str(self.remote), "commit-tree", tree],
                                              input=b"Fictional competing ref\n", env=env).decode().strip()
        def race(config):
            self.provider_calls += 1
            if self.provider_calls == 2:
                subprocess.run(["git", "--git-dir=" + str(self.remote), "update-ref", self.config["ref"], competitor],
                               check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return copy.deepcopy(self.evidence)
        with self.assertRaisesRegex(ValueError, "CAS failed"):
            self.publish(built, self.adapter(provider=race))
        self.assertEqual(self.ref(), competitor)

    def test_git_lost_ack_recovery_uses_durable_exact_commit_intent(self):
        built = self.first()
        def crash(stage):
            if stage == "after-cas":
                raise RuntimeError("lost Git acknowledgement")
        with self.assertRaises(RuntimeError):
            self.publish(built, fault=crash)
        published_oid = self.ref()
        self.assertIsNotNone(published_oid)
        result = self.publish(built)
        self.assertEqual(result["channels"][0]["ref"], published_oid)
        self.assertEqual(self.ref(), published_oid)

    def test_git_isolation_ignores_workspace_git_hooks_and_inherited_git_configuration(self):
        subprocess.run(["git", "init", "--quiet", "--template=", str(self.fx.workspace)], check=True)
        hooks = self.fx.workspace / ".git/hooks"
        hooks.mkdir()
        (hooks / "pre-push").write_text("#!/bin/sh\nexit 99\n")
        (hooks / "pre-push").chmod(0o700)
        before = (self.fx.workspace / ".git/config").read_bytes()
        built = self.first()
        contamination = {"GIT_DIR": str(self.fx.workspace / ".git"), "GIT_WORK_TREE": str(self.fx.workspace),
                         "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks)}
        with patch.dict(os.environ, contamination):
            self.publish(built)
        self.assertEqual((self.fx.workspace / ".git/config").read_bytes(), before)
        self.assertFalse((self.fx.workspace / ".git/refs/heads/hive").exists())
        self.assertEqual(self.fx.original_bytes(), self.fx.data)

    def test_filesystem_authority_and_git_mirror_share_one_signed_head(self):
        filesystem = {"id": "fixture-store", "kind": "filesystem", "role": "authority", "path": str(self.fx.channel_root)}
        mirror = {**self.config, "role": "mirror"}
        self.fx.channels = [filesystem, mirror]
        built = self.first()
        published = self.publish(built, self.adapter(config=mirror))
        self.assertEqual(len(published["channels"]), 2)
        pointers = {item["pointer_sha256"] for item in published["channels"]}
        self.assertEqual(len(pointers), 1)
        self.fx.init_client()
        first = client.pull(self.fx.client, filesystem)
        adapter = self.adapter(config=mirror, directory=self.fx.client / "git-fixture")
        second = client.pull(self.fx.client, mirror, adapter=adapter)
        self.assertEqual(first["pointer_sha256"], second["pointer_sha256"])
        self.assertEqual(second["status"], "unchanged")


if __name__ == "__main__":
    unittest.main()
