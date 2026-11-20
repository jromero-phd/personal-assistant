"""Runner stop conditions and report building, driven by fake SDK message streams (no API)."""

import asyncio
import json
from datetime import date
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from assistant.core.runner import AgentConfig, _wrap_tool, build_options, run_agent
from assistant.core.tooling import RiskLevel, ToolSpec
from assistant.tools import default_registry

DATA = Path(__file__).resolve().parents[1] / "data" / "sample"
CONFIG = AgentConfig(today=date(2026, 11, 14))


def result(
    subtype="success", *, is_error=False, turns=2, stop_reason="end_turn", text="done", **kw
):
    return ResultMessage(
        subtype=subtype,
        duration_ms=10,
        duration_api_ms=5,
        is_error=is_error,
        num_turns=turns,
        session_id="s1",
        stop_reason=stop_reason,
        total_cost_usd=0.01,
        result=text if subtype == "success" else None,
        **kw,
    )


def stream_of(*messages, then_raise=None):
    async def fake_query(*, prompt, options):
        for m in messages:
            yield m
        if then_raise:
            raise then_raise

    return fake_query


def run(*messages, then_raise=None):
    reg = default_registry(DATA)
    return asyncio.run(
        run_agent("q", reg, CONFIG, query_fn=stream_of(*messages, then_raise=then_raise))
    )


def tool_turn(name="mcp__assistant__get_expenses", args=None, tid="t1", is_error=False):
    return [
        AssistantMessage(
            content=[ToolUseBlock(id=tid, name=name, input=args or {"month": "2026-10"})], model="m"
        ),
        UserMessage(content=[ToolResultBlock(tool_use_id=tid, content="{}", is_error=is_error)]),
    ]


def test_completed_run_records_tools_text_cost():
    r = run(
        SystemMessage(subtype="init", data={"tools": ["mcp__assistant__get_expenses"]}),
        *tool_turn(),
        AssistantMessage(content=[TextBlock(text="You spent $185.35.")], model="m"),
        result(text="You spent $185.35."),
    )
    assert r.outcome == "completed" and r.completed
    assert r.final_text == "You spent $185.35."
    assert r.tool_names == ["get_expenses"]  # server prefix stripped
    assert r.tool_calls[0].input == {"month": "2026-10"} and r.tool_calls[0].is_error is False
    assert r.num_turns == 2 and r.cost_usd == 0.01
    assert r.available_tools == ["mcp__assistant__get_expenses"]


def test_tool_error_flag_is_recorded():
    r = run(*tool_turn(is_error=True), result())
    assert r.tool_calls[0].is_error is True


def test_max_turns_is_reported_not_success():
    # query() yields the error result and THEN raises; the report must keep the result.
    r = run(
        *tool_turn(),
        result("error_max_turns", is_error=True, stop_reason="tool_use"),
        then_raise=RuntimeError("Reached maximum number of turns"),
    )
    assert r.outcome == "max_turns" and not r.completed
    assert r.final_text == ""  # no answer was produced; the caller must not present one
    assert "max_turns" in r.error


def test_max_budget_is_reported():
    r = run(result("error_max_budget_usd", is_error=True), then_raise=RuntimeError("budget"))
    assert r.outcome == "max_budget"


def test_refusal_is_not_treated_as_an_answer():
    r = run(result(stop_reason="refusal", text="I can't help with that."))
    assert r.outcome == "refused" and not r.completed


def test_api_error_with_success_subtype_is_an_error():
    r = run(result("success", is_error=True, text="API Error: overloaded", api_error_status=529))
    assert r.outcome == "error" and "529" in r.error


def test_other_error_subtype_is_an_error():
    r = run(result("error_during_execution", is_error=True, errors=["boom"]))
    assert r.outcome == "error" and "boom" in r.error


def test_process_failure_with_no_result_is_reported_not_raised():
    r = run(then_raise=ConnectionError("cli died"))
    assert r.outcome == "error" and "ConnectionError" in r.error


def test_empty_stream_is_an_error():
    r = run()
    assert r.outcome == "error" and r.error


def test_report_is_json_serializable():
    r = run(*tool_turn(), result())
    json.dumps(r.to_dict())


def test_build_options_applies_lockdown_and_backstops():
    opts = build_options(default_registry(DATA), CONFIG)
    assert opts.model == "claude-sonnet-5-5"
    assert opts.tools == [] and opts.setting_sources == [] and opts.permission_mode == "dontAsk"
    assert opts.max_turns == 10 and opts.max_budget_usd == 0.25
    assert "Saturday, 2026-11-14" in opts.system_prompt  # injected "today", not the clock


def test_wrapped_handler_converts_envelope_and_flags_errors():
    spec = default_registry(DATA).get("get_expenses")
    sdk_tool = _wrap_tool(spec)
    good = asyncio.run(sdk_tool.handler({"month": "2026-10"}))
    assert good["is_error"] is False
    assert json.loads(good["content"][0]["text"])["ok"] is True
    bad = asyncio.run(sdk_tool.handler({"month": "nope"}))
    assert bad["is_error"] is True
    assert json.loads(bad["content"][0]["text"])["error"]["category"] == "validation"


def test_wrapped_handler_survives_a_crashing_tool():
    def boom(_args):
        raise KeyError("secret internal detail")

    spec = ToolSpec(
        "crashy_tool",
        "A tool that always crashes, used to test that handler bugs never kill the agent loop.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.READ_ONLY,
        boom,
    )
    out = asyncio.run(_wrap_tool(spec).handler({}))
    body = json.loads(out["content"][0]["text"])
    assert out["is_error"] is True and body["error"]["category"] == "internal"
    assert "secret internal detail" not in out["content"][0]["text"]  # no internals leaked
