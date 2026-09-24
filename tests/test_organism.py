from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
ORGANISM = ROOT / "organism"


def builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("organism_build", ORGANISM / "tools" / "build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_generated_view_matches_the_organism_tree() -> None:
    build = builder()
    outputs = build.build(build.load(ORGANISM), ORGANISM)
    assert ROOT / "ECOSYSTEM.md" in outputs, "ECOSYSTEM.md must stay generated from organism/"
    assert build.check(ORGANISM) == 0


def test_a_crossing_with_an_unknown_end_is_refused(sandbox: Path) -> None:
    build = builder()
    tree = sandbox / "organism"
    shutil.copytree(ORGANISM, tree, ignore=shutil.ignore_patterns("__pycache__", "*.pdf"))
    crossing = tree / "crossings" / "hive-organization.md"
    text = crossing.read_text(encoding="utf-8")
    crossing.write_text(text.replace("to: organization", "to: nowhere"), encoding="utf-8")
    with pytest.raises(build.Refused, match="names `nowhere`"):
        build.load(tree)
