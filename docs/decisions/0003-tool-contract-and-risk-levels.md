# ADR 0003: The tool contract (schema, risk level, result envelope, errors)

Status: accepted (Phase 1). Date: 2026-11-14.

## Context

Tools are how the model touches the world. Their interface decides how reliably the model
picks the right one and recovers from failure.

## Decision

Every tool is a `ToolSpec` (`core/tooling.py`) with:

1. **A strict input schema**: object, `additionalProperties: false`. Enforced when the spec
   is built.
2. **A declared risk level**: `read_only`, `reversible`, `irreversible`. Policies key off
   this. In Phase 1 the registry refuses anything but `read_only` (`policies/registration.py`),
   so a side-effecting tool cannot be added before the approval gate exists (Phase 3).
3. **A real description** (at least 80 characters, enforced). Ours state what the tool does,
   input formats with an example, limits, what an empty result means, and which sibling tool
   to use for other questions. Minimal descriptions cause misrouting between similar tools.
4. **One result envelope**: `{"ok": true, "data": ...}` or
   `{"ok": false, "error": {"category", "retryable", "message"}}`. The SDK `is_error` flag is
   set from `ok`.
5. **Error categories**: `transient` (retryable), `validation`, `permission`, `business`,
   `internal` (not retryable). A generic "operation failed" gives the model nothing to decide on.
6. **Valid empty is not an error.** "No events that day" and "no spending recorded for that
   month" return `ok: true` with count 0 and a `data_covers` range, so the model can tell
   "nothing there" from "the lookup broke".

Arithmetic lives in code. `get_expenses` returns exact totals (Decimal) and per-category
totals. The model never adds numbers.

## Two layers of input validation (a wrinkle worth knowing)

The SDK validates input against the JSON schema before our handler runs, and a schema failure
comes back to the model as plain text, not our envelope. So the schema only checks shape and
required fields. Format rules (dates, month, category) are checked in our handler, which
returns the structured `validation` error with an example. The model sees the version we
designed.

## Workflow or agent?

Tools are building blocks for either. See ADR 0004.

## What is deterministic vs left to the model

- Deterministic: validation, range limits, filtering, sorting, totals, error shape, risk rule.
- Model: choosing a tool, converting "next Tuesday" to a date, explaining results.

## Tradeoffs

- Split by data type (calendar vs expenses) rather than one `lookup` tool. Narrow tools are
  easier to describe and select; the cost is more tools as we grow. If we pass ~5 tools per
  agent we revisit (tool selection tends to degrade as tool count grows).
- Month-at-a-time expense queries mean a multi-month question costs several calls. That is
  fine at this scale and keeps each result small.
