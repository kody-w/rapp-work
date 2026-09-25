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
    assert ORGANISM / "views" / "lock-in.html" in outputs
    assert build.check(ORGANISM) == 0


def test_every_gap_holds_back_exactly_one_layer() -> None:
    build = builder()
    tree = build.load(ORGANISM)
    held = [item for _, items in build.locks(tree).values() for item in items if item.startswith("G")]
    assert sorted(held) == sorted(gap["id"] for gap in tree["gap"])
    assert build.locks(tree)[0] == ("in RAPP/1", [])
    assert build.locks(tree)[6] == ("nothing to graduate", [])


def test_rapp1_holds_only_what_is_in_force() -> None:
    build = builder()
    tree = build.load(ORGANISM)
    for box in build.boxes(tree):
        assert (build.channel(box) == "RAPP/1") == (build.status(box["health"]) == "in force"), box["where"]
        assert build.channel(box) != "RAPP/1" or "experimental" not in box["health"], box["where"]
    lanes = {box["name"]: build.channel(box) for box in build.boxes(tree)}
    assert lanes["Brainstem app"] == "newest" and lanes["Workspaces"] == "RAPP/1"
    assert lanes["Outside knowledge"] == "outside" and lanes["You"] is None


@pytest.mark.parametrize(
    ("name", "old", "new", "why"),
    [
        ("crossings/folder-hive-organization.md", "to: organization", "to: nowhere", "names `nowhere`"),
        ("crossings/estate-organization.md", "arrow: up", "arrow: down", "points against"),
        ("gaps/G18.md", "phase: 1", "phase: 6", "`phase` is 1 to 5"),
        ("gaps/G18.md", "who: you", "who: nobody", "`who` is one of"),
        ("gaps/G18.md", "blocks: brainstem", "blocks: nowhere", "`blocks` names"),
        ("lock.md", '  - "1: accept or refuse RAPP proposal 0002 (G19), Tier 2 loading: a draft on '
         '`experimental/proposal-0002-tier2-parity`"\n', "", "no phase 1 step in lock.md names G19"),
        ("lock.md", "Public copy, the Brainstem app", "the Brainstem app", "Public copy is not in RAPP/1 yet"),
        ("parts/workspaces.md", "health: in force", "health: in force; its migration is experimental",
         "where nothing is experimental"),
        ("clean-pull.md", '"RAR: 50"', '"RAR: fifty"', "each `mentions` item reads"),
        ("clean-pull.md", "phase: 2", "phase: 3", "no phase 3 step in lock.md says"),
        ("clean-pull.md", '"planned: the installer', '"maybe: the installer', "each `door` item reads"),
        ("lock.md", '"1: merge RAPP proposal 0001', '"2: merge RAPP proposal 0001', "names G18, which is no phase 2 gap"),
    ],
)
def test_a_broken_tree_is_refused(sandbox: Path, name: str, old: str, new: str, why: str) -> None:
    build = builder()
    tree = sandbox / "organism"
    shutil.copytree(ORGANISM, tree, ignore=shutil.ignore_patterns("__pycache__", "*.pdf"))
    part = tree / name
    text = part.read_text(encoding="utf-8")
    assert old in text, f"{name} no longer holds {old!r}; update this test"
    part.write_text(text.replace(old, new), encoding="utf-8")
    with pytest.raises(build.Refused, match=why):
        build.load(tree)
