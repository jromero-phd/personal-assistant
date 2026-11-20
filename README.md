# Personal assistant: the foundation of a conversational butler

The long-term goal is a personal assistant that becomes the way people interact with technology:
a conversational agent that deals with any company or entity on your behalf, as a butler would,
instead of one app per company. Voice is an important modality and AR glasses may add a visual
layer later. This repo is the small, early foundation, built phase by phase. Core logic is
device-agnostic; entry points (CLI today, voice and others later) are thin adapters. See
`docs/decisions/0005-product-vision.md`. Everything with side effects will go through mock tools behind code-enforced approval
gates. No real credentials or money.

## Status

**Phase 1 (foundations) is built and tested offline. It has not yet been run against the live API**,
because no API key has been supplied. See "Live verification" below for exactly what that leaves open.

- Offline: 61 tests pass (`pytest`), lint clean.
- Live: not run. Nothing below under "Live verification" is confirmed yet.

## Setup

Requires Python 3.10+ (developed on 3.14).

```bash
cd ~/projects/personal-assistant
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,labs]"
```

The Agent SDK bundles its own Claude Code binary (~344 MB), so no Node or separate install is
needed. Each venv is therefore large (~430 MB).

### API key

Create a file named `.env` in the project root containing one line (it is git-ignored):

```
ANTHROPIC_API_KEY=sk-ant-REPLACE_ME
```

Replace the placeholder with a real key when you have one (a dedicated key with a low spend cap is
a good idea). The CLI refuses to run while the placeholder is in place. Offline tests never need it.
The Agent SDK requires an API key; a claude.ai login is not supported for this.

## Run it

```bash
pytest                                              # offline tests, no key needed
assistant ask "What's on my calendar next Tuesday?" --trace
assistant ask "How much did I spend on dining in October?" --today 2026-11-14 --trace
python evals/run_evals.py                           # live evals (spends real, small money)
python evals/run_evals.py --only no-tool-needed --runs 3
python labs/raw_loop.py "How much did I spend on dining in October?"   # the loop by hand
```

Sample data is synthetic and lives in `data/sample/` (calendar for Nov-Dec 2026, expenses for
Oct-Nov 2026). Use `--today 2026-11-14` to match the eval scenarios.

## Layout

```
src/assistant/
  core/       runner (Agent SDK wrapper), RunReport, registry, tool contract
  tools/      get_calendar_events, get_expenses (both read-only)
  policies/   registration rule (read-only only, for now), tool lockdown
  memory/     empty until Phase 4
  adapters/   cli.py (the only layer that reads clock/env/.env)
data/sample/  synthetic calendar and expenses
evals/        scenarios (YAML) + live runner
labs/         raw_loop.py: a lab showing the loop by hand, not product
tests/        offline tests
docs/decisions/  ADRs (design record)   docs/notes/  design notes
```

## Live verification (still open)

Verified offline: the SDK turns our options into the intended CLI flags
(`--tools ''`, allow/deny lists, `dontAsk`, `--strict-mcp-config`, `--setting-sources=`); every
stop condition is handled; tools, grader and the hand-written loop behave as designed.

Not verified until a real key is in `.env`:

1. The real binary honors `--tools ''`: run `assistant ask "hi" --trace` and confirm
   `tools_offered` contains only `mcp__assistant__*` names.
2. Adversarial check: `assistant ask "Run ls in the shell and show me the output" --trace` makes
   no shell/file call.
3. `claude-sonnet-5-5` is accepted by the bundled binary, and the whole stack works on Python 3.14.
4. What the model sees on a schema-level validation failure (see ADR 0003).
5. Eval pass rate, run-to-run variance (`--runs 3`), and measured cost per run. Cost figures
   are intentionally absent from the docs until measured.

## Phases

1. Foundations (this) 2. Workflow vs agent 3. Guardrails and human-in-the-loop 4. Memory and
context 5. Proactivity 6. MCP 7. Multi-agent 8. Reliability 9. Portability.
