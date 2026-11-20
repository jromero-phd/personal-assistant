# ADR 0001: Python on the Claude Agent SDK (not a hand-written loop)

Status: accepted (Phase 1). Date: 2026-11-14.

## Context

We need an agent loop. There are three ways to get one:

| Option | Who runs the loop | Built-in tools | Fit for this project |
|---|---|---|---|
| Manual loop on the Anthropic SDK | us (`while stop_reason == "tool_use"`) | none | Most control and most code. Best for seeing the loop. |
| Tool Runner (Anthropic SDK, beta) | the SDK helper, for tools we define | none | Less code; per-turn hooks for approval/logging. |
| Claude Agent SDK | a bundled Claude Code process | Bash, Write, Edit, WebFetch, ... | Batteries included: hooks, permissions, sessions, subagents, MCP. |

You chose the Agent SDK (agent definitions, hooks, subagents, `allowedTools`).

## Decision

- Language: Python. Package: `claude-agent-sdk` (0.2.181 at time of writing). It needs
  Python 3.10+; we develop on 3.14.10 (installs and imports cleanly; see README for what
  has been run live).
- Model: `claude-sonnet-5-5`, one config value (`AgentConfig.model`).
- The product code never writes the loop. We configure it and observe it (`core/runner.py`).
- `labs/raw_loop.py` implements the loop by hand with the plain Anthropic SDK, to show what
  the Agent SDK hides. It is a lab, not product code.

## What we gave up (the honest part)

- **We do not see `stop_reason` per turn.** The Agent SDK hides it. We see a final
  `ResultMessage` with a `subtype`, `num_turns`, cost, and `stop_reason` of the last turn.
  Domain 1.1 is about handling `stop_reason` directly, hence the lab.
- **A big dependency.** The package bundles a ~344 MB Claude Code binary (about 430 MB per
  venv). The loop runs in a subprocess we do not control. Whether that runs well on a
  Raspberry Pi is unverified; we check in Phase 9.
- **Built-in tools are ON by default.** That is the wrong default for an assistant that must
  not touch the shell or filesystem. We lock them down in code (ADR 0002 / `policies/lockdown.py`).
- **Billing/limits are an estimate** (`total_cost_usd` is client-side).

## Workflow or agent?

The runner itself is neither: it is infrastructure. See ADR 0004 for the capability.

## What is deterministic vs left to the model

- Deterministic (code): which tools exist, their schemas, the lockdown, the backstop limits
  (`max_turns=10`, `max_budget_usd=0.25`), how every outcome maps to a report.
- Model judgment: whether to call a tool, which one, with what arguments, and when it is done.
- `max_turns` and the budget are backstops, not the stopping mechanism. The normal stop is
  the model finishing by itself. Hitting a backstop is reported as a failure.

## Notes

- This model rejects forced `tool_choice` (`any` / a named tool) with a 400 (per the current
  API reference), and the Agent SDK never sets it. Do not expect to use it here.
- Older docs call the subagent tool "Task". Current Agent SDK docs list it as `Agent`. We
  block both names in the lockdown list and will confirm which is live in Phase 7.
