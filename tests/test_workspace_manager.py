from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "skills" / "rapp-workspace-manager" / "scripts" / "manage.py"
SPEC = importlib.util.spec_from_file_location("rapp_workspace_manager", SCRIPT)
MANAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MANAGER)


class WorkspaceManagerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="rapp-work-manager-"))
        self.addCleanup(shutil.rmtree, self.root)
        self.registry = self.root / "config" / "workspaces.json"
        self.workspace = self.root / "workspaces" / "finance"
        self.workspace.parent.mkdir()

    def args(self, **values):
        values.setdefault("mode", "solo")
        return types.SimpleNamespace(registry=str(self.registry), **values)

    def test_create_carries_project_skills_and_pointer_only_registry(self):
        result = MANAGER.create(
            self.args(
                path=str(self.workspace),
                owner_label="example-owner",
                slug="finance",
                world_id="example-business",
            )
        )
        self.assertEqual(result["status"], "created")
        record = json.loads((self.workspace / "rappid.json").read_text())
        self.assertEqual(record["workspace_spec"], "rapp-workspace/2.0")
        self.assertTrue(MANAGER.R.rappid_valid(record["rappid"]))
        for name in ("rapp-workspace", "rapp-private-hive", "rapp-workspace-manager"):
            self.assertTrue((self.workspace / ".github" / "skills" / name / "SKILL.md").is_file())
        registry = json.loads(self.registry.read_text())
        self.assertEqual(len(registry["workspaces"]), 1)
        self.assertEqual(
            set(registry["workspaces"][0]),
            {"rappid", "name", "path", "world_id", "mode", "active"},
        )
        self.assertNotIn("content", self.registry.read_text())

    def test_register_is_idempotent_and_world_scoped(self):
        MANAGER.create(
            self.args(
                path=str(self.workspace),
                owner_label="example-owner",
                slug="finance",
                world_id="example-business",
            )
        )
        first = MANAGER.register(self.workspace, self.registry)
        second = MANAGER.register(self.workspace, self.registry)
        self.assertEqual(first, second)
        self.assertEqual(len(json.loads(self.registry.read_text())["workspaces"]), 1)

    def test_existing_or_symlink_target_is_refused(self):
        self.workspace.mkdir()
        with self.assertRaisesRegex(ValueError, "must not already exist"):
            MANAGER.create(
                self.args(
                    path=str(self.workspace),
                    owner_label="example-owner",
                    slug="finance",
                    world_id="example-business",
                )
            )
        self.workspace.rmdir()
        target = self.root / "external"
        target.mkdir()
        self.workspace.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "must not already exist"):
            MANAGER.create(
                self.args(
                    path=str(self.workspace),
                    owner_label="example-owner",
                    slug="finance",
                    world_id="example-business",
                )
            )

    def test_invalid_existing_workspace_is_not_registered(self):
        self.workspace.mkdir()
        (self.workspace / "rappid.json").write_text(
            json.dumps(
                {
                    "schema": "rapp/1",
                    "rappid": "rappid:@example/workspace:" + "a" * 64,
                    "world_id": "Other World",
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "world_id"):
            MANAGER.register(self.workspace, self.registry)
        self.assertFalse(self.registry.exists())

    def test_created_hive_workspace_forces_lease_without_environment_flag(self):
        result = MANAGER.create(
            self.args(
                path=str(self.workspace),
                owner_label="example-owner",
                slug="finance",
                world_id="example-business",
                mode="hive",
            )
        )
        self.assertEqual(result["workspace"]["mode"], "hive")
        tool = self.workspace / "tools" / "append_frame.py"
        environment = dict(os.environ)
        environment.pop("RAPP_REQUIRE_LEASE", None)
        environment["RAPP1_PATH"] = str(ROOT / "vendor" / "rapp-1")
        genesis = subprocess.run(
            [
                sys.executable, str(tool), "--genesis", "--project", "demo",
                "--title", "Demo", "--goal", "Lease test",
            ],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(genesis.returncode, 0, genesis.stderr)
        append = subprocess.run(
            [
                sys.executable, str(tool), "--project", "demo",
                "--event", "work.checkpoint", "--actor", "alice",
                "--payload", '{"step":"must-refuse"}',
            ],
            cwd=self.workspace,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(append.returncode, 0)
        self.assertIn("strict lease mode", append.stderr + append.stdout)


if __name__ == "__main__":
    unittest.main()
