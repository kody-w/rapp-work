from __future__ import annotations

import json
from pathlib import Path

import pytest

from rapp_work import PortableNeuron, discover
from rapp_work.errors import Refusal


def test_discovery_is_inert_for_skills_plugins_and_neurons(sandbox: Path) -> None:
    sentinel = sandbox / "executed"
    skill = sandbox / ".github/skills/example/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: example-skill\n---\nNever execute.\n", encoding="utf-8")
    plugin_dir = sandbox / "plugin"
    plugin_dir.mkdir()
    entrypoint = plugin_dir / "plugin.py"
    entrypoint.write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n")
    (plugin_dir / "rapp-work-plugin.json").write_text(
        json.dumps(
            {
                "capabilities": ["example"],
                "entrypoint": "plugin.py",
                "name": "example-plugin",
                "schema": "rapp-work-plugin/1",
                "version": "1.0.0",
            }
        )
    )
    neuron = sandbox / "neurons/example/agent.py"
    neuron.parent.mkdir(parents=True)
    neuron.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n"
        "metadata = {'name': 'Example neuron', 'parameters': {}}\n",
        encoding="utf-8",
    )
    result = discover({"roots": [str(sandbox)]})
    assert result["status"] == "ok"
    payload = result["result"]
    assert [value["name"] for value in payload["skills"]] == ["example-skill"]
    assert [value["name"] for value in payload["plugins"]] == ["example-plugin"]
    assert payload["neurons"][0]["declared_name"] == "Example neuron"
    assert all(value["executed"] is False for group in ("skills", "plugins", "neurons") for value in payload[group])
    assert not sentinel.exists()


def test_malformed_plugin_is_reported_not_executed(sandbox: Path) -> None:
    plugin = sandbox / "rapp-work-plugin.json"
    plugin.write_text('{"schema":"rapp-work-plugin/1","unknown":true}', encoding="utf-8")
    result = discover({"roots": [str(sandbox)]})
    assert result["status"] == "ok"
    assert result["result"]["plugins"] == []
    assert result["result"]["refusals"][0]["code"] == "REFUSE_INPUT_KEYS"


def test_discovery_refuses_bounds_and_ignores_symlink(sandbox: Path) -> None:
    target = sandbox / "target"
    target.write_text("data")
    (sandbox / "link").symlink_to(target)
    result = discover({"roots": [str(sandbox)], "max_entries": 10})
    assert any(value["code"] == "REFUSE_SYMLINK" for value in result["result"]["refusals"])
    refused = discover({"roots": [str(sandbox)], "max_entries": 0})
    assert refused["status"] == "refused"
    assert refused["refusal"]["code"] == "REFUSE_DISCOVERY_LIMIT"


def test_portable_neuron_copy_requires_explicit_hash(sandbox: Path) -> None:
    path = sandbox / "agent.py"
    path.write_text("metadata = {'name': 'Inert'}\n", encoding="utf-8")
    neuron = PortableNeuron.inspect(path)
    destination = sandbox / "copy.py"
    with pytest.raises(Refusal, match="REFUSE_APPLY_REQUIRED"):
        neuron.copy_as_data(destination, apply=False, expected_sha256=neuron.sha256)
    with pytest.raises(Refusal, match="REFUSE_PLAN_HASH"):
        neuron.copy_as_data(destination, apply=True, expected_sha256="0" * 64)
    assert neuron.copy_as_data(
        destination,
        apply=True,
        expected_sha256=neuron.sha256,
    )["executed"] is False
    assert destination.read_bytes() == path.read_bytes()
