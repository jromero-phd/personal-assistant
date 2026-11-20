"""The agent run: wraps the Claude Agent SDK's loop and turns its stream into a RunReport.

Who owns the loop? The Agent SDK does (it drives a bundled Claude Code process). We do
not write `while stop_reason == "tool_use"`; we configure it and observe it. See
ADR 0001 for that tradeoff and labs/raw_loop.py for the loop written by hand.

Stopping, in order of importance:
  1. The model finishes by itself (a final turn with no tool calls). This is the normal
     stop and the only one that yields an answer.
  2. max_turns and max_budget_usd are BACKSTOPS against runaway loops. Hitting one is a
     reported failure (outcome "max_turns" / "max_budget"), never silently treated as success.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolAnnotations,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_sdk_mcp_server,
    tool,
)
from claude_agent_sdk import query as sdk_query

from assistant.core.registry import ToolRegistry
from assistant.core.report import RunReport, ToolCallRecord
from assistant.core.tooling import ErrorCategory, RiskLevel, ToolSpec, err
from assistant.policies.lockdown import lockdown_options

SERVER_NAME = "assistant"
DEFAULT_MODEL = "claude-sonnet-5-5"

QueryFn = Callable[..., AsyncIterator[Any]]


@dataclass(frozen=True)
class AgentConfig:
    today: date  # injected, never read from the clock here, so runs are reproducible
    model: str = DEFAULT_MODEL
    max_turns: int = 10  # backstop
    max_budget_usd: float = 0.25  # backstop (checked after each response; may overshoot by one)
    effort: str | None = None  # None = SDK/model default


def build_system_prompt(today: date) -> str:
    # This is GUIDANCE. Anything that must hold is enforced in code (policies/), not here.
    return (
        "You are a personal assistant for one user.\n"
        f"Today's date is {today:%A, %Y-%m-%d}.\n\n"
        "Answer questions about the user's calendar and spending using the provided tools.\n"
        "- Resolve relative dates ('next Tuesday', 'this month') against today's date before "
        "calling a tool. If a date was ambiguous, say which date you used.\n"
        "- Take facts and totals from tool results. Never estimate or invent them. Totals "
        "returned by a tool are exact; do not recompute them.\n"
        "- If a tool returns no data for the period asked, say so plainly and mention the "
        "period the data covers.\n"
        "- If a tool returns an error, check its 'retryable' flag: retry a transient error at "
        "most once; fix the input for a validation error; otherwise explain the problem briefly.\n"
        "- You can only read information. You cannot create, change, or delete anything.\n"
        "Keep answers short."
    )


def _wrap_tool(spec: ToolSpec):
    """Adapt a ToolSpec to an SDK tool. Handler failures become structured error results."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            envelope = spec.handler(args)
        except Exception as exc:  # noqa: BLE001 - a handler bug must not crash the loop
            envelope = err(ErrorCategory.INTERNAL, f"tool crashed: {type(exc).__name__}")
        return {
            "content": [{"type": "text", "text": json.dumps(envelope)}],
            "is_error": not envelope.get("ok", False),
        }

    annotations = ToolAnnotations(readOnlyHint=True) if spec.risk is RiskLevel.READ_ONLY else None
    return tool(spec.name, spec.description, spec.input_schema, annotations=annotations)(handler)


def build_options(registry: ToolRegistry, config: AgentConfig) -> ClaudeAgentOptions:
    server = create_sdk_mcp_server(
        name=SERVER_NAME, version="0.1.0", tools=[_wrap_tool(s) for s in registry.specs()]
    )
    kwargs: dict[str, Any] = dict(
        model=config.model,
        system_prompt=build_system_prompt(config.today),
        mcp_servers={SERVER_NAME: server},
        max_turns=config.max_turns,
        max_budget_usd=config.max_budget_usd,
        **lockdown_options(SERVER_NAME, registry.names()),
    )
    if config.effort is not None:
        kwargs["effort"] = config.effort
    return ClaudeAgentOptions(**kwargs)


def _short_name(full: str) -> str:
    prefix = f"mcp__{SERVER_NAME}__"
    return full.removeprefix(prefix)


def _apply_result(report: RunReport, msg: ResultMessage) -> None:
    report.subtype = msg.subtype
    report.stop_reason = msg.stop_reason
    report.num_turns = msg.num_turns
    report.cost_usd = msg.total_cost_usd
    report.session_id = msg.session_id
    report.duration_ms = msg.duration_ms
    if msg.stop_reason == "refusal":
        report.outcome = "refused"
        report.error = "the model declined this request"
    elif msg.subtype == "success" and not msg.is_error:
        report.outcome = "completed"
        report.final_text = msg.result or report.final_text
    elif msg.subtype == "error_max_turns":
        report.outcome = "max_turns"
        report.error = "hit the max_turns backstop before finishing"
    elif msg.subtype == "error_max_budget_usd":
        report.outcome = "max_budget"
        report.error = "hit the max_budget_usd backstop before finishing"
    else:
        report.outcome = "error"
        detail = "; ".join(msg.errors or []) or msg.result or ""
        status = f" (HTTP {msg.api_error_status})" if msg.api_error_status else ""
        report.error = f"{msg.subtype}{status} {detail}".strip()


async def run_agent(
    prompt: str,
    registry: ToolRegistry,
    config: AgentConfig,
    *,
    query_fn: QueryFn | None = None,
) -> RunReport:
    """Run one agent session to completion and return a RunReport. Never raises for run failures."""
    report = RunReport()
    by_id: dict[str, ToolCallRecord] = {}
    last_text = ""
    saw_result = False
    try:
        options = build_options(registry, config)
        stream = (query_fn or sdk_query)(prompt=prompt, options=options)
        # Iterate to the end; do not `break` early (the SDK warns this breaks async cleanup).
        async for msg in stream:
            if isinstance(msg, SystemMessage) and msg.subtype == "init":
                tools = msg.data.get("tools") if isinstance(msg.data, dict) else None
                report.available_tools = list(tools) if isinstance(tools, list) else None
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock):
                        rec = ToolCallRecord(_short_name(block.name), dict(block.input), block.id)
                        report.tool_calls.append(rec)
                        by_id[block.id] = rec
                    elif isinstance(block, TextBlock):
                        last_text = block.text
            elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, ToolResultBlock) and block.tool_use_id in by_id:
                        by_id[block.tool_use_id].is_error = bool(block.is_error)
            elif isinstance(msg, ResultMessage):
                saw_result = True
                report.final_text = last_text
                _apply_result(report, msg)
    except Exception as exc:  # noqa: BLE001 - boundary: any SDK/process failure becomes a report
        # A single-shot query() raises AFTER yielding an error result (max_turns etc.).
        # If we already recorded that result, keep it; otherwise this is a process/connection
        # failure that produced no result at all.
        if not saw_result:
            report.outcome = "error"
            report.error = f"{type(exc).__name__}: {exc}"
    if not saw_result and report.error is None:
        report.error = "the run ended without a result message"
    return report
