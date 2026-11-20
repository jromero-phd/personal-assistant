# Phase 1 notes: the agentic loop and tool design

## The concept: the agentic loop

1. Send the conversation plus tool definitions to the model.
2. Look at `stop_reason`.
   - `"tool_use"`: run every requested tool, append the results to the history, go again.
   - `"end_turn"`: the model is finished. Return its answer.
3. Anything else (`max_tokens`, `refusal`, ...) is not an answer: report it.

Key facts:
- The API is stateless. You resend the full history every turn, including the assistant's
  previous turn and your `tool_result` blocks. That is how the model "remembers" tool output.
- All tool results for one assistant turn go back together in **one** user message.
- A turn can contain text **and** tool calls. Text present does not mean done.
- The model decides the next step from context. A pre-built sequence of calls is a
  *workflow*, not an agent (that comparison is Phase 2).

Anti-patterns:
- Stopping by parsing the model's prose ("I'm done").
- Treating "assistant produced text" as completion.
- Using an iteration cap as the **primary** stop. It is a safety net. Hitting it is a failure
  you report.

Where to see it in this repo:
- By hand: `labs/raw_loop.py` (the whole loop in about 55 lines, `run_raw_loop`; tests in `tests/test_raw_loop.py`).
- Inside the Agent SDK: `core/runner.py` configures and observes it, but you do not see
  `stop_reason` per turn. That tradeoff is ADR 0001.

## The concept: tool design

- **The description is the interface.** The model picks tools from their descriptions.
  Minimal ones ("Retrieves order details") cause it to confuse similar tools. Good ones state
  inputs with examples, edge cases, and when to use a sibling tool instead. The fix to try
  first for misrouting is better descriptions, before few-shot examples, routing layers or
  merging tools.
- **Structured errors.** Return a category (`transient`/`validation`/`permission`/`business`),
  a `retryable` flag, and a human-readable message. Uniform "operation failed" gives the model
  nothing to decide with, and invites wasted retries.
- **Valid empty vs failure.** "No results" is a successful query. A timeout is a failure. If
  you blur them, the agent either retries pointlessly or reports a false "nothing found".
- **Fewer, scoped tools.** Reliability falls as the tool count per agent grows. Give each agent only what its role needs.
- **Put determinism in code.** Totals, validation and ordering rules belong in handlers and
  hooks. Prompt instructions are probabilistic.

## The tradeoff

Agent SDK (less code, built-in hooks/permissions/sessions; hides the loop and ships dangerous
default tools) vs raw loop (full visibility, more code, you own everything). We use the SDK for
the product and the raw loop for learning.

## Notes on model behavior

- Forced `tool_choice` (`"any"`, a named tool) returns a 400 on our model (`claude-sonnet-5-5`),
  and the Agent SDK does not expose it. `auto` may return text; forced selection would not stop
  semantic mistakes inside the output anyway.
- The subagent tool is named `Agent` in current SDK docs (older docs call it `Task`).
