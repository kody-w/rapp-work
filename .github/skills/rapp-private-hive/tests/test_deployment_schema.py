from __future__ import annotations

import copy
import json
import unittest

from jsonschema import Draft202012Validator, FormatChecker

from _deployment_fixtures import FixtureTest, SKILL
from private_hive import client, release
from private_hive.common import canonical, parse, safe_path_set


class DeploymentSchemaTests(FixtureTest):
    def test_generated_artifacts_match_closed_deployment_schemas(self):
        schema = json.loads((SKILL / "schemas/deployment.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        built = self.fx.first_release(pending=True)
        release.approve(self.fx.publisher, self.fx.key, built["plan_hash"])
        frozen = self.fx.frozen(built["plan_hash"])
        documents = [built["plan"], frozen["approval"], parse(frozen["pointer"]),
                     release.export_anchor(self.fx.publisher),
                     parse((self.fx.custody / "identity.json").read_bytes()),
                     {"schema": "rapp-private-hive-channels/1", "channels": self.fx.channels}]
        tags = {definition["properties"]["schema"]["const"] for definition in schema["$defs"].values()
                if isinstance(definition, dict) and "schema" in definition.get("properties", {})}
        for raw in frozen["files"].values():
            value = parse(raw)
            if value.get("schema") in tags:
                documents.append(value)
        self.assertGreater(len(documents), 15)
        for value in documents:
            with self.subTest(schema=value["schema"]):
                validator.validate(value)
                invalid = {**value, "unexpected_private_metadata": "not allowed"}
                self.assertFalse(validator.is_valid(invalid))

    def test_canonical_boundary_refuses_duplicates_floats_and_noncanonical_bytes(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":1.5}', b'{"a": 1}', b'[]', b'{"a":9007199254740992}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse(raw)
        self.assertEqual(parse(canonical({"a": 1})), {"a": 1})

    def test_unicode_data_paths_round_trip_and_normalization_aliases_refuse(self):
        source = self.fx.workspace / "safe/資料.txt"
        source.write_bytes(b"Generic public Unicode filename fixture.")
        self.fx.select("safe/資料.txt", data_class="neutral")
        built = self.fx.first_release(selected=False)
        schema = json.loads((SKILL / "schemas/deployment.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(built["plan"])
        self.fx.publish(built["plan_hash"])
        self.fx.init_client()
        client.pull(self.fx.client, self.fx.channels[0])
        rendered = client.materialize(self.fx.client, self.fx.output)
        from pathlib import Path
        self.assertEqual((Path(rendered["generation"]) / "rooms/general/safe/資料.txt").read_bytes(), source.read_bytes())
        with self.assertRaisesRegex(ValueError, "colliding"):
            safe_path_set(["safe/é.txt", "safe/e\u0301.txt"])

    def test_vendored_authenticated_profile_is_byte_exact_and_standalone(self):
        source = SKILL.parents[2] / "protocols/rapp-hive/1"
        for path in (SKILL / "vendor/hive").rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                original = source / path.relative_to(SKILL / "vendor/hive")
                self.assertTrue(original.is_file(), original.name)
                self.assertEqual(path.read_bytes(), original.read_bytes(), path.name)
        self.assertEqual((SKILL / "vendor/rapp.py").read_bytes(), (SKILL / "vendor/hive/reference/rapp.py").read_bytes())


if __name__ == "__main__":
    unittest.main()
