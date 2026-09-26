from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from agent_trees import DEEP_CHAIN_SOURCE, DRAFT_SOURCE
from agent_trees import write as _write

import rapp_work.agent_files as agent_files
from rapp_work import discover
from rapp_work._python_source import (
    MAX_DECIMAL_DIGITS,
    MAX_FORMAT_FIELDS,
    MAX_SOURCE_COST,
    MAX_SOURCE_NESTING,
    measure_source,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"

# (verdict, cost, nesting) on every supported interpreter. On 3.10 and 3.11 the fields come
# from the port of CPython's f-string scanner; on 3.12 and later from the tokenizer itself.
FORMAT_SAMPLES: dict[str, tuple[str, tuple[str, int, int]]] = {
    "plain": ('x = f"a{b}c"\n', ("within", 8, 7)),
    "conversion_spec": ('x = f"a{x!r:>{w}}b{{c}}{y=}"\n', ("within", 18, 11)),
    "nested_spec": ('x = f"{x:{y}.{z}}"\n', ("within", 15, 12)),
    "multiline_field": ('x = f"""{\n a\n + b}"""\n', ("within", 12, 8)),
    "nested_literals": ("x = f'''{f\"{f'{a}'}\"}'''\n", ("within", 16, 13)),
    "raw_backslash": ('x = rf"\\d{a}\\{b}"\n', ("within", 11, 7)),
    "named_escape": ('x = f"\\N{LATIN SMALL LETTER A}{a}"\n', ("within", 8, 7)),
    "doubled": ('x = f"{{}}{a}{{{b}}}"\n', ("within", 11, 7)),
    "self_documenting": ('x = f"{a = !r:^9}"\n', ("within", 12, 10)),
    "dict_in_field": ("x = f\"{ {'k': [1, (2, 3)]}['k'] }\"\n", ("within", 23, 14)),
    "comparisons_in_field": ('x = f"{a!=b} {a<=b} {a>b} {a==b}"\n', ("within", 25, 8)),
    "lambda_in_field": ('x = f"{(lambda a, b: a + b)(1, 2)}"\n', ("within", 22, 13)),
    "concatenated": ('x = (f"{a}" "b" f"{c}"\n     f"{d:{e}}")\n', ("within", 26, 12)),
    "brace_in_field_string": ("x = f\"{d['}']}\"\n", ("within", 11, 9)),
    "triple_in_field_string": ("x = f\"{'''a}b'''}\"\n", ("within", 8, 7)),
    # A lone quote of the same kind does not end a triple-quoted string inside a field.
    "quote_in_triple_field_string": ("x = f\"{'''a'}b'''}\"\n", ("within", 8, 7)),
    "quote_in_triple_field_string_double": ('x = f\'{"""a"}b"""}\'\n', ("within", 8, 7)),
    # Adjacent literals nest as deeply as their deepest member, not as their sum.
    "adjacent_then_operator": ('x = f"{a}" f"{(b)}" + c\n', ("within", 17, 10)),
    "adjacent_nested_then_operator": ('x = f"{(a)}" "s" f"{[(b)]}" f"{c}" * d\n', ("within", 27, 12)),
    # Tokens inside a formatted literal cost one more unit per 4,096 characters of their line.
    "long_line": ("x = [" + 'f"{a}", ' * 700 + "]\n", ("within", 7705, 9)),
    "split_lines": ("x = [\n" + '    f"{a}",\n' * 700 + "]\n", ("within", 4906, 9)),
}

# The largest n within the nesting bound; n + 1 is over it.
NESTING_EDGES: dict[str, tuple[Any, int]] = {
    "chain": (lambda n: "x = 1" + "+1" * n + "\n", 252),
    "brackets": (lambda n: "x = " + "(" * n + "1" + ")" * n + "\n", 126),
    "elif_chain": (lambda n: "if a: pass\n" + "elif a: pass\n" * n, 252),
    "lambda_parameters": (lambda n: "x = " + "lambda a, b: " * n + "1\n", 84),
    "field_chain": (lambda n: "x = f'{1" + "+1" * n + "}'\n", 249),
    "not_chain": (lambda n: "x = " + "not " * n + "a\n", 252),
}

# Chains long enough to overflow an unguarded 3.10 parse on a 512 KiB stack, yet within the
# cost bound, so that only the nesting bound keeps them from the parser.
HOSTILE_SOURCES = {
    "binop": b"x = 1" + b"+1" * 60_000 + b"\n",
    "attribute": b"x = a" + b".b" * 60_000 + b"\n",
    "call": b"x = a" + b"()" * 60_000 + b"\n",
    "subscript": b"x = a" + b"[0]" * 40_000 + b"\n",
    "annotation": b"x: a" + b"|a" * 60_000 + b"\n",
    "matmul": b"x = a" + b"@a" * 60_000 + b"\n",
    "format_field": b"x = f'''{1" + b"\n+1" * 40_000 + b"}'''\n",
    "match_value": b"match x:\n    case a" + b".b" * 60_000 + b":\n        pass\n",
    "decorator": b"@a" + b".b" * 60_000 + b"\ndef f():\n    pass\n",
    "delete_target": b"del a" + b".b" * 60_000 + b"\n",
    "keywords": b"x = " + b"not " * 60_000 + b"a\n",
    "long_chain": DEEP_CHAIN_SOURCE,
    "decimal": b"x = " + b"9" * (MAX_DECIMAL_DIGITS + 1) + b"\n",
    "fields": b"x = f'" + b"{a}" * (MAX_FORMAT_FIELDS + 1) + b"'\n",
    "cost": b"a\n" * (MAX_SOURCE_COST // 2 + 1),
}
AT_BOUND_SOURCES = {
    "edge_brackets": b"x = " + b"(" * 126 + b"1" + b")" * 126 + b"\n",
    "edge_field_brackets": b"x = f'{" + b"(" * 124 + b"1" + b")" * 124 + b"}'\n",
    "edge_chain": b"x = 1" + b"+1" * 252 + b"\n",
    "edge_not": b"x = " + b"not " * 252 + b"a\n",
    "edge_lambda": b"x = " + b"lambda a, b: " * 84 + b"1\n",
    "edge_cost": b"a\n" * (MAX_SOURCE_COST // 2),
}
HARSH_HOST = r"""
import json, sys, threading
sys.setrecursionlimit(1_000_000)
from rapp_work import discover
found = {}
def run():
    envelope = discover(json.loads(sys.argv[1]))
    result = envelope["result"]
    found["agents"] = {r["path"].rsplit("/", 1)[-1]: r["syntax"] for r in result.get("agents", [])}
    found["refusals"] = {r["path"].rsplit("/", 1)[-1]: r["code"] for r in result["refusals"]}
    found["neurons"] = [r["path"].rsplit("/", 2)[-2] for r in result["neurons"]]
threading.stack_size(512 * 1024)
thread = threading.Thread(target=run)
thread.start()
thread.join()
print(json.dumps(found, sort_keys=True))
"""


def _harsh_discover(inputs: dict[str, Any]) -> dict[str, Any]:
    """Discover in a child with a 512 KiB thread stack and a recursion limit of 1,000,000."""

    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(SOURCE_ROOT), *filter(None, [environment.get("PYTHONPATH")])]
    )
    completed = subprocess.run(
        [sys.executable, "-c", HARSH_HOST, json.dumps(inputs)],
        capture_output=True,
        text=True,
        timeout=600,
        env=environment,
        check=False,
    )
    assert completed.returncode == 0, (completed.returncode, completed.stderr[-2000:])
    return dict(json.loads(completed.stdout))


def _syntax(envelope: dict[str, Any]) -> dict[str, str]:
    assert envelope["status"] == "ok", envelope
    return {
        Path(record["path"]).name.removesuffix("_agent.py"): record["syntax"]
        for record in envelope["result"]["agents"]
    }


@pytest.mark.parametrize("name", sorted(FORMAT_SAMPLES))
def test_measure_is_identical_on_every_supported_interpreter(name: str) -> None:
    source, expected = FORMAT_SAMPLES[name]
    assert tuple(measure_source(source, MAX_SOURCE_COST)) == expected


@pytest.mark.parametrize("name", sorted(NESTING_EDGES))
def test_nesting_bound_is_exact(name: str) -> None:
    build, largest = NESTING_EDGES[name]
    within = measure_source(build(largest), MAX_SOURCE_COST)
    assert (within.verdict, within.nesting) == ("within", MAX_SOURCE_NESTING)
    assert measure_source(build(largest + 1), MAX_SOURCE_COST).verdict == "over-limit"


def test_siblings_do_not_accumulate_nesting() -> None:
    flat = [
        "x = [" + ", ".join(["a.b + c"] * 5000) + "]\n",
        "x = {\n" + "".join(f"    'k{i}': (1, [2, {{3: 4}}]),\n" for i in range(3000)) + "}\n",
        'x = f"' + "{a.b}" * 1000 + '"\n',
        "x = (\n" + '    f"{a}" "b"\n' * 900 + ")\n",
        "if a:\n    pass\n" * 2000,
    ]
    for source in flat:
        measure = measure_source(source, MAX_SOURCE_COST)
        assert measure.verdict == "within" and measure.nesting < 16, measure


def test_indentation_follows_the_tokenizer_limit() -> None:
    def blocks(levels: int) -> str:
        return "".join(" " * i + "if a:\n" for i in range(levels)) + " " * levels + "pass\n"

    assert measure_source(blocks(99), MAX_SOURCE_COST).verdict == "within"
    assert measure_source(blocks(100), MAX_SOURCE_COST).verdict == "invalid"


def test_cost_bound_is_exact(sandbox: Path) -> None:
    lines = MAX_SOURCE_COST // 2
    assert tuple(measure_source("a\n" * lines, MAX_SOURCE_COST)) == ("within", MAX_SOURCE_COST, 3)
    over = measure_source("a\n" * (lines + 1), MAX_SOURCE_COST)
    assert (over.verdict, over.cost) == ("over-cost", MAX_SOURCE_COST + 1)
    _write(sandbox / "agents/at_agent.py", b"a\n" * lines)
    _write(sandbox / "agents/over_agent.py", b"a\n" * (lines + 1))
    assert _syntax(discover({"roots": [str(sandbox)], "agents": True})) == {
        "at": "parsed",
        "over": "over-limit",
    }


def test_decimal_literal_bound_does_not_follow_host_settings() -> None:
    within = [
        "x = " + "9" * MAX_DECIMAL_DIGITS + "\n",
        "x = " + "1_0" * (MAX_DECIMAL_DIGITS // 2) + "\n",
        "x = 0x" + "f" * 5000 + "\n",
        "x = 1." + "0" * 5000 + "\n",
        "x = " + "9" * 5000 + "j\n",
    ]
    over = [
        "x = " + "9" * (MAX_DECIMAL_DIGITS + 1) + "\n",
        "x = 1" + "_0" * MAX_DECIMAL_DIGITS + "\n",
    ]
    setter = getattr(sys, "set_int_max_str_digits", None)
    previous = sys.get_int_max_str_digits() if setter is not None else None
    settings = [0, 640, 100_000] if setter is not None else [None]
    try:
        for setting in settings:
            if setter is not None:
                setter(setting)
            assert [measure_source(s, MAX_SOURCE_COST).verdict for s in within] == ["within"] * 5
            assert [measure_source(s, MAX_SOURCE_COST).verdict for s in over] == ["over-limit"] * 2
    finally:
        if setter is not None:
            setter(previous)


def test_replacement_fields_are_bounded_per_run_of_adjacent_literals() -> None:
    def one_literal(fields: int) -> str:
        return 'x = f"' + "{a}" * fields + '"\n'

    def one_run(fields: int) -> str:
        return "x = (\n" + '    f"{a}"\n' * fields + ")\n"

    def separate_runs(fields: int) -> str:
        return "x = [\n" + '    f"{a}",\n' * fields + "]\n"

    def spec_fields(fields: int) -> str:
        return 'x = f"' + "{a:{b}}" * (fields // 2) + '"\n'

    for build in (one_literal, one_run, spec_fields):
        assert measure_source(build(MAX_FORMAT_FIELDS), MAX_SOURCE_COST).verdict == "within"
        verdict = measure_source(build(MAX_FORMAT_FIELDS + 2), MAX_SOURCE_COST).verdict
        assert verdict == "over-limit"
    assert measure_source(separate_runs(4 * MAX_FORMAT_FIELDS), MAX_SOURCE_COST).verdict == "within"


def test_hostile_sources_never_reach_the_parser_even_on_a_harsh_host(sandbox: Path) -> None:
    for name, data in {**HOSTILE_SOURCES, **AT_BOUND_SOURCES}.items():
        _write(sandbox / f"agents/{name}_agent.py", data)
    _write(sandbox / "neurons/deep/agent.py", DEEP_CHAIN_SOURCE)
    _write(sandbox / "neurons/edge/agent.py", AT_BOUND_SOURCES["edge_field_brackets"])
    found = _harsh_discover({"roots": [str(sandbox)], "agents": True})
    syntax = {name.removesuffix("_agent.py"): value for name, value in found["agents"].items()}
    assert syntax == {
        **dict.fromkeys(HOSTILE_SOURCES, "over-limit"),
        **dict.fromkeys(AT_BOUND_SOURCES, "parsed"),
    }
    assert found["refusals"] == {"agent.py": "REFUSE_DISCOVERY_METADATA"}
    assert found["neurons"] == ["edge"]


def test_default_discover_guards_portable_neuron_parsing(sandbox: Path) -> None:
    _write(sandbox / "neurons/deep/agent.py", DEEP_CHAIN_SOURCE)
    _write(
        sandbox / "neurons/latin/agent.py",
        b"# -*- coding: latin-1 -*-\nmetadata = {'name': 'caf\xe9'}\n",
    )
    _write(sandbox / "agents/deep_agent.py", DEEP_CHAIN_SOURCE)
    found = _harsh_discover({"roots": [str(sandbox)]})
    assert found == {
        "agents": {},
        "neurons": ["latin"],
        "refusals": {"agent.py": "REFUSE_DISCOVERY_METADATA"},
    }
    envelope = discover({"roots": [str(sandbox)]})
    (neuron,) = envelope["result"]["neurons"]
    assert neuron["declared_name"] == "caf\xe9"


def test_call_budget_is_spent_in_order_and_charged_for_every_measure(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = measure_source(DRAFT_SOURCE.decode(), MAX_SOURCE_COST).cost
    deep = measure_source(DEEP_CHAIN_SOURCE.decode(), MAX_SOURCE_COST)
    assert deep.verdict == "over-limit" and deep.cost > unit
    monkeypatch.setattr(agent_files, "MAX_CALL_PARSE_COST", deep.cost + 2 * unit + unit // 2)
    first = sandbox / "first"
    second = sandbox / "second"
    _write(first / "agents/0deep_agent.py", DEEP_CHAIN_SOURCE)
    for name in ("a", "b"):
        _write(first / f"agents/{name}_agent.py", DRAFT_SOURCE)
    for name in ("c", "d"):
        _write(second / f"agents/{name}_agent.py", DRAFT_SOURCE)
    expected = {
        "0deep": "over-limit",
        "a": "parsed",
        "b": "parsed",
        "c": "over-budget",
        "d": "over-budget",
    }
    forward = discover({"roots": [str(first), str(second)], "agents": True})
    backward = discover({"roots": [str(second), str(first)], "agents": True})
    assert _syntax(forward) == _syntax(backward) == expected
    alone = discover({"roots": [str(second)], "agents": True})
    assert _syntax(alone) == {"c": "parsed", "d": "parsed"}


def test_a_nul_source_is_invalid_before_any_budget_check(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = measure_source(DRAFT_SOURCE.decode(), MAX_SOURCE_COST).cost
    monkeypatch.setattr(agent_files, "MAX_CALL_PARSE_COST", unit)
    _write(sandbox / "agents/a_agent.py", DRAFT_SOURCE)
    _write(sandbox / "agents/b_agent.py", b"x = 1\x00\n")
    _write(sandbox / "agents/c_agent.py", DRAFT_SOURCE)
    found = discover({"roots": [str(sandbox)], "agents": True})
    assert _syntax(found) == {"a": "parsed", "b": "invalid", "c": "over-budget"}


def test_call_budget_is_sixty_four_largest_files() -> None:
    assert agent_files.MAX_CALL_PARSE_COST == 64 * MAX_SOURCE_COST
    assert agent_files.ParseBudget().remaining == agent_files.MAX_CALL_PARSE_COST
