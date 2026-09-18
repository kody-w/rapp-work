from __future__ import annotations

import base64
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._json import closed_object, strict_json_loads
from ._paths import absolute_path, read_regular, safe_relative
from ._resources import data_file, protocols_root, vendor_root
from .errors import require
from .rapp1 import hash_bytes, rappid_parts, rappid_valid, verify_detached_jws

RAPP_REPOSITORY = "https://github.com/kody-w/rapp-1"
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


def _is_lower_hex(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _load_rapp1_pin(path: Path) -> dict[str, Any]:
    pin = closed_object(
        strict_json_loads(read_regular(path), where="RAPP/1 pin"),
        required=RAPP1_PIN_KEYS,
        where="RAPP/1 pin",
    )
    require(
        pin["schema"] == "rapp-work-parent-pin/1"
        and pin["protocol"] == "rapp/1"
        and pin["repository"] == RAPP_REPOSITORY
        and _is_lower_hex(pin["commit"], 40)
        and pin["spec_path"] == "SPEC.md"
        and _is_lower_hex(pin["spec_sha256"], 64)
        and pin["reference_path"] == "rapp.py"
        and _is_lower_hex(pin["reference_sha256"], 64),
        "REFUSE_PARENT_PIN",
        "RAPP/1 pin contract mismatch",
    )
    return pin


def _load_rapp_work_pin(path: Path) -> dict[str, Any]:
    pin = closed_object(
        strict_json_loads(read_regular(path), where="RAPP Work SDK parent pin"),
        required=RAPP_WORK_PIN_KEYS,
        where="RAPP Work SDK parent pin",
    )
    require(
        pin["schema"] == "rapp-work-sdk-parent-pin/1"
        and pin["protocol"] == "rapp-work/1"
        and pin["repository"] == RAPP_REPOSITORY
        and _is_lower_hex(pin["commit"], 40)
        and pin["spec_path"] == "protocols/rapp-work/1/SPEC.md"
        and _is_lower_hex(pin["spec_sha256"], 64)
        and pin["schema_path"] == "protocols/rapp-work/1/schema.json"
        and _is_lower_hex(pin["schema_sha256"], 64),
        "REFUSE_WORK_PIN",
        "RAPP Work SDK parent pin contract mismatch",
    )
    return pin


@dataclass(frozen=True)
class ProfileDescriptor:
    id: str
    parent: str | None
    authority: str
    activation: str
    spec_path: str
    spec_sha256: str
    schema_path: str | None
    schema_sha256: str | None

    @classmethod
    def from_dict(cls, value: Any) -> ProfileDescriptor:
        item = closed_object(
            value,
            required={
                "activation",
                "authority",
                "id",
                "parent",
                "schema_path",
                "schema_sha256",
                "spec_path",
                "spec_sha256",
            },
            where="profile descriptor",
        )
        require(
            isinstance(item["id"], str)
            and isinstance(item["authority"], str)
            and isinstance(item["activation"], str)
            and isinstance(item["spec_path"], str)
            and isinstance(item["spec_sha256"], str),
            "REFUSE_PROFILE",
            "profile descriptor fields have the wrong type",
        )
        require(
            (item["schema_path"] is None and item["schema_sha256"] is None)
            or (
                isinstance(item["schema_path"], str)
                and isinstance(item["schema_sha256"], str)
            ),
            "REFUSE_PROFILE",
            "profile schema path/hash must both be present or absent",
        )
        return cls(**item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "activation": self.activation,
            "authority": self.authority,
            "id": self.id,
            "parent": self.parent,
            "schema_path": self.schema_path,
            "schema_sha256": self.schema_sha256,
            "spec_path": self.spec_path,
            "spec_sha256": self.spec_sha256,
        }


def _resource_path(value: str) -> Path:
    prefix, separator, relative = value.partition(":")
    require(bool(separator and relative), "REFUSE_PROFILE", "invalid profile resource path")
    relative = safe_relative(relative)
    if prefix == "vendor":
        return vendor_root() / relative
    if prefix == "protocols":
        return protocols_root() / relative
    if prefix == "data":
        return data_file(relative)
    raise ValueError(f"unknown profile resource prefix: {prefix}")


class ProfileRegistry:
    """Closed profile descriptors with exact byte commitments."""

    def __init__(self, profiles: Iterable[ProfileDescriptor] = ()) -> None:
        self._profiles: dict[str, ProfileDescriptor] = {}
        for profile in profiles:
            self.register(profile)

    @classmethod
    def default(cls) -> ProfileRegistry:
        value = strict_json_loads(read_regular(data_file("profiles.json")), where="profile registry")
        item = closed_object(
            value,
            required={"profiles", "schema"},
            where="profile registry",
        )
        require(
            item["schema"] == "rapp-work-profile-registry/1"
            and isinstance(item["profiles"], list),
            "REFUSE_PROFILE",
            "wrong profile registry schema",
        )
        return cls(ProfileDescriptor.from_dict(profile) for profile in item["profiles"])

    def register(self, profile: ProfileDescriptor) -> None:
        require(
            profile.id not in self._profiles,
            "REFUSE_PROFILE_DUPLICATE",
            "profile is already registered",
            profile=profile.id,
        )
        require(
            profile.parent is None or profile.parent in self._profiles,
            "REFUSE_PROFILE_PARENT",
            "profile parent must be registered first",
            profile=profile.id,
            parent=profile.parent,
        )
        self._profiles[profile.id] = profile

    def get(self, profile_id: str) -> ProfileDescriptor:
        require(
            profile_id in self._profiles,
            "REFUSE_PROFILE_UNKNOWN",
            "profile is not registered",
            profile=profile_id,
        )
        return self._profiles[profile_id]

    def ids(self) -> tuple[str, ...]:
        return tuple(self._profiles)

    def descriptors(self) -> tuple[ProfileDescriptor, ...]:
        return tuple(self._profiles.values())

    def verify(self) -> dict[str, Any]:
        parent_pin = _load_rapp1_pin(data_file("RAPP1_PIN.json"))
        work_pin = _load_rapp_work_pin(data_file("RAPP_WORK_PIN.json"))
        require(
            parent_pin["repository"] == work_pin["repository"]
            and parent_pin["commit"] == work_pin["commit"],
            "REFUSE_WORK_PIN",
            "RAPP/1 and RAPP Work SDK parent pins must name the same canonical revision",
        )
        parent = self._profiles.get("rapp/1")
        if parent is not None:
            require(
                parent.parent is None
                and parent.authority == "pinned-parent"
                and parent.activation == "required"
                and parent.spec_path == "vendor:SPEC.md"
                and parent.spec_sha256 == parent_pin["spec_sha256"]
                and parent.schema_path is None
                and parent.schema_sha256 is None,
                "REFUSE_PARENT_PIN",
                "RAPP/1 profile descriptor differs from its packaged pin",
            )
        work = self._profiles.get("rapp-work/1")
        if work is not None:
            require(
                work.parent == "rapp/1"
                and work.authority == "accepted-canonical-protocol"
                and work.activation == "sdk-parent-pin-not-estate-activation"
                and work.spec_path == "data:rapp-work-1-SPEC.md"
                and work.spec_sha256 == work_pin["spec_sha256"]
                and work.schema_path == "data:rapp-work-1-schema.json"
                and work.schema_sha256 == work_pin["schema_sha256"],
                "REFUSE_WORK_PIN",
                "RAPP Work profile descriptor differs from its SDK parent pin",
            )
        checked: list[dict[str, Any]] = []
        for profile in self._profiles.values():
            spec = read_regular(_resource_path(profile.spec_path))
            require(
                hashlib.sha256(spec).hexdigest() == profile.spec_sha256,
                "REFUSE_PROFILE_HASH",
                "profile specification hash mismatch",
                profile=profile.id,
            )
            schema_verified = False
            if profile.schema_path is not None:
                schema = read_regular(_resource_path(profile.schema_path))
                require(
                    hashlib.sha256(schema).hexdigest() == profile.schema_sha256,
                    "REFUSE_PROFILE_HASH",
                    "profile schema hash mismatch",
                    profile=profile.id,
                )
                schema_verified = True
            checked.append(
                {
                    "activation": profile.activation,
                    "authority": profile.authority,
                    "id": profile.id,
                    "schema_verified": schema_verified,
                    "spec_sha256": profile.spec_sha256,
                }
            )
        return {"profiles": checked, "status": "verified"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "profiles": [profile.to_dict() for profile in self._profiles.values()],
            "schema": "rapp-work-profile-registry/1",
        }


def verify_source_estate(root: Path) -> dict[str, Any]:
    root = absolute_path(root)
    parent_pin = _load_rapp1_pin(root / "RAPP1_PIN.json")
    work_pin = _load_rapp_work_pin(root / "RAPP_WORK_PIN.json")
    packaged_parent_pin = _load_rapp1_pin(root / "src/rapp_work/data/RAPP1_PIN.json")
    packaged_work_pin = _load_rapp_work_pin(
        root / "src/rapp_work/data/RAPP_WORK_PIN.json"
    )
    require(
        parent_pin == packaged_parent_pin
        and parent_pin["repository"] == work_pin["repository"]
        and parent_pin["commit"] == work_pin["commit"],
        "REFUSE_PARENT_PIN",
        "source and packaged RAPP/1 pins or canonical revisions differ",
    )
    require(
        work_pin == packaged_work_pin,
        "REFUSE_WORK_PIN",
        "source and packaged RAPP Work SDK parent pins differ",
    )
    require(
        hashlib.sha256(read_regular(root / "vendor/rapp-1/SPEC.md")).hexdigest()
        == parent_pin["spec_sha256"]
        and hashlib.sha256(read_regular(root / "vendor/rapp-1/rapp.py")).hexdigest()
        == parent_pin["reference_sha256"],
        "REFUSE_PARENT_PIN",
        "source estate RAPP/1 parent bytes differ from the pin",
    )
    require(
        hashlib.sha256(
            read_regular(root / "src/rapp_work/data/rapp-work-1-SPEC.md")
        ).hexdigest()
        == work_pin["spec_sha256"]
        and hashlib.sha256(
            read_regular(root / "src/rapp_work/data/rapp-work-1-schema.json")
        ).hexdigest()
        == work_pin["schema_sha256"],
        "REFUSE_WORK_PIN",
        "packaged canonical RAPP Work bytes differ from the SDK parent pin",
    )
    identity = strict_json_loads(read_regular(root / "rappid.json"), where="estate identity")
    anchor = strict_json_loads(read_regular(root / "owner-anchor.json"), where="estate anchor")
    registry = strict_json_loads(read_regular(root / "registry.json"), where="estate registry")
    require(
        identity.get("schema") == "rapp/1" and rappid_valid(identity.get("rappid")),
        "REFUSE_ESTATE_IDENTITY",
        "source estate identity is not RAPP/1 conformant",
    )
    require(
        anchor.get("schema") == "rapp-work-anchor/1"
        and anchor.get("owner_rappid") == identity["rappid"],
        "REFUSE_ESTATE_ANCHOR",
        "source estate anchor does not bind the repository identity",
    )
    try:
        spki = base64.b64decode(anchor["spki_der_b64"], validate=True)
    except (KeyError, ValueError, TypeError) as error:
        raise ValueError("source estate anchor SPKI is invalid") from error
    require(
        hashlib.sha256(spki).hexdigest() == anchor.get("spki_sha256")
        and rappid_parts(anchor["owner_rappid"])["hash"] == hash_bytes("rapp/1:rappid", spki),
        "REFUSE_ESTATE_ANCHOR",
        "source estate anchor key commitment mismatch",
    )
    unsigned = {key: value for key, value in registry.items() if key != "sig"}
    ok, reason = verify_detached_jws(
        unsigned,
        registry.get("sig"),
        spki,
        expected_kid=anchor["owner_rappid"],
    )
    require(
        ok,
        "REFUSE_ESTATE_REGISTRY",
        "source estate registry signature refused",
        reason=reason,
    )
    signed_protocol_entries = {
        entry["name"]: entry
        for entry in registry.get("entries", [])
        if isinstance(entry, dict)
        and entry.get("type") == "protocol"
        and entry.get("deprecated") is False
    }
    signed_protocols = {
        name: entry.get("spec_hash") for name, entry in signed_protocol_entries.items()
    }
    root_work_sha256 = hashlib.sha256(read_regular(root / "SPEC.md")).hexdigest()
    expected = {
        "rapp/1": parent_pin["spec_sha256"],
        "rapp-work/1": root_work_sha256,
        "rapp-hive/1": hashlib.sha256(
            read_regular(root / "protocols/rapp-hive/1/SPEC.md")
        ).hexdigest(),
        "rapp-federation/1": hashlib.sha256(
            read_regular(root / "protocols/rapp-federation/1/SPEC.md")
        ).hexdigest(),
    }
    require(
        signed_protocols == expected,
        "REFUSE_ESTATE_REGISTRY",
        "signed protocol pins do not match source bytes",
    )
    signed_parent = signed_protocol_entries["rapp/1"]
    signed_work = signed_protocol_entries["rapp-work/1"]
    require(
        signed_parent.get("spec_repo") == parent_pin["repository"]
        and signed_parent.get("spec_path") == parent_pin["spec_path"]
        and signed_parent.get("spec_hash") == parent_pin["spec_sha256"],
        "REFUSE_ESTATE_REGISTRY",
        "historical estate RAPP/1 entry differs from the canonical parent pin",
    )
    require(
        signed_work.get("spec_repo") == "https://github.com/kody-w/rapp-work"
        and signed_work.get("spec_path") == "SPEC.md"
        and signed_work.get("spec_hash") == root_work_sha256,
        "REFUSE_ESTATE_REGISTRY",
        "historical signed RAPP Work estate pin differs from root evidence",
    )
    index = strict_json_loads(
        read_regular(root / "protocols/index.json"),
        where="source profile index",
    )
    require(
        isinstance(index, dict) and isinstance(index.get("profiles"), list),
        "REFUSE_PROFILE",
        "source profile index has the wrong shape",
    )
    indexed = {
        profile.get("name"): profile
        for profile in index["profiles"]
        if isinstance(profile, dict)
    }
    require(
        set(indexed) == {"rapp-work-sdk/1", "rapp-hive/1", "rapp-federation/1"},
        "REFUSE_PROFILE",
        "source profile index has an unexpected profile set",
    )
    for name, profile in indexed.items():
        spec_path = profile.get("spec_path")
        schema_path = profile.get("schema_path")
        require(
            isinstance(spec_path, str)
            and isinstance(profile.get("spec_sha256"), str)
            and hashlib.sha256(read_regular(root / safe_relative(spec_path))).hexdigest()
            == profile["spec_sha256"]
            and isinstance(schema_path, str)
            and isinstance(profile.get("schema_sha256"), str)
            and hashlib.sha256(read_regular(root / safe_relative(schema_path))).hexdigest()
            == profile["schema_sha256"],
            "REFUSE_PROFILE_HASH",
            "source profile index commitment mismatch",
            profile=name,
        )
    require(
        indexed["rapp-work-sdk/1"].get("activation")
        == "workspace-integration-not-estate-authority",
        "REFUSE_PROFILE",
        "source SDK profile makes an invalid estate-authority claim",
    )
    return {
        "historical_signed_estate_pin": {
            "protocol": "rapp-work/1",
            "repository": signed_work["spec_repo"],
            "spec_path": signed_work["spec_path"],
            "spec_sha256": signed_work["spec_hash"],
        },
        "identity": identity["rappid"],
        "rapp1_parent_pin": parent_pin,
        "registry_seq": registry.get("registry_seq"),
        "sdk_parent_pin": work_pin,
        "signed_profiles": sorted(signed_protocols),
        "status": "verified",
    }
