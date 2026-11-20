"""Live eval runner for the assistant. Makes REAL API calls and spends real (small) money.

    python evals/run_evals.py                 # all scenarios
    python evals/run_evals.py --only no-tool-needed --runs 3

Every scenario also gets two automatic checks, regardless of its YAML:
  - lockdown: every tool the model was offered must be one of ours (no built-ins)
  - backstops: the run must finish by itself (outcome "completed"), not by hitting a limit

Results are written to evals/results/ (git-ignored).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assistant.adapters.cli import PROJECT_ROOT, api_key_problem, load_dotenv
from assistant.core.report import RunReport
from assistant.core.runner import AgentConfig, run_agent
from assistant.tools import default_registry

SCENARIO_FILE = ROOT / "evals" / "scenarios" / "phase1.yaml"
OUR_PREFIX = "mcp__assistant__"


@dataclass
class Scenario:
    id: str
    prompt: str
    tools_all_of: list[str]
    tools_none_of: list[str]
    answer_contains_all: list[str]
    answer_contains_any: list[str]
    answer_not_matches: list[str]


def load_scenarios(path: Path = SCENARIO_FILE) -> tuple[date, list[Scenario]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    scenarios = [
        Scenario(
            id=s["id"],
            prompt=s["prompt"],
            tools_all_of=s.get("tools_all_of", []),
            tools_none_of=s.get("tools_none_of", []),
            answer_contains_all=s.get("answer_contains_all", []),
            answer_contains_any=s.get("answer_contains_any", []),
            answer_not_matches=s.get("answer_not_matches", []),
        )
        for s in doc["scenarios"]
    ]
    return date.fromisoformat(doc["today"]), scenarios


def grade(s: Scenario, r: RunReport) -> list[str]:
    """Return a list of failure reasons (empty = pass). Pure function, unit-tested offline."""
    fails: list[str] = []
    if not r.completed:
        fails.append(f"run did not complete: {r.outcome} ({r.error})")
    called = set(r.tool_names)
    for t in s.tools_all_of:
        if t not in called:
            fails.append(f"expected tool not called: {t}")
    for t in s.tools_none_of:
        if t in called:
            fails.append(f"forbidden tool called: {t}")
    if r.available_tools is None:
        fails.append("lockdown unverified: SDK did not report the tool list")
    else:
        extra = [t for t in r.available_tools if not t.startswith(OUR_PREFIX)]
        if extra:
            fails.append(f"lockdown broken: model was offered {extra}")
    text = r.final_text
    for needle in s.answer_contains_all:
        if needle.lower() not in text.lower():
            fails.append(f"answer missing: {needle!r}")
    if s.answer_contains_any and not any(n.lower() in text.lower() for n in s.answer_contains_any):
        fails.append(f"answer has none of: {s.answer_contains_any}")
    for pattern in s.answer_not_matches:
        if re.search(pattern, text):
            fails.append(f"answer matched forbidden pattern: {pattern}")
    return fails


async def run_all(only: list[str] | None, runs: int, model: str) -> int:
    today, scenarios = load_scenarios()
    if only:
        scenarios = [s for s in scenarios if s.id in only]
    registry = default_registry(PROJECT_ROOT / "data" / "sample")
    config = AgentConfig(today=today, model=model)
    out_dir = ROOT / "evals" / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.jsonl"

    total_cost, failures, total_runs = 0.0, 0, 0
    with out_path.open("w", encoding="utf-8") as fh:
        for s in scenarios:
            for i in range(runs):
                report = await run_agent(s.prompt, registry, config)
                fails = grade(s, report)
                total_runs += 1
                failures += bool(fails)
                total_cost += report.cost_usd or 0.0
                status = "PASS" if not fails else "FAIL"
                print(
                    f"{status}  {s.id} [{i + 1}/{runs}] tools={report.tool_names} "
                    f"turns={report.num_turns} cost=${report.cost_usd or 0:.4f}"
                )
                for f in fails:
                    print(f"        - {f}")
                fh.write(json.dumps({"scenario": s.id, "fails": fails, **report.to_dict()}) + "\n")
    print(
        f"\n{total_runs - failures}/{total_runs} passed. Total cost ${total_cost:.4f}. Log: {out_path}"
    )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", help="scenario ids to run")
    parser.add_argument("--runs", type=int, default=1, help="repeat each scenario N times")
    parser.add_argument("--model", default=AgentConfig.model)
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    problem = api_key_problem()
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    return asyncio.run(run_all(args.only, args.runs, args.model))


if __name__ == "__main__":
    raise SystemExit(main())
