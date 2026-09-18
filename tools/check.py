#!/usr/bin/env python3
"""Verify the RAPP Work standards estate and execute profile conformance."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "rapp-1"
sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT / "src"))

import rapp as R  # noqa: E402
import rapp_registry as REG  # noqa: E402

from rapp_work.discovery import api_metadata  # noqa: E402
from rapp_work.profiles import ProfileRegistry, verify_source_estate  # noqa: E402

CANONICAL_COMMIT = "591e014ad39e223b00ab343ae26e5d9a867ebeee"
CANONICAL_REPOSITORY = "https://github.com/kody-w/rapp-1"
RAPP1_PIN_KEYS = {
    "commit",
    "protocol",
    "reference_path",
    "reference_sha256",
    "repository",
    "schema",
    "spec_path",
    "spec_sha256",
}
RAPP_WORK_PIN_KEYS = {
    "commit",
    "protocol",
    "repository",
    "schema",
    "schema_path",
    "schema_sha256",
    "spec_path",
    "spec_sha256",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


pin = json.loads((ROOT / "RAPP1_PIN.json").read_text(encoding="utf-8"))
packaged_pin = json.loads(
    (ROOT / "src/rapp_work/data/RAPP1_PIN.json").read_text(encoding="utf-8")
)
require(set(pin) == RAPP1_PIN_KEYS, "RAPP/1 pin is not closed")
require(pin == packaged_pin, "root and packaged RAPP/1 pins differ")
require(
    pin["schema"] == "rapp-work-parent-pin/1"
    and pin["protocol"] == "rapp/1"
    and pin["repository"] == CANONICAL_REPOSITORY
    and pin["commit"] == CANONICAL_COMMIT
    and pin["spec_path"] == "SPEC.md"
    and pin["reference_path"] == "rapp.py",
    "wrong RAPP/1 pin contract",
)
require(
    sha(VENDOR / "SPEC.md") == pin["spec_sha256"],
    "vendored RAPP/1 SPEC hash mismatch",
)
require(sha(VENDOR / "rapp.py") == pin["reference_sha256"], "vendored rapp.py hash mismatch")

work_pin = json.loads((ROOT / "RAPP_WORK_PIN.json").read_text(encoding="utf-8"))
packaged_work_pin = json.loads(
    (ROOT / "src/rapp_work/data/RAPP_WORK_PIN.json").read_text(encoding="utf-8")
)
require(set(work_pin) == RAPP_WORK_PIN_KEYS, "RAPP Work SDK parent pin is not closed")
require(work_pin == packaged_work_pin, "root and packaged RAPP Work SDK parent pins differ")
require(
    work_pin["schema"] == "rapp-work-sdk-parent-pin/1"
    and work_pin["protocol"] == "rapp-work/1"
    and work_pin["repository"] == CANONICAL_REPOSITORY
    and work_pin["commit"] == CANONICAL_COMMIT
    and work_pin["spec_path"] == "protocols/rapp-work/1/SPEC.md"
    and work_pin["schema_path"] == "protocols/rapp-work/1/schema.json",
    "wrong RAPP Work SDK parent pin contract",
)
require(
    sha(ROOT / "src/rapp_work/data/rapp-work-1-SPEC.md") == work_pin["spec_sha256"],
    "packaged canonical RAPP Work SPEC hash mismatch",
)
require(
    sha(ROOT / "src/rapp_work/data/rapp-work-1-schema.json")
    == work_pin["schema_sha256"],
    "packaged canonical RAPP Work schema hash mismatch",
)
require(
    pin["repository"] == work_pin["repository"] and pin["commit"] == work_pin["commit"],
    "canonical RAPP/1 and RAPP Work revisions differ",
)

identity = json.loads((ROOT / "rappid.json").read_text(encoding="utf-8"))
anchor = json.loads((ROOT / "owner-anchor.json").read_text(encoding="utf-8"))
registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
require(identity["schema"] == "rapp/1" and R.rappid_valid(identity["rappid"]), "invalid repository RAPPID")
require(anchor["schema"] == "rapp-work-anchor/1", "invalid owner anchor schema")
require(anchor["owner_rappid"] == identity["rappid"], "anchor/repository identity mismatch")
spki = base64.b64decode(anchor["spki_der_b64"], validate=True)
require(hashlib.sha256(spki).hexdigest() == anchor["spki_sha256"], "anchor SPKI checksum mismatch")
require(R.rappid_parts(anchor["owner_rappid"])["hash"] == R.Hb("rapp/1:rappid", spki),
        "anchor key does not bind the owner RAPPID")
unsigned = {key: value for key, value in registry.items() if key != "sig"}
ok, why = R.verify_detached_jws(unsigned, registry["sig"], spki, expected_kid=anchor["owner_rappid"])
require(ok, f"registry signature refused: {why}")
REG.Registry(registry["entries"])

index = json.loads((ROOT / "protocols" / "index.json").read_text(encoding="utf-8"))
profiles = {profile["name"]: profile for profile in index["profiles"]}
require(
    set(profiles) == {"rapp-work-sdk/1", "rapp-hive/1", "rapp-federation/1"},
    "unexpected profile index",
)
for profile in profiles.values():
    expected_parent = "rapp-work/1" if profile["name"] == "rapp-work-sdk/1" else "rapp/1"
    require(profile["parent"] == expected_parent, f"{profile['name']} parent mismatch")
    require(sha(ROOT / profile["spec_path"]) == profile["spec_sha256"],
            f"{profile['name']} SPEC hash mismatch")
    require(sha(ROOT / profile["schema_path"]) == profile["schema_sha256"],
            f"{profile['name']} schema hash mismatch")

protocol_entries = {
    entry["name"]: entry
    for entry in registry["entries"]
    if entry.get("type") == "protocol" and entry.get("deprecated") is False
}
expected_protocols = {
    "rapp/1": pin["spec_sha256"],
    "rapp-work/1": sha(ROOT / "SPEC.md"),
    **{
        name: profile["spec_sha256"]
        for name, profile in profiles.items()
        if name != "rapp-work-sdk/1"
    },
}
require({name: entry["spec_hash"] for name, entry in protocol_entries.items()} == expected_protocols,
        "signed registry protocol pins do not match checked-in bytes")
require(
    protocol_entries["rapp/1"]["spec_repo"] == pin["repository"]
    and protocol_entries["rapp/1"]["spec_path"] == pin["spec_path"],
    "historical estate RAPP/1 locator differs from the canonical parent pin",
)
require(
    protocol_entries["rapp-work/1"]["spec_repo"] == "https://github.com/kody-w/rapp-work"
    and protocol_entries["rapp-work/1"]["spec_path"] == "SPEC.md"
    and protocol_entries["rapp-work/1"]["spec_hash"] != work_pin["spec_sha256"],
    "historical signed RAPP Work pin was confused with the SDK parent pin",
)
require(
    profiles["rapp-work-sdk/1"]["activation"] == "workspace-integration-not-estate-authority",
    "SDK integration profile must not claim frozen estate activation",
)
profile_registry = ProfileRegistry.default()
profile_registry.verify()
canonical_work = profile_registry.get("rapp-work/1")
require(
    canonical_work.authority == "accepted-canonical-protocol"
    and canonical_work.activation == "sdk-parent-pin-not-estate-activation"
    and canonical_work.spec_sha256 == work_pin["spec_sha256"]
    and canonical_work.schema_sha256 == work_pin["schema_sha256"],
    "SDK profile registry does not use the canonical RAPP Work parent pin",
)
estate_verification = verify_source_estate(ROOT)
require(
    estate_verification["rapp1_parent_pin"] == pin
    and estate_verification["sdk_parent_pin"] == work_pin
    and estate_verification["historical_signed_estate_pin"]["spec_sha256"]
    == sha(ROOT / "SPEC.md"),
    "source-estate verification did not preserve both SDK pins and historical evidence",
)
metadata = api_metadata()
require(
    metadata["distribution"] == "rapp-work"
    and metadata["import"] == "rapp_work"
    and metadata["command"] == "rapp-work"
    and [item["name"] for item in metadata["operations"]]
    == ["status", "verify", "discover", "scaffold", "update", "migrate"],
    "static SDK API metadata mismatch",
)

commands = [
    [sys.executable, "protocols/rapp-hive/1/reference/hive_conformance.py"],
    [sys.executable, "protocols/rapp-federation/1/reference/schema_source.py", "--check"],
    [sys.executable, "protocols/rapp-federation/1/reference/conformance.py"],
]
for command in commands:
    subprocess.run(command, cwd=ROOT, check=True)

test_environment = dict(os.environ)
test_environment["PYTHONPATH"] = str(ROOT / "src") + (
    os.pathsep + test_environment["PYTHONPATH"]
    if test_environment.get("PYTHONPATH")
    else ""
)
subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    cwd=ROOT,
    env=test_environment,
    check=True,
)
for skill in ("rapp-work", "rapp-workspace-manager", "rapp-workspace", "rapp-private-hive"):
    require((ROOT / ".github" / "skills" / skill / "SKILL.md").is_file(),
            f"missing project skill: {skill}")

print("RAPP Work: signed registry and all profile conformance checks PASS")
