"""Deterministic guardrails: registration policy, tool contract, and lockdown config."""

import pytest

from assistant.core.registry import ToolRegistry
from assistant.core.tooling import ErrorCategory, RiskLevel, ToolSpec, err, ok
from assistant.policies.lockdown import BUILTIN_TOOLS, lockdown_options, mcp_tool_name
from assistant.policies.registration import PolicyViolation

GOOD_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
LONG_DESC = "A sufficiently long description that explains what the tool does and when to use it."


def make(name="do_thing", risk=RiskLevel.READ_ONLY, desc=LONG_DESC, schema=GOOD_SCHEMA):
    return ToolSpec(name, desc, schema, risk, lambda a: ok({}))


def test_phase1_registry_accepts_read_only():
    reg = ToolRegistry()
    reg.register(make())
    assert reg.names() == ["do_thing"]


@pytest.mark.parametrize("risk", [RiskLevel.REVERSIBLE, RiskLevel.IRREVERSIBLE])
def test_phase1_registry_refuses_side_effecting_tools(risk):
    with pytest.raises(PolicyViolation, match="approval gate"):
        ToolRegistry().register(make(risk=risk))


def test_registry_refuses_duplicates():
    reg = ToolRegistry()
    reg.register(make())
    with pytest.raises(PolicyViolation, match="duplicate"):
        reg.register(make())


def test_toolspec_rejects_weak_definitions():
    with pytest.raises(ValueError, match="description too short"):
        make(desc="Gets stuff.")
    with pytest.raises(ValueError, match="additionalProperties"):
        make(schema={"type": "object", "properties": {}})
    with pytest.raises(ValueError, match="snake_case"):
        make(name="Do-Thing")


def test_error_envelope_retryable_defaults():
    assert err(ErrorCategory.TRANSIENT, "x")["error"]["retryable"] is True
    for cat in (ErrorCategory.VALIDATION, ErrorCategory.PERMISSION, ErrorCategory.BUSINESS):
        assert err(cat, "x")["error"]["retryable"] is False
    assert err(ErrorCategory.BUSINESS, "x", retryable=True)["error"]["retryable"] is True


def test_lockdown_exposes_only_our_tools():
    opts = lockdown_options("assistant", ["get_expenses", "get_calendar_events"])
    assert opts["tools"] == []  # no built-in tools offered at all
    assert opts["allowed_tools"] == [
        mcp_tool_name("assistant", "get_expenses"),
        mcp_tool_name("assistant", "get_calendar_events"),
    ]
    assert all(t.startswith("mcp__assistant__") for t in opts["allowed_tools"])
    assert opts["permission_mode"] == "dontAsk"  # unlisted => denied, never prompted
    assert opts["setting_sources"] == []  # ignore this machine's Claude Code settings/hooks
    assert opts["strict_mcp_config"] is True
    for dangerous in ("Bash", "Write", "Edit", "WebFetch", "Read"):
        assert dangerous in opts["disallowed_tools"]
    assert set(opts["disallowed_tools"]) == set(BUILTIN_TOOLS)
    assert not set(opts["allowed_tools"]) & set(opts["disallowed_tools"])
