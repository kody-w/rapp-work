#!/usr/bin/env python3
"""Verify the RAPP Work standards estate and execute profile conformance."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "rapp-1"
sys.path.insert(0, str(VENDOR))

import rapp as R  # noqa: E402
import rapp_registry as REG  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


pin = json.loads((ROOT / "RAPP1_PIN.json").read_text(encoding="utf-8"))
require(pin["schema"] == "rapp-work-parent-pin/1", "wrong RAPP/1 pin schema")
require(sha(VENDOR / "SPEC.md") == pin["spec_sha256"], "vendored RAPP/1 SPEC hash mismatch")
require(sha(VENDOR / "rapp.py") == pin["reference_sha256"], "vendored rapp.py hash mismatch")

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
require(set(profiles) == {"rapp-hive/1", "rapp-federation/1"}, "unexpected profile index")
for profile in profiles.values():
    require(profile["parent"] == "rapp/1", f"{profile['name']} parent mismatch")
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
    **{name: profile["spec_sha256"] for name, profile in profiles.items()},
}
require({name: entry["spec_hash"] for name, entry in protocol_entries.items()} == expected_protocols,
        "signed registry protocol pins do not match checked-in bytes")

commands = [
    [sys.executable, "protocols/rapp-hive/1/reference/hive_conformance.py"],
    [sys.executable, "protocols/rapp-federation/1/reference/schema_source.py", "--check"],
    [sys.executable, "protocols/rapp-federation/1/reference/conformance.py",
     "--report", "conformance-results.json"],
]
for command in commands:
    subprocess.run(command, cwd=ROOT, check=True)

subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
    cwd=ROOT,
    check=True,
)
for skill in ("rapp-work", "rapp-workspace-manager", "rapp-workspace", "rapp-private-hive"):
    require((ROOT / ".github" / "skills" / skill / "SKILL.md").is_file(),
            f"missing project skill: {skill}")

print("RAPP Work: signed registry and all profile conformance checks PASS")
