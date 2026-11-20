# ADR 0002: Repo layout, the device-agnostic core, and tool lockdown

Status: accepted (Phase 1). Date: 2026-11-14.

## Context

The assistant must run on a laptop, later a Raspberry Pi, later a phone client, and maybe
dedicated hardware. So the logic cannot assume a terminal, a clock, a filesystem layout, or
environment variables.

## Decision

```
src/assistant/
  core/       runner, report, registry, the tool contract. No clock, no env, no CLI.
  tools/      concrete tools; each takes a data directory, so storage is injectable.
  policies/   deterministic guardrails (registration rule, tool lockdown). Later: approval gates.
  memory/     empty until Phase 4.
  adapters/   thin entry points. Only layer that reads the clock, env, or .env.
```

Rules, enforced by `tests/test_layering.py` (it reads imports, so it cannot rot silently):

- `core/` never imports `adapters/` or the concrete `tools/`. It only knows the `ToolSpec` contract.
- `policies/` depends only on the tool contract.
- `core/`, `tools/`, `policies/` never call `date.today()`, `datetime.now()` or `os.environ`.
  "Today" is injected through `AgentConfig.today`, which also makes evals reproducible.

A Raspberry Pi should only need a different adapter. A phone client would be another one.

## Tool lockdown (policy, not prompt)

The Agent SDK offers Claude Code's built-in tools by default, and `allowed_tools` only
auto-approves; it does not remove anything. We layer defenses (`policies/lockdown.py`):

1. `tools=[]` (SDK passes `--tools ""`): no built-in tools offered.
2. `disallowed_tools`: explicit deny list as a backstop.
3. `permission_mode="dontAsk"`: anything not pre-approved is denied, never prompted.
4. `setting_sources=[]` and `strict_mcp_config=True`: no settings, hooks, skills, or MCP
   servers from this machine's Claude Code config leak into the assistant.

Verified offline: the SDK turns these options into the expected command-line flags.
**Not yet verified live:** that the real binary honors them. The live eval checks it on every
run (`lockdown` check in `evals/run_evals.py`: the model must be offered only `mcp__assistant__*`).

## Workflow or agent?

N/A (structure, not a capability).

## What is deterministic vs left to the model

Everything in this ADR is deterministic. None of it relies on telling the model to behave.

## Tradeoffs

- More files than a single script. The payoff is that Phase 5 (scheduler) and Phase 9 (Pi)
  add adapters without touching core.
- A venv is not a sandbox. It isolates packages, not permissions. The lockdown is what
  contains the agent.
