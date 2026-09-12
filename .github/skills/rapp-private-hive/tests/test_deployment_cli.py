from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from _deployment_fixtures import Fixture, FixtureTest, SKILL
from private_hive.common import canonical, digest


class DeploymentCLITests(FixtureTest):
    def command(self, *arguments, skill=None, success=True):
        skill = skill or SKILL
        environment = {name: value for name, value in os.environ.items()
                       if name not in {"PYTHONPATH", "GH_TOKEN", "GITHUB_TOKEN"} and not name.startswith("GIT_")}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run([sys.executable, str(skill / "scripts/deploy_hive.py"), *map(str, arguments)],
                                cwd=skill, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result

    def config_file(self, fixture):
        path = fixture.root / "channels.json"
        path.write_bytes(canonical({"schema": "rapp-private-hive-channels/1", "channels": fixture.channels}))
        return path

    def test_two_process_cli_e2e_from_migrated_workspace_to_anchor_only_client(self):
        fixture = Fixture(keyless_owner=True)
        self.addCleanup(fixture.close)
        fixture.select()
        fixture.select("safe/tool.py", data_class="neutral")
        fixture.select("private/GODD-secret.txt", data_class="godd")
        fixture.stage()
        config = self.config_file(fixture)
        self.command("key", "load", "--key-dir", fixture.custody, "--expected-rappid", fixture.key.rappid)
        initialized = self.command("authority", "init", "--workspace", fixture.workspace,
                                   "--publisher-dir", fixture.publisher, "--key-dir", fixture.custody,
                                   "--channels", config, "--adopt-prepared-owner", fixture.member)
        self.assertEqual(initialized["anchor"]["hive_rappid"], fixture.prepared["hive_rappid"])
        anchor_file = fixture.root / "independent-anchor.json"
        self.command("authority", "anchor", "--publisher-dir", fixture.publisher, "--out", anchor_file)
        built = self.command("release", "build", "--publisher-dir", fixture.publisher,
                             "--key-dir", fixture.custody, "--stage-root", fixture.stage_root)
        plan = built["plan_hash"]
        shown = self.command("release", "show", "--publisher-dir", fixture.publisher, "--plan-hash", plan)
        self.assertEqual(shown["plan"], built["plan"])
        self.command("release", "publish", "--publisher-dir", fixture.publisher, "--key-dir", fixture.custody,
                     "--plan-hash", plan, success=False)
        self.assertFalse(fixture.channel_root.exists())
        self.command("release", "approve", "--publisher-dir", fixture.publisher,
                     "--key-dir", fixture.custody, "--plan-hash", plan)
        self.command("release", "publish", "--publisher-dir", fixture.publisher,
                     "--key-dir", fixture.custody, "--plan-hash", plan)
        self.assertEqual(fixture.original_bytes(), fixture.data)
        for path in (fixture.workspace, fixture.custody, fixture.publisher):
            path.rename(path.with_name("offline-" + path.name))
        self.command("client", "init", "--client-dir", fixture.client, "--anchor", anchor_file,
                     "--expected-spki-sha256", digest(fixture.key.spki))
        self.command("client", "pull", "--client-dir", fixture.client, "--channels", config,
                     "--channel-id", fixture.channels[0]["id"])
        materialized = self.command("client", "materialize", "--client-dir", fixture.client,
                                    "--destination", fixture.output)
        self.assertEqual(materialized["files"], 2)
        self.assertFalse(materialized["executed"])
        generation = Path(materialized["generation"])
        self.assertEqual((generation / "rooms/general/safe/tool.py").read_bytes(), fixture.data["safe/tool.py"])
        self.assertFalse((generation / "private/GODD-secret.txt").exists())
        self.command("client", "verify", "--client-dir", fixture.client, "--destination", fixture.output)
        repeated = self.command("client", "pull", "--client-dir", fixture.client, "--channels", config,
                                "--channel-id", fixture.channels[0]["id"])
        self.assertEqual(repeated["status"], "unchanged")

    def test_cli_explicit_key_creation_never_overwrites_existing_custody(self):
        directory = self.fx.root / "cli-keys"
        first = self.command("key", "create", "--key-dir", directory, "--owner-label", "fictional-cli-owner")
        before = (directory / "owner.pk8.pem").read_bytes()
        self.command("key", "create", "--key-dir", directory, "--owner-label", "fictional-cli-owner", success=False)
        self.assertEqual(before, (directory / "owner.pk8.pem").read_bytes())
        loaded = self.command("key", "load", "--key-dir", directory, "--expected-rappid", first["owner_rappid"])
        self.assertEqual(first["spki_sha256"], loaded["spki_sha256"])

    def test_cli_existing_authority_import_has_an_explicit_oob_gate(self):
        built = self.fx.first_release()
        self.fx.publish(built["plan_hash"])
        config = self.config_file(self.fx)
        anchor = self.fx.root / "anchor.json"
        self.command("authority", "anchor", "--publisher-dir", self.fx.publisher, "--out", anchor)
        destination = self.fx.root / "cli-import"
        base = ["authority", "import", "--workspace", self.fx.workspace, "--publisher-dir", destination,
                "--key-dir", self.fx.custody, "--channels", config, "--source", self.fx.channel_root,
                "--anchor", anchor]
        self.command(*base, "--expected-spki-sha256", "0" * 64, success=False)
        self.assertFalse(destination.exists())
        result = self.command(*base, "--expected-spki-sha256", digest(self.fx.key.spki))
        self.assertEqual(result["status"], "authority-imported")
        self.assertEqual(result["anchor"]["hive_rappid"], self.fx.prepared["hive_rappid"])

    def test_unsupported_cli_workflows_have_no_effects(self):
        for operation in ("sharepoint", "public-git", "federation", "seal", "key-release", "rotate-owner", "topology"):
            result = self.command(operation, "activate", success=False)
            self.assertIn(b"unsupported operation refused before effects", result.stderr)
        self.assertFalse(self.fx.publisher.exists())
        self.assertFalse(self.fx.channel_root.exists())

    def test_copied_standalone_skill_preflights_and_checksum_failure_precedes_effects(self):
        installed = self.fx.root / "standalone-skill"
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__", ".hive-test-work"))
        self.assertEqual(self.command("--preflight", skill=installed)["status"], "verified-skill-lock")
        source = installed / "lib/private_hive/keys.py"
        source.write_bytes(source.read_bytes() + b"\n# Tampered fictional installed copy.\n")
        directory = self.fx.root / "must-not-create"
        result = self.command("key", "create", "--key-dir", directory, "--owner-label", "fictional-test",
                              skill=installed, success=False)
        self.assertIn(b"checksum lock mismatch", result.stderr)
        self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
