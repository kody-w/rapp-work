from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import types
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_workspace.py"
SPEC = importlib.util.spec_from_file_location("prepare_workspace", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WorkspacePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp(prefix="rapp-private-hive-test-"))
        self.addCleanup(shutil.rmtree, self.temporary)
        self.workspace = self.temporary / "workspace"
        self.workspace.mkdir()
        self.member = "rappid:@alice/member:" + "1" * 64
        self.workspace_rappid = "rappid:@alice/workspace:" + "2" * 64
        (self.workspace / "rappid.json").write_text(
            json.dumps({"schema": "rapp/1", "rappid": self.workspace_rappid, "mode": "solo"}),
            encoding="utf-8",
        )
        (self.workspace / "notes").mkdir()
        (self.workspace / "notes" / "private.md").write_text("private GODD", encoding="utf-8")
        (self.workspace / "dogg").mkdir()
        (self.workspace / "dogg" / "template.json").write_text('{"safe":true}', encoding="utf-8")
        self.before = {
            path.relative_to(self.workspace).as_posix(): path.read_bytes()
            for path in self.workspace.rglob("*")
            if path.is_file()
        }
        self.scanner_key = Ed25519PrivateKey.generate()
        self.scanner_spki = self.scanner_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.scanner_rappid = MODULE.R.mint_rappid(
            "fictional-scanner",
            "pii",
            spki_der=self.scanner_spki,
        )

    def args(self, **values):
        return types.SimpleNamespace(**values)

    def prepare(self):
        result = MODULE.command_prepare(
            self.args(
                workspace=str(self.workspace),
                member_rappid=self.member,
                hive_name="alice-private-hive",
                world_id="alice-world",
            )
        )
        MODULE.command_trust_scanner(
            self.args(
                workspace=str(self.workspace),
                scanner_rappid=self.scanner_rappid,
                spki_sha256=hashlib.sha256(self.scanner_spki).hexdigest(),
            )
        )
        return result

    @staticmethod
    def b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def pii_receipt(self, relative: str, *, file_hash: str | None = None, result: str = "none") -> Path:
        source = self.workspace / relative
        unsigned = {
            "schema": "rapp-pii-scan/1",
            "file_sha256": file_hash or hashlib.sha256(source.read_bytes()).hexdigest(),
            "result": result,
            "scanner_rappid": self.scanner_rappid,
            "scanner_version": "1.0.0",
            "scanned_utc": MODULE.utc_now(),
            "spki_der_b64": base64.b64encode(self.scanner_spki).decode("ascii"),
        }
        header = {
            "alg": "EdDSA",
            "b64": False,
            "crit": ["b64"],
            "kid": self.scanner_rappid,
        }
        protected = self.b64url(MODULE.canonical_bytes(header))
        signature = self.scanner_key.sign(
            protected.encode("ascii") + b"." + MODULE.canonical_bytes(unsigned)
        )
        receipt = {**unsigned, "sig": f"{protected}..{self.b64url(signature)}"}
        path = self.temporary / f"pii-{len(list(self.temporary.glob('pii-*.json')))}.json"
        path.write_bytes(MODULE.canonical_bytes(receipt))
        return path

    @staticmethod
    def generation_root(stage_result: dict) -> Path:
        return Path(stage_result["outbox"]) / "generations" / stage_result["generation"]

    def assert_original_bytes_unchanged(self):
        for relative, expected in self.before.items():
            self.assertEqual((self.workspace / relative).read_bytes(), expected)

    def test_prepare_is_additive_and_idempotent(self):
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first["status"], "prepared")
        self.assertEqual(second["status"], "already-prepared")
        self.assertEqual(first["hive_rappid"], second["hive_rappid"])
        self.assertEqual(first["workspace_rappid"], self.workspace_rappid)
        state = MODULE.read_json(self.workspace / ".rapp-hive" / "state.json")
        self.assertEqual(second["dimension_rappid"], state["dimension_rappid"])
        self.assert_original_bytes_unchanged()
        selection = MODULE.read_json(self.workspace / ".rapp-hive" / "selection.json")
        self.assertEqual(selection["default"], "local-only")
        self.assertEqual(selection["entries"], [])

    def test_dogg_requires_pii_evidence_and_stages_by_copy(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "pii"):
            MODULE.command_select(
                self.args(
                    workspace=str(self.workspace),
                    path="dogg/template.json",
                    data_class="dogg",
                    room="general",
                    protection=None,
                    pii_evidence=None,
                )
            )
        evidence = self.pii_receipt("dogg/template.json")
        selected = MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(evidence),
            )
        )
        outbox = self.temporary / "outbox"
        staged = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(outbox))
        )
        self.assertEqual(selected["entry"]["pii_status"], "none")
        self.assertEqual(staged["staged"], 1)
        staged_file = self.generation_root(staged) / "objects" / "dogg" / "template.json"
        self.assertTrue(staged_file.is_file())
        self.assertEqual(staged_file.read_bytes(), (self.workspace / "dogg" / "template.json").read_bytes())
        self.assert_original_bytes_unchanged()

    def test_plaintext_godd_never_enters_outbox(self):
        self.prepare()
        selected = MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="notes/private.md",
                data_class="godd",
                room="private",
                protection="sealed-room",
                pii_evidence=None,
            )
        )
        outbox = self.temporary / "outbox"
        staged = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(outbox))
        )
        self.assertEqual(selected["entry"]["status"], "pending-seal")
        self.assertEqual(staged["staged"], 0)
        self.assertEqual(staged["pending_sealed"], ["notes/private.md"])
        self.assertFalse(any(path.name == "private.md" for path in outbox.rglob("*")))
        self.assert_original_bytes_unchanged()

    def test_every_sealed_room_selection_stays_pending_encryption(self):
        self.prepare()
        for data_class, relative in (
            ("dogg", "dogg/template.json"),
            ("neutral", "dogg/template.json"),
            ("godd", "notes/private.md"),
        ):
            with self.subTest(data_class=data_class):
                receipt = None
                if data_class != "godd":
                    receipt = str(self.pii_receipt(relative))
                result = MODULE.command_select(
                    self.args(
                        workspace=str(self.workspace),
                        path=relative,
                        data_class=data_class,
                        room="private",
                        protection="sealed-room",
                        pii_evidence=receipt,
                    )
                )
                self.assertEqual(result["entry"]["status"], "pending-seal")
                staged = MODULE.command_stage(
                    self.args(
                        workspace=str(self.workspace),
                        outbox=str(self.temporary / f"outbox-{data_class}"),
                    )
                )
                self.assertEqual(staged["staged"], 0)
                self.assertFalse(any(path.is_file() and path.name == Path(relative).name
                                     for path in Path(staged["outbox"]).rglob("objects/*")))

    def test_changed_selection_refuses_staging_without_deleting_source(self):
        self.prepare()
        evidence = self.pii_receipt("dogg/template.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(evidence),
            )
        )
        source = self.workspace / "dogg" / "template.json"
        source.write_text('{"safe":true,"evolved":true}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "reselect"):
            MODULE.command_stage(
                self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
            )
        self.assertTrue(source.is_file())

    def test_skill_lock_matches_every_managed_file(self):
        skill_root = Path(__file__).resolve().parents[1]
        lock = json.loads((skill_root / "rapp" / "agent.lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["schema"], "rapp-skill-lock/1")
        self.assertEqual(lock["name"], "rapp-private-hive")
        paths = [entry["path"] for entry in lock["files"]]
        self.assertEqual(set(paths), MODULE.MANAGED_SKILL_FILES)
        self.assertEqual(len(paths), len(set(paths)))
        for entry in lock["files"]:
            path = skill_root / entry["path"]
            self.assertTrue(path.is_file(), entry["path"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])

    def test_reclassification_to_godd_removes_prior_plaintext_generation(self):
        self.prepare()
        neutral_receipt = self.pii_receipt("notes/private.md")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="notes/private.md",
                data_class="neutral",
                room="general",
                protection=None,
                pii_evidence=str(neutral_receipt),
            )
        )
        first = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        self.assertTrue((self.generation_root(first) / "objects" / "notes" / "private.md").is_file())
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="notes/private.md",
                data_class="godd",
                room="private",
                protection="sealed-room",
                pii_evidence=None,
            )
        )
        second = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        self.assertFalse(any(path.name == "private.md" for path in Path(second["outbox"]).rglob("*")))
        self.assertFalse(self.generation_root(first).exists())

    def test_control_symlink_and_source_ancestor_symlink_are_refused(self):
        foreign = self.temporary / "foreign"
        foreign.mkdir()
        (foreign / "rappid.json").write_text(
            json.dumps({"schema": "rapp/1", "rappid": "rappid:@bob/workspace:" + "3" * 64}),
            encoding="utf-8",
        )
        control = self.workspace / ".rapp-hive"
        control.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.prepare()
        control.unlink()
        self.prepare()
        outside = self.temporary / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret", encoding="utf-8")
        (self.workspace / "linked").symlink_to(outside, target_is_directory=True)
        receipt = self.pii_receipt("dogg/template.json")
        with self.assertRaisesRegex(ValueError, "symlink"):
            MODULE.command_select(
                self.args(
                    workspace=str(self.workspace),
                    path="linked/secret.txt",
                    data_class="neutral",
                    room="general",
                    protection=None,
                    pii_evidence=str(receipt),
                )
            )

    def test_baseline_tamper_and_stale_selection_never_report_verified(self):
        self.prepare()
        baseline_path = self.workspace / ".rapp-hive" / "baseline.json"
        baseline = MODULE.read_json(baseline_path)
        baseline["files"].pop()
        baseline_path.write_bytes(MODULE.canonical_bytes(baseline))
        with self.assertRaisesRegex(ValueError, "baseline commitment"):
            MODULE.command_verify(self.args(workspace=str(self.workspace)))

        shutil.rmtree(self.workspace / ".rapp-hive")
        self.prepare()
        receipt = self.pii_receipt("dogg/template.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(receipt),
            )
        )
        (self.workspace / "dogg" / "template.json").write_text('{"changed":true}', encoding="utf-8")
        report = MODULE.command_verify(self.args(workspace=str(self.workspace)))
        self.assertEqual(report["status"], "selection-stale")
        self.assertEqual(report["stale_selection"], ["dogg/template.json"])

    def test_pii_receipt_must_be_signed_and_bound_to_exact_file(self):
        self.prepare()
        wrong = self.pii_receipt("dogg/template.json", file_hash="0" * 64)
        with self.assertRaisesRegex(ValueError, "not bound"):
            MODULE.command_select(
                self.args(
                    workspace=str(self.workspace),
                    path="dogg/template.json",
                    data_class="dogg",
                    room="general",
                    protection=None,
                    pii_evidence=str(wrong),
                )
            )

    def test_prepare_rejects_configuration_mismatch(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.command_prepare(
                self.args(
                    workspace=str(self.workspace),
                    member_rappid=self.member,
                    hive_name="different-hive",
                    world_id="alice-world",
                )
            )

    def test_incomplete_or_permissive_control_generation_is_refused(self):
        control = self.workspace / ".rapp-hive"
        control.mkdir(mode=0o700)
        state_path = control / "state.json"
        state_path.write_text("{}", encoding="utf-8")
        state_path.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "incomplete|wrong schema"):
            self.prepare()
        shutil.rmtree(control)
        self.prepare()
        control.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "0700"):
            MODULE.command_verify(self.args(workspace=str(self.workspace)))

    def test_outbox_symlink_is_refused_and_private_modes_are_enforced(self):
        self.prepare()
        receipt = self.pii_receipt("dogg/template.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(receipt),
            )
        )
        target = self.temporary / "outside-outbox"
        target.mkdir()
        link = self.temporary / "linked-outbox"
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            MODULE.command_stage(self.args(workspace=str(self.workspace), outbox=str(link)))
        result = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        stage_root = Path(result["outbox"])
        self.assertEqual(stat.S_IMODE(stage_root.stat().st_mode), 0o700)
        for path in stage_root.rglob("*"):
            if path.is_dir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            elif path.is_file():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_failed_restage_leaves_previous_generation_current(self):
        self.prepare()
        first_receipt = self.pii_receipt("dogg/template.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(first_receipt),
            )
        )
        first = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        (self.workspace / "dogg" / "second.json").write_text('{"safe":true}', encoding="utf-8")
        second_receipt = self.pii_receipt("dogg/second.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/second.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(second_receipt),
            )
        )
        (self.workspace / "dogg" / "second.json").write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "reselect"):
            MODULE.command_stage(
                self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
            )
        current = MODULE.read_json(Path(first["outbox"]) / "current.json")
        self.assertEqual(current["generation"], first["generation"])
        self.assertTrue(self.generation_root(first).is_dir())

    def test_restage_repairs_corrupted_existing_generation(self):
        self.prepare()
        receipt = self.pii_receipt("dogg/template.json")
        MODULE.command_select(
            self.args(
                workspace=str(self.workspace),
                path="dogg/template.json",
                data_class="dogg",
                room="general",
                protection=None,
                pii_evidence=str(receipt),
            )
        )
        first = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        staged_file = self.generation_root(first) / "objects" / "dogg" / "template.json"
        expected = (self.workspace / "dogg" / "template.json").read_bytes()
        staged_file.write_bytes(b"CORRUPTED")
        second = MODULE.command_stage(
            self.args(workspace=str(self.workspace), outbox=str(self.temporary / "outbox"))
        )
        self.assertEqual(second["generation"], first["generation"])
        self.assertEqual(staged_file.read_bytes(), expected)

    def test_unselected_workspace_edits_are_reported_as_evolution(self):
        self.prepare()
        (self.workspace / "notes" / "private.md").write_text("organically evolved", encoding="utf-8")
        report = MODULE.command_verify(self.args(workspace=str(self.workspace)))
        self.assertEqual(report["status"], "workspace-evolved")
        self.assertEqual(report["baseline_changes"], ["notes/private.md"])

    def test_derived_stage_root_cannot_overlap_workspace(self):
        self.prepare()
        declaration = MODULE.read_json(self.workspace / ".rapp-hive" / "declaration.json")
        hive_key = hashlib.sha256(declaration["hive_rappid"].encode("utf-8")).hexdigest()[:24]
        outbox = self.temporary / "outbox"
        outbox.mkdir(mode=0o700)
        relocated = outbox / f"hive-{hive_key}"
        self.workspace.rename(relocated)
        self.workspace = relocated
        with self.assertRaisesRegex(ValueError, "overlaps"):
            MODULE.command_stage(self.args(workspace=str(self.workspace), outbox=str(outbox)))

    def test_windows_drive_paths_are_rejected(self):
        for path in ("C:/outside/private.json", "c:relative.txt", "folder/name:stream"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    MODULE.safe_relative(path)

    def test_large_local_control_json_is_not_limited_to_frame_size(self):
        path = self.temporary / "large.json"
        value = {"schema": "fixture/1", "items": ["x" * 200 for _ in range(6000)]}
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assertGreater(path.stat().st_size, 1024 * 1024)
        self.assertEqual(MODULE.read_json(path), value)

    def test_legacy_workspace_migration_is_additive_identity_preserving_and_idempotent(self):
        first = MODULE.command_migrate(
            self.args(
                workspace=str(self.workspace),
                member_rappid=self.member,
                hive_name="alice-private-hive",
                world_id="alice-world",
            )
        )
        second = MODULE.command_migrate(
            self.args(
                workspace=str(self.workspace),
                member_rappid=self.member,
                hive_name="alice-private-hive",
                world_id="alice-world",
            )
        )
        self.assertEqual(first["status"], "migrated")
        self.assertEqual(second["status"], "already-migrated")
        self.assertEqual(first["migration_id"], second["migration_id"])
        self.assertEqual(first["workspace_rappid"], self.workspace_rappid)
        self.assertTrue(first["identity_preserved"])
        self.assertTrue(first["original_bytes_unchanged"])
        self.assertEqual(first["source_workspace_spec"], "legacy-unversioned")
        self.assertEqual(first["project_skill"]["status"], "embedded")
        project_skill = self.workspace / ".github" / "skills" / "rapp-private-hive"
        self.assertTrue((project_skill / "SKILL.md").is_file())
        preflight = subprocess.run(
            [sys.executable, str(project_skill / "scripts" / "deploy_hive.py"), "--preflight"],
            cwd=project_skill,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(preflight.returncode, 0, preflight.stderr)
        self.assert_original_bytes_unchanged()

    def test_migration_refuses_workspace_changes_after_prior_preparation(self):
        MODULE.command_prepare(
            self.args(
                workspace=str(self.workspace),
                member_rappid=self.member,
                hive_name="alice-private-hive",
                world_id="alice-world",
            )
        )
        source = self.workspace / "notes" / "private.md"
        source.write_text("changed after preparation", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            MODULE.command_migrate(
                self.args(
                    workspace=str(self.workspace),
                    member_rappid=self.member,
                    hive_name="alice-private-hive",
                    world_id="alice-world",
                )
            )
        self.assertEqual(source.read_text(encoding="utf-8"), "changed after preparation")

    def test_migration_preserves_legacy_symlinks_without_following_them(self):
        link = self.workspace / "notes" / "current-private"
        link.symlink_to("private.md")
        result = MODULE.command_migrate(
            self.args(
                workspace=str(self.workspace),
                member_rappid=self.member,
                hive_name="alice-private-hive",
                world_id="alice-world",
            )
        )
        self.assertEqual(result["status"], "migrated")
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.readlink().as_posix(), "private.md")
        report = MODULE.command_verify(self.args(workspace=str(self.workspace)))
        self.assertEqual(report["status"], "verified")

    def test_migration_refuses_symlinked_project_skill_or_parent(self):
        external = self.temporary / "external-skill"
        shutil.copytree(MODULE.ROOT, external)
        project = self.workspace / ".github"
        project.mkdir()
        skills = project / "skills"
        skills.mkdir()
        (skills / "rapp-private-hive").symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            MODULE.command_migrate(
                self.args(
                    workspace=str(self.workspace),
                    member_rappid=self.member,
                    hive_name="alice-private-hive",
                    world_id="alice-world",
                )
            )
        shutil.rmtree(self.workspace / ".rapp-hive")
        shutil.rmtree(project)
        outside = self.temporary / "outside-skills"
        outside.mkdir()
        project.mkdir()
        (project / "skills").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            MODULE.command_migrate(
                self.args(
                    workspace=str(self.workspace),
                    member_rappid=self.member,
                    hive_name="alice-private-hive",
                    world_id="alice-world",
                )
            )


if __name__ == "__main__":
    unittest.main()
