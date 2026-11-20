# ADR 0004: Phase 1 capability: "answer questions about my calendar and spending"

Status: accepted (Phase 1). Date: 2026-11-14.

## Workflow or agent? Agent. With a caveat.

An **agent** (model decides the tool calls) rather than a fixed command or a prompt chain.

Why it fits: the path cannot be predicted from the input. "What's on next Tuesday?" needs the
calendar. "How much on dining in October?" needs expenses. "When is my dentist and what did I
pay them?" needs both, in either order. The model has to map free text onto tools and
arguments, and sometimes call a tool twice.

The caveat, stated plainly: a single lookup like "what's on tomorrow?" could be a fixed
command with no model at all (a date picker and a query). If every request were one lookup,
a workflow would be cheaper, faster and fully predictable. We use an agent here because
mapping free-form language to tools is what this phase practices, not because lookups need
one. Phase 2 does the comparison properly (same task as a fixed chain vs as an agent) and
may revise this.

## What is deterministic vs left to the model

| Deterministic (code, schemas, config) | Left to the model's judgment |
|---|---|
| Which tools exist and their schemas | Whether and which tool to call |
| Read-only only (registry rule) | Arguments (e.g. what "next Tuesday" is) |
| Lockdown: no shell, files, or web | Whether a second call is needed |
| Validation, filtering, totals | How to phrase the answer |
| Limits: 10 turns, $0.25 per run | Recovering from a tool error (guided by `retryable`) |
| How each outcome is reported | Saying "no data" instead of guessing (prompt guidance only) |

The last row is the weakest: "do not invent numbers" is a prompt instruction, so it can fail.
It is mitigated by exact totals from tools and checked by evals (`no-data-for-period`,
`expenses-category-total`), not guaranteed. Anything that must hold goes in code (Phase 3).

## Stopping

The model stops when it produces a turn with no tool calls. `max_turns` and
`max_budget_usd` are backstops, reported as failures when hit. An iteration cap as the
*primary* stop is an anti-pattern: it cuts off legitimate work and hides loops that never end.

## Evals

`evals/scenarios/phase1.yaml`: 7 scenarios graded deterministically (tools called, tools
forbidden, facts that must or must not appear). Two checks apply to every run: the lockdown
(model offered only our tools) and "finished by itself". The grader and the scenarios' facts
are tested offline. Live runs need an API key.

## Tradeoffs

- Predictability: lower than a workflow (the model may take a different path run to run).
  Evals run each scenario once by default; use `--runs N` to see variance.
- Cost and latency: several model turns per question, versus zero for a fixed command.
