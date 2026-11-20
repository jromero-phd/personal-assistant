"""CLI adapter: a thin entry point. All real logic lives in core/ and tools/.

This is the only layer that reads the clock, the environment, or .env. A Raspberry Pi or
a phone client would be another adapter next to this one.

    assistant ask "What's on my calendar next Tuesday?" --trace
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

from assistant.core.runner import DEFAULT_MODEL, AgentConfig, run_agent
from assistant.tools import default_registry

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "sample"
PLACEHOLDER_KEY_MARKER = "REPLACE_ME"


def load_dotenv(path: Path) -> None:
    """Minimal .env loader. Never overrides variables already set in the environment."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def api_key_problem() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return "ANTHROPIC_API_KEY is not set. Copy your key into .env (see README)."
    if PLACEHOLDER_KEY_MARKER in key:
        return "ANTHROPIC_API_KEY in .env is still the placeholder. Paste a real key (see README)."
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="assistant", description="Personal assistant agent")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Ask the assistant one question")
    ask.add_argument("question")
    ask.add_argument("--trace", action="store_true", help="Show tool calls, turns, and cost")
    ask.add_argument("--json", action="store_true", help="Print the full RunReport as JSON")
    ask.add_argument("--today", type=date.fromisoformat, default=None, help="Override today's date")
    ask.add_argument("--data-dir", type=Path, default=None, help="Folder with calendar.json etc.")
    ask.add_argument("--model", default=DEFAULT_MODEL)
    ask.add_argument("--max-turns", type=int, default=10)
    ask.add_argument("--max-budget", type=float, default=0.25, help="USD backstop per run")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(PROJECT_ROOT / ".env")
    problem = api_key_problem()
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    data_dir = args.data_dir or Path(os.environ.get("ASSISTANT_DATA_DIR", DEFAULT_DATA_DIR))
    config = AgentConfig(
        today=args.today or date.today(),
        model=args.model,
        max_turns=args.max_turns,
        max_budget_usd=args.max_budget,
    )
    report = asyncio.run(run_agent(args.question, default_registry(data_dir), config))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.final_text if report.completed else f"[{report.outcome}] {report.error}")
    if args.trace and not args.json:
        for call in report.tool_calls:
            flag = " (error)" if call.is_error else ""
            print(f"  -> {call.name}({json.dumps(call.input)}){flag}", file=sys.stderr)
        cost = f"${report.cost_usd:.4f}" if report.cost_usd is not None else "n/a"
        print(
            f"  outcome={report.outcome} turns={report.num_turns} cost={cost} "
            f"tools_offered={report.available_tools}",
            file=sys.stderr,
        )
    return 0 if report.completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
