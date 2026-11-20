"""LAB (not part of the product): the agentic loop written by hand.

The product uses the Claude Agent SDK, which runs this loop for you inside a bundled
process. This lab shows the loop itself, so here it is with the plain
Anthropic SDK, reusing the product's tools and registry.

    python labs/raw_loop.py "How much did I spend on dining in October?"

Read it top to bottom; the numbered comments are the lifecycle:

  1. send messages + tools to the model
  2. append the assistant turn to history UNCHANGED (thinking blocks must round-trip)
  3. branch on stop_reason:
       "end_turn"  -> the model is done: return its text      (the real stopping condition)
       "tool_use"  -> run EVERY requested tool, send ALL results back in ONE user message
       anything else (max_tokens, refusal, ...) -> stop and REPORT it; never present as an answer
  4. loop

Anti-patterns this avoids:
  - deciding to stop by parsing the model's prose ("I'm done", "Final answer:")
  - treating "the assistant produced some text" as completion (it may also contain tool calls)
  - using an iteration cap as the primary stop. MAX_ITERATIONS below is only a safety net,
    and hitting it is reported as a failure.

Notes: no tool_choice is set (forced tool_choice is rejected by this model; "auto" is default).
Server-side refusal fallbacks are deliberately NOT enabled here so that `refusal` handling
stays visible. Needs `pip install -e ".[labs]"` and a real ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assistant.core.registry import ToolRegistry
from assistant.core.runner import DEFAULT_MODEL, build_system_prompt
from assistant.core.tooling import ErrorCategory, err

MAX_ITERATIONS = 15  # safety net only


@dataclass
class RawLoopResult:
    stop_reason: str  # the model's final stop_reason, or "max_iterations"
    text: str = ""
    iterations: int = 0
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    @property
    def completed(self) -> bool:
        return self.stop_reason == "end_turn"


def anthropic_tools(registry: ToolRegistry) -> list[dict[str, Any]]:
    return [
        {"name": s.name, "description": s.description, "input_schema": s.input_schema}
        for s in registry.specs()
    ]


def execute_tool(registry: ToolRegistry, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
    """Run one tool. Returns (json text for the model, is_error)."""
    spec = registry.get(name)
    if spec is None:
        envelope = err(ErrorCategory.VALIDATION, f"Unknown tool {name!r}.")
    else:
        try:
            envelope = spec.handler(tool_input)
        except Exception as exc:  # noqa: BLE001 - tool bugs become error results
            envelope = err(ErrorCategory.INTERNAL, f"tool crashed: {type(exc).__name__}")
    return json.dumps(envelope), not envelope["ok"]


def run_raw_loop(
    prompt: str,
    registry: ToolRegistry,
    create: Callable[..., Any],
    *,
    system: str,
    model: str = DEFAULT_MODEL,
    max_iterations: int = MAX_ITERATIONS,
) -> RawLoopResult:
    tools = anthropic_tools(registry)
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    result = RawLoopResult(stop_reason="max_iterations")

    for iteration in range(1, max_iterations + 1):
        # 1. send the full history every time: the API is stateless
        response = create(
            model=model, max_tokens=16000, system=system, tools=tools, messages=messages
        )
        result.iterations = iteration
        result.stop_reason = response.stop_reason

        # 2. keep the assistant turn exactly as returned (do not rebuild or filter blocks)
        messages.append({"role": "assistant", "content": response.content})

        # 3. branch on stop_reason, not on the text
        if response.stop_reason == "end_turn":
            result.text = "".join(b.text for b in response.content if b.type == "text")
            return result

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result.tool_calls.append((block.name, dict(block.input)))
                text, is_error = execute_tool(registry, block.name, dict(block.input))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": text,
                        "is_error": is_error,
                    }
                )
            # ALL results for this turn go back together in ONE user message
            messages.append({"role": "user", "content": tool_results})
            continue  # 4. loop

        # max_tokens (truncated), refusal, pause_turn, ...: stop and report honestly
        return result

    result.stop_reason = "max_iterations"
    return result


def main() -> int:
    from anthropic import Anthropic

    from assistant.adapters.cli import api_key_problem, load_dotenv
    from assistant.tools import default_registry

    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    load_dotenv(ROOT / ".env")
    if problem := api_key_problem():
        print(f"error: {problem}", file=sys.stderr)
        return 2
    client = Anthropic()
    registry = default_registry(ROOT / "data" / "sample")
    result = run_raw_loop(
        sys.argv[1],
        registry,
        client.messages.create,
        system=build_system_prompt(date.today()),
    )
    for name, args in result.tool_calls:
        print(f"  -> {name}({json.dumps(args)})", file=sys.stderr)
    print(f"  stop_reason={result.stop_reason} iterations={result.iterations}", file=sys.stderr)
    print(result.text if result.completed else f"[{result.stop_reason}] no answer produced")
    return 0 if result.completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
