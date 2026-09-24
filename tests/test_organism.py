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


@pytest.mark.parametrize(
    ("name", "old", "new", "why"),
    [
        ("folder-hive-organization.md", "to: organization", "to: nowhere", "names `nowhere`"),
        ("estate-organization.md", "arrow: up", "arrow: down", "points against"),
    ],
)
def test_a_broken_crossing_is_refused(sandbox: Path, name: str, old: str, new: str, why: str) -> None:
    build = builder()
    tree = sandbox / "organism"
    shutil.copytree(ORGANISM, tree, ignore=shutil.ignore_patterns("__pycache__", "*.pdf"))
    crossing = tree / "crossings" / name
    crossing.write_text(crossing.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    with pytest.raises(build.Refused, match=why):
        build.load(tree)
