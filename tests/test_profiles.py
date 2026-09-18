from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from rapp_work import ProfileRegistry
from rapp_work.errors import Refusal
from rapp_work.profiles import verify_source_estate

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_COMMIT = "591e014ad39e223b00ab343ae26e5d9a867ebeee"
CANONICAL_WORK_SPEC_SHA256 = "283359355c3fe2858e28744368255683af3ed28a68e290e56c231e7d4b13c08e"
CANONICAL_WORK_SCHEMA_SHA256 = "ff30f9878f12fa4ad7d93c4c205eb1cb580137a7dee87aa9d23c88a93466d19e"
HISTORICAL_WORK_SPEC_SHA256 = "861920ed31dd31412cc67064532ca855e3d9f842f1f63fa7f3daeab605fddf7e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_default_registry_has_qualified_profile_order() -> None:
    registry = ProfileRegistry.default()
    assert registry.ids() == (
        "rapp/1",
        "rapp-work/1",
        "rapp-work-sdk/1",
        "rapp-hive/1",
        "rapp-federation/1",
    )
    assert registry.verify()["status"] == "verified"
    work = registry.get("rapp-work/1")
    assert work.authority == "accepted-canonical-protocol"
    assert work.activation == "sdk-parent-pin-not-estate-activation"
    assert work.spec_sha256 == CANONICAL_WORK_SPEC_SHA256
    assert work.schema_sha256 == CANONICAL_WORK_SCHEMA_SHA256


def test_parent_pins_and_packaged_canonical_resources_are_exact() -> None:
    root_parent = json.loads((ROOT / "RAPP1_PIN.json").read_bytes())
    packaged_parent = json.loads((ROOT / "src/rapp_work/data/RAPP1_PIN.json").read_bytes())
    root_work = json.loads((ROOT / "RAPP_WORK_PIN.json").read_bytes())
    packaged_work = json.loads((ROOT / "src/rapp_work/data/RAPP_WORK_PIN.json").read_bytes())

    assert root_parent == packaged_parent
    assert root_work == packaged_work
    assert root_parent["commit"] == root_work["commit"] == CANONICAL_COMMIT
    assert set(root_work) == {
        "commit",
        "protocol",
        "repository",
        "schema",
        "schema_path",
        "schema_sha256",
        "spec_path",
        "spec_sha256",
    }
    assert root_work["repository"] == "https://github.com/kody-w/rapp-1"
    assert root_work["spec_path"] == "protocols/rapp-work/1/SPEC.md"
    assert root_work["schema_path"] == "protocols/rapp-work/1/schema.json"
    assert (
        sha256(ROOT / "src/rapp_work/data/rapp-work-1-SPEC.md")
        == root_work["spec_sha256"]
        == CANONICAL_WORK_SPEC_SHA256
    )
    assert (
        sha256(ROOT / "src/rapp_work/data/rapp-work-1-schema.json")
        == root_work["schema_sha256"]
        == CANONICAL_WORK_SCHEMA_SHA256
    )


def test_sdk_parent_pin_is_distinct_from_historical_signed_estate_pin() -> None:
    result = verify_source_estate(ROOT)
    assert result["signed_profiles"] == [
        "rapp-federation/1",
        "rapp-hive/1",
        "rapp-work/1",
        "rapp/1",
    ]
    assert "rapp-work-sdk/1" not in result["signed_profiles"]
    assert result["rapp1_parent_pin"]["commit"] == CANONICAL_COMMIT
    assert result["sdk_parent_pin"]["spec_sha256"] == CANONICAL_WORK_SPEC_SHA256
    assert result["sdk_parent_pin"]["schema_sha256"] == CANONICAL_WORK_SCHEMA_SHA256
    assert result["historical_signed_estate_pin"] == {
        "protocol": "rapp-work/1",
        "repository": "https://github.com/kody-w/rapp-work",
        "spec_path": "SPEC.md",
        "spec_sha256": HISTORICAL_WORK_SPEC_SHA256,
    }
    assert sha256(ROOT / "SPEC.md") == HISTORICAL_WORK_SPEC_SHA256
    assert (
        result["historical_signed_estate_pin"]["spec_sha256"]
        != result["sdk_parent_pin"]["spec_sha256"]
    )


def test_source_estate_refuses_nonclosed_work_pin(sandbox: Path) -> None:
    (sandbox / "RAPP1_PIN.json").write_bytes((ROOT / "RAPP1_PIN.json").read_bytes())
    work_pin = json.loads((ROOT / "RAPP_WORK_PIN.json").read_bytes())
    work_pin["unsigned_extension"] = True
    (sandbox / "RAPP_WORK_PIN.json").write_text(json.dumps(work_pin), encoding="utf-8")
    with pytest.raises(Refusal, match="REFUSE_INPUT_KEYS"):
        verify_source_estate(sandbox)


def test_profile_hash_mutation_refuses() -> None:
    base = ProfileRegistry.default()
    profiles = list(base.descriptors())
    profiles[2] = replace(profiles[2], spec_sha256="0" * 64)
    mutated = ProfileRegistry(profiles)
    with pytest.raises(Refusal, match="REFUSE_PROFILE_HASH"):
        mutated.verify()


def test_canonical_work_descriptor_mutation_refuses() -> None:
    base = ProfileRegistry.default()
    profiles = list(base.descriptors())
    profiles[1] = replace(profiles[1], authority="signed-estate-profile")
    mutated = ProfileRegistry(profiles)
    with pytest.raises(Refusal, match="REFUSE_WORK_PIN"):
        mutated.verify()


def test_duplicate_and_missing_parent_refuse() -> None:
    registry = ProfileRegistry.default()
    with pytest.raises(Refusal, match="REFUSE_PROFILE_DUPLICATE"):
        registry.register(registry.get("rapp/1"))
    orphan = replace(registry.get("rapp-work-sdk/1"), id="orphan/1", parent="missing/1")
    empty = ProfileRegistry()
    with pytest.raises(Refusal, match="REFUSE_PROFILE_PARENT"):
        empty.register(orphan)
