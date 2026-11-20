"""Offline checks of the eval set itself: it loads, references real tools, is grounded in the
sample data, and the grader catches what it should. No API calls."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from assistant.core.report import RunReport, ToolCallRecord
from assistant.tools import default_registry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample"


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("run_evals", ROOT / "evals" / "run_evals.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_evals"] = mod  # dataclasses needs the module registered before exec
    spec.loader.exec_module(mod)
    return mod


def report(text="ok", tools=(), outcome="completed", offered=("mcp__assistant__get_expenses",)):
    return RunReport(
        outcome=outcome,
        final_text=text,
        tool_calls=[ToolCallRecord(t, {}) for t in tools],
        available_tools=list(offered) if offered is not None else None,
    )


def test_scenarios_load_and_reference_real_tools(ev):
    _today, scenarios = ev.load_scenarios()
    names = set(default_registry(DATA).names())
    assert len(scenarios) >= 6
    assert len({s.id for s in scenarios}) == len(scenarios)
    for s in scenarios:
        assert set(s.tools_all_of + s.tools_none_of) <= names, s.id
        assert not set(s.tools_all_of) & set(s.tools_none_of), s.id


def test_expected_facts_exist_in_sample_data():
    reg = default_registry(DATA)
    cal = reg.get("get_calendar_events").handler
    exp = reg.get("get_expenses").handler
    tue = json.dumps(cal({"start_date": "2026-11-17", "end_date": "2026-11-17"}))
    assert "Maria" in tue and "Book club" in tue
    nov18 = json.dumps(cal({"start_date": "2026-11-18", "end_date": "2026-11-18"}))
    assert "Quarterly planning" in nov18 and "Car service" in nov18
    assert exp({"month": "2026-10", "category": "dining"})["data"]["total"] == 185.35
    assert exp({"month": "2026-11", "category": "health"})["data"]["total"] == 220.0
    assert "Sky Airlines" in json.dumps(exp({"month": "2026-11", "category": "travel"}))


def test_grader_passes_a_good_run(ev):
    _t, scenarios = ev.load_scenarios()
    s = next(x for x in scenarios if x.id == "expenses-category-total")
    assert ev.grade(s, report("You spent $185.35 on dining.", ["get_expenses"])) == []


def test_grader_catches_each_failure_kind(ev):
    _t, scenarios = ev.load_scenarios()
    by_id = {s.id: s for s in scenarios}
    s = by_id["expenses-category-total"]
    assert any("not called" in f for f in ev.grade(s, report("185.35", [])))
    assert any(
        "forbidden" in f
        for f in ev.grade(s, report("185.35", ["get_expenses", "get_calendar_events"]))
    )
    assert any("missing" in f for f in ev.grade(s, report("about $190", ["get_expenses"])))
    assert any(
        "did not complete" in f
        for f in ev.grade(s, report("185.35", ["get_expenses"], outcome="max_turns"))
    )
    no_data = by_id["no-data-for-period"]
    assert any(
        "forbidden pattern" in f
        for f in ev.grade(no_data, report("You spent $250.", ["get_expenses"]))
    )
    assert ev.grade(no_data, report("No data for that period.", ["get_expenses"])) == []


def test_grader_enforces_lockdown_and_flags_unverified(ev):
    _t, scenarios = ev.load_scenarios()
    s = next(x for x in scenarios if x.id == "no-tool-needed")
    leaked = report("hi", offered=("mcp__assistant__get_expenses", "Bash"))
    assert any("lockdown broken" in f for f in ev.grade(s, leaked))
    unknown = report("hi", offered=None)
    assert any("lockdown unverified" in f for f in ev.grade(s, unknown))
