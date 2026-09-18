from __future__ import annotations

import hashlib
import json

import pytest

from tools.verify_package import verify_inventory_files


def package_files() -> dict[str, bytes]:
    payloads = {"README.md": b"# fixture\n"}
    inventory = {
        "distribution": "rapp-work",
        "files": [
            {
                "bytes": len(content),
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for path, content in sorted(payloads.items())
        ],
        "profile": "rapp-work-sdk/1",
        "protocol": "rapp-work/1",
        "schema": "rapp-work-release-inventory/1",
        "version": "1.0.0",
    }
    files = {
        **payloads,
        "RELEASE-INVENTORY.json": json.dumps(
            inventory,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        "PKG-INFO": (
            b"Metadata-Version: 2.4\n"
            b"Name: rapp-work\n"
            b"Version: 1.0.0\n"
            b"Requires-Python: >=3.10\n"
            b"Requires-Dist: cryptography<47,>=42\n\n"
        ),
        "setup.cfg": b"[egg_info]\ntag_build = \ntag_date = 0\n\n",
        "src/rapp_work.egg-info/dependency_links.txt": b"\n",
        "src/rapp_work.egg-info/entry_points.txt": (
            b"[console_scripts]\nrapp-work = rapp_work.cli:main\n"
        ),
        "src/rapp_work.egg-info/requires.txt": (
            b"cryptography<47,>=42\n\n"
            b"[dev]\n"
            b"build<2,>=1.2\n"
            b"jsonschema<5,>=4.21\n"
            b"mypy<2,>=1.15\n"
            b"pytest<10,>=8\n"
            b"ruff<1,>=0.11\n"
            b"wheel<1,>=0.45\n"
        ),
        "src/rapp_work.egg-info/top_level.txt": b"rapp_work\n",
    }
    files["src/rapp_work.egg-info/PKG-INFO"] = files["PKG-INFO"]
    source_names = set(payloads) | {
        "RELEASE-INVENTORY.json",
        "src/rapp_work.egg-info/PKG-INFO",
        "src/rapp_work.egg-info/SOURCES.txt",
        "src/rapp_work.egg-info/dependency_links.txt",
        "src/rapp_work.egg-info/entry_points.txt",
        "src/rapp_work.egg-info/requires.txt",
        "src/rapp_work.egg-info/top_level.txt",
    }
    files["src/rapp_work.egg-info/SOURCES.txt"] = (
        "\n".join(sorted(source_names)) + "\n"
    ).encode()
    return files


def test_sdist_inventory_refuses_omission() -> None:
    files = package_files()
    del files["README.md"]
    with pytest.raises(ValueError, match="missing inventoried"):
        verify_inventory_files(files)


def test_sdist_inventory_refuses_contamination() -> None:
    files = package_files()
    files["unexpected.txt"] = b"contamination"
    with pytest.raises(ValueError, match="non-inventoried"):
        verify_inventory_files(files)


def test_sdist_inventory_refuses_hash_mismatch() -> None:
    files = package_files()
    files["README.md"] = b"changed"
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_inventory_files(files)
