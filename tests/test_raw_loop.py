"""The hand-written loop's control flow, with a scripted fake in place of the API."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from assistant.tools import default_registry

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample"


@pytest.fixture(scope="module")
def lab():
    spec = importlib.util.spec_from_file_location("raw_loop", ROOT / "labs" / "raw_loop.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["raw_loop"] = mod
    spec.loader.exec_module(mod)
    return mod


def text(t):
    return NS(type="text", text=t)


def tool_use(name, args, id="tu1"):
    return NS(type="tool_use", id=id, name=name, input=args)


def scripted(*responses):
    """A fake messages.create that returns the given responses in order and records requests."""
    calls = []
    queue = list(responses)

    def create(**kwargs):
        calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return queue.pop(0)

    create.calls = calls
    return create


def resp(stop_reason, *content):
    return NS(stop_reason=stop_reason, content=list(content))


def test_tool_then_answer(lab):
    create = scripted(
        resp(
            "tool_use",
            text("Let me look."),
            tool_use("get_expenses", {"month": "2026-10", "category": "dining"}),
        ),
        resp("end_turn", text("You spent $185.35.")),
    )
    r = lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    assert r.completed and r.text == "You spent $185.35." and r.iterations == 2
    assert r.tool_calls == [("get_expenses", {"month": "2026-10", "category": "dining"})]
    # the second request carries history: user, assistant (unchanged), user(tool_result)
    second = create.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][1].type == "tool_use"  # assistant turn kept as returned
    tr = second[2]["content"][0]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "tu1" and tr["is_error"] is False
    assert '"total": 185.35' in tr["content"]


def test_parallel_tool_calls_return_all_results_in_one_message(lab):
    create = scripted(
        resp(
            "tool_use",
            tool_use("get_expenses", {"month": "2026-10"}, id="a"),
            tool_use(
                "get_calendar_events",
                {"start_date": "2026-11-17", "end_date": "2026-11-17"},
                id="b",
            ),
        ),
        resp("end_turn", text("done")),
    )
    r = lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    results = create.calls[1]["messages"][-1]["content"]
    assert [x["tool_use_id"] for x in results] == ["a", "b"]  # one message, both results
    assert r.completed


def test_text_alongside_tool_use_does_not_end_the_loop(lab):
    # The anti-pattern: "the assistant said something, so it must be finished".
    create = scripted(
        resp("tool_use", text("Final answer: 42"), tool_use("get_expenses", {"month": "2026-10"})),
        resp("end_turn", text("real answer")),
    )
    r = lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    assert r.text == "real answer" and r.iterations == 2


def test_tool_error_is_sent_back_flagged_and_loop_continues(lab):
    create = scripted(
        resp("tool_use", tool_use("get_expenses", {"month": "October"})),
        resp("end_turn", text("sorry, fixed it")),
    )
    r = lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    tr = create.calls[1]["messages"][-1]["content"][0]
    assert tr["is_error"] is True and '"validation"' in tr["content"]
    assert r.completed


def test_unknown_tool_is_an_error_result_not_a_crash(lab):
    create = scripted(
        resp("tool_use", tool_use("delete_everything", {})), resp("end_turn", text("ok"))
    )
    lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    tr = create.calls[1]["messages"][-1]["content"][0]
    assert tr["is_error"] is True and "Unknown tool" in tr["content"]


@pytest.mark.parametrize("reason", ["max_tokens", "refusal", "pause_turn"])
def test_non_end_turn_stops_are_reported_not_answered(lab, reason):
    create = scripted(resp(reason, text("partial or declined text")))
    r = lab.run_raw_loop("q", default_registry(DATA), create, system="s")
    assert r.stop_reason == reason and not r.completed and r.text == ""


def test_iteration_cap_is_a_reported_failure(lab):
    forever = [
        resp("tool_use", tool_use("get_expenses", {"month": "2026-10"}, id=f"t{i}"))
        for i in range(5)
    ]
    r = lab.run_raw_loop(
        "q", default_registry(DATA), scripted(*forever), system="s", max_iterations=3
    )
    assert r.stop_reason == "max_iterations" and not r.completed and r.iterations == 3
