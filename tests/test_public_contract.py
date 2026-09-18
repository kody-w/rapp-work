from __future__ import annotations

from pathlib import Path

import rapp_work
from rapp_work import execute
from rapp_work.discovery import api_metadata

ROOT = Path(__file__).resolve().parents[1]


def test_exact_top_level_public_api() -> None:
    assert rapp_work.__all__ == [
        "COMMAND_NAME",
        "DIST_NAME",
        "FRAME_KEYS",
        "IMPORT_NAME",
        "MAX_RELEASE_OBSERVATIONS",
        "PROTOCOL_ID",
        "PUBLIC_OPERATIONS",
        "SDK_VERSION",
        "WORKSPACE_PROFILE_ID",
        "FileAction",
        "FilesystemTransport",
        "HiveHighWater",
        "HiveStreamPosition",
        "HiveVector",
        "MigrationPlan",
        "MigrationReceipt",
        "Organization",
        "PortableNeuron",
        "PrivateGitTransport",
        "ProfileDescriptor",
        "ProfileRegistry",
        "RappFrame",
        "ReleaseObservation",
        "ReleaseObservationStore",
        "ReleasePlan",
        "SignedRelease",
        "Workspace",
        "__version__",
        "build_frame",
        "discover",
        "execute",
        "migrate",
        "pinned_parent",
        "scaffold",
        "status",
        "update",
        "validate_chain",
        "validate_frame",
        "verify",
        "verify_hive_high_water",
    ]


def test_static_contract_names_and_operations() -> None:
    metadata = api_metadata()
    assert metadata["distribution"] == "rapp-work"
    assert metadata["import"] == "rapp_work"
    assert metadata["command"] == "rapp-work"
    assert metadata["module_command"] == "python -m rapp_work"
    assert metadata["protocol"] == "rapp-work/1"
    assert metadata["workspace_profile"] == "rapp-work-sdk/1"
    assert [value["name"] for value in metadata["operations"]] == [
        "status",
        "verify",
        "discover",
        "scaffold",
        "update",
        "migrate",
    ]


def test_unknown_operation_is_stable_refusal() -> None:
    result = execute("publish", {})
    assert result["status"] == "refused"
    assert result["refusal"]["code"] == "REFUSE_OPERATION"
    assert result["refusal"]["details"]["allowed"] == list(rapp_work.PUBLIC_OPERATIONS)


def test_legacy_implementations_are_not_duplicated_under_src() -> None:
    compat = ROOT / "src/rapp_work/compat"
    assert not (compat / "private_hive").exists()
    assert not (compat / "workspace_manager.py").exists()
    assert (ROOT / ".github/skills/rapp-private-hive/lib/private_hive").is_dir()
    assert (ROOT / ".github/skills/rapp-workspace-manager/scripts/manage.py").is_file()
