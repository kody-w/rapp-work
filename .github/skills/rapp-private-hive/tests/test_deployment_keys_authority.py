from __future__ import annotations

import copy
import os
from pathlib import Path
import stat
import unittest

from _deployment_fixtures import Fixture, FixtureTest, P
from private_hive import keys, release
from private_hive.authority import authenticated_registry
from private_hive.common import H, R, canonical, digest, parse, particle, read_file, unb64
from private_hive.state import State


class KeyCustodyTests(FixtureTest):
    def test_explicit_creation_load_and_no_remint(self):
        directory = self.fx.custody
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for name in ("owner.pk8.pem", "identity.json"):
            self.assertEqual(stat.S_IMODE((directory / name).stat().st_mode), 0o600)
        before = (directory / "owner.pk8.pem").read_bytes()
        loaded = keys.load(directory, expected_rappid=self.fx.key.rappid)
        self.assertEqual(loaded.spki, self.fx.key.spki)
        with self.assertRaisesRegex(ValueError, "never remint"):
            keys.create(directory, "fictional-owner")
        self.assertEqual(before, (directory / "owner.pk8.pem").read_bytes())

    def test_missing_or_partial_custody_never_remints(self):
        (self.fx.custody / "owner.pk8.pem").unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            keys.load(self.fx.custody)
        with self.assertRaises(ValueError):
            keys.create(self.fx.custody, "fictional-owner")
        self.assertFalse((self.fx.custody / "owner.pk8.pem").exists())
        with self.assertRaises(ValueError):
            keys.load(self.fx.root / "missing")
        self.assertFalse((self.fx.root / "missing").exists())

    def test_permissive_directory_and_file_refused_without_chmod(self):
        self.fx.custody.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "0700"):
            keys.load(self.fx.custody)
        self.assertEqual(stat.S_IMODE(self.fx.custody.stat().st_mode), 0o755)
        self.fx.custody.chmod(0o700)
        private = self.fx.custody / "owner.pk8.pem"
        private.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "0600"):
            keys.load(self.fx.custody)

    def test_symlink_and_hardlink_private_keys_refused(self):
        private = self.fx.custody / "owner.pk8.pem"
        saved = self.fx.root / "original.pk8.pem"
        private.rename(saved)
        private.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, "symlink"):
            keys.load(self.fx.custody)
        private.unlink()
        os.link(saved, private)
        with self.assertRaisesRegex(ValueError, "hardlinked"):
            keys.load(self.fx.custody)

    def test_identity_substitution_wrong_owner_and_extra_files_refused(self):
        other = R.mint_rappid("fictional-other", "owner", self.fx.key.spki)
        with self.assertRaisesRegex(ValueError, "owner mismatch"):
            keys.load(self.fx.custody, expected_rappid=other)
        (self.fx.custody / "unexpected").write_text("not key material")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            keys.load(self.fx.custody)

    def test_symlinked_parent_refused_before_key_creation(self):
        parent = self.fx.root / "link"
        parent.symlink_to(self.fx.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            keys.create(parent / "new-key", "fictional-owner")
        self.assertFalse((self.fx.root / "new-key").exists())


class AuthorityTests(FixtureTest):
    def initialized(self):
        self.fx.init()
        return State.readonly_snapshot(self.fx.publisher)["authority"]

    def test_signed_anchor_exact_registry_spki_kinds_and_genesis(self):
        authority = self.initialized()
        anchor = keys.verify_anchor(canonical(authority["anchor"]))
        registry = authenticated_registry(canonical(authority["registry"]), anchor)
        self.assertEqual(registry._kinds, {kind: "body" for kind in H.KIND_SCHEMAS})
        self.assertEqual(registry._keys, {self.fx.key.rappid: self.fx.key.spki})
        self.assertEqual(len(registry._genesis), 3)
        self.assertEqual(anchor["hive_rappid"], self.fx.prepared["hive_rappid"])
        self.assertIn(self.fx.prepared["dimension_rappid"], registry._genesis)
        self.assertEqual(anchor["genesis_frame_hash"], registry._genesis[anchor["hive_rappid"]])
        self.assertEqual(self.fx.original_bytes(), self.fx.data)

    def test_registry_signatures_spec_pin_kind_and_genesis_fail_closed(self):
        authority = self.initialized()
        for variation in ("sig", "protocol", "kind", "spki", "genesis", "rotation"):
            with self.subTest(variation=variation):
                registry = copy.deepcopy(authority["registry"])
                if variation == "sig":
                    registry["sig"] = "invalid"
                else:
                    if variation == "protocol":
                        next(item for item in registry["entries"] if item["type"] == "protocol")["spec_hash"] = "1" * 64
                    elif variation == "kind":
                        next(item for item in registry["entries"] if item["type"] == "kind")["family"] = "mind"
                    elif variation == "spki":
                        next(item for item in registry["entries"] if item["type"] == "spki")["spki_der_b64"] = "AAAA"
                    elif variation == "genesis":
                        next(item for item in registry["entries"] if item.get("stream_id") == authority["anchor"]["hive_rappid"])["frame_hash"] = "2" * 64
                    else:
                        registry["entries"].append({"type": "re-anchor"})
                    registry.pop("sig")
                    registry = self.fx.key.signed(registry)
                with self.assertRaises(ValueError):
                    authenticated_registry(canonical(registry), authority["anchor"])

    def test_monotonic_registry_rollback_and_same_sequence_fork(self):
        authority = self.initialized()
        registry = copy.deepcopy(authority["registry"])
        registry.pop("sig")
        registry["registry_seq"] = 0
        with self.assertRaisesRegex(ValueError, "rollback"):
            authenticated_registry(canonical(self.fx.key.signed(registry)), authority["anchor"])
        registry["registry_seq"] = 1
        registry["canonical_source"] += "-fork"
        with self.assertRaisesRegex(ValueError, "fork"):
            authenticated_registry(canonical(self.fx.key.signed(registry)), authority["anchor"])

    def test_prepared_keyless_owner_requires_explicit_first_binding(self):
        fixture = Fixture(keyless_owner=True)
        self.addCleanup(fixture.close)
        with self.assertRaisesRegex(ValueError, "adopt-prepared-owner"):
            release.initialize(fixture.workspace, fixture.publisher, fixture.key, fixture.channels)
        self.assertFalse(fixture.publisher.exists())
        result = fixture.init()
        self.assertEqual(result["anchor"]["hive_rappid"], fixture.prepared["hive_rappid"])
        self.assertEqual(P.read_json(fixture.workspace / ".rapp-hive" / "state.json"), fixture.prepared)
        self.assertEqual(fixture.original_bytes(), fixture.data)

    def test_existing_authority_is_refused_not_replaced(self):
        old = self.fx.workspace / "registry.json"
        old.write_bytes(canonical({"schema": "rapp/1-registry", "sig": "not-trusted"}))
        before = old.read_bytes()
        with self.assertRaisesRegex(ValueError, "existing authority"):
            self.fx.init()
        self.assertEqual(old.read_bytes(), before)
        self.assertFalse(self.fx.publisher.exists())

    def test_existing_channel_authority_cannot_be_silently_bootstrapped_again(self):
        built = self.fx.first_release()
        self.fx.publish(built["plan_hash"])
        other_state = self.fx.root / "must-import"
        with self.assertRaisesRegex(ValueError, "existing channel authority"):
            release.initialize(self.fx.workspace, other_state, self.fx.key, self.fx.channels)
        self.assertFalse(other_state.exists())

    def test_unsupported_channels_and_topology_refuse_before_effects(self):
        for kind in ("sharepoint", "public-git", "federation", "lan"):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    release.initialize(self.fx.workspace, self.fx.publisher, self.fx.key,
                                       [{"id": "unsupported", "kind": kind, "role": "authority"}])
                self.assertFalse(self.fx.publisher.exists())
                self.assertFalse(self.fx.channel_root.exists())
        self.fx.init()
        database = read_file(self.fx.publisher / "state.sqlite3", private=True)
        changed = [{**self.fx.channels[0], "id": "different"}]
        with self.assertRaisesRegex(ValueError, "topology"):
            release.initialize(self.fx.workspace, self.fx.publisher, self.fx.key, changed)
        self.assertEqual(read_file(self.fx.publisher / "state.sqlite3", private=True), database)

    def test_repeated_initialization_and_anchor_export_are_immutable(self):
        first = self.fx.init()
        second = self.fx.init()
        self.assertEqual(first["anchor"], second["anchor"])
        destination = self.fx.root / "out-of-band-anchor.json"
        release.export_anchor(self.fx.publisher, destination)
        before = destination.read_bytes()
        release.export_anchor(self.fx.publisher, destination)
        self.assertEqual(destination.read_bytes(), before)
        self.assertNotIn(b"PRIVATE KEY", before)


if __name__ == "__main__":
    unittest.main()
