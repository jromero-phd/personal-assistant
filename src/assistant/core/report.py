"""RunReport: a plain, serializable record of one agent run (no SDK types leak out)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Why the run ended. "completed" is the only outcome where final_text is an answer.
OUTCOMES = ("completed", "max_turns", "max_budget", "refused", "error")


@dataclass
class ToolCallRecord:
    name: str  # short name, e.g. "get_expenses" (server prefix stripped)
    input: dict[str, Any]
    tool_use_id: str = ""
    is_error: bool | None = None  # None until a result is seen


@dataclass
class RunReport:
    outcome: str = "error"
    final_text: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    num_turns: int = 0
    cost_usd: float | None = None
    stop_reason: str | None = None
    subtype: str | None = None
    error: str | None = None
    session_id: str | None = None
    duration_ms: int | None = None
    # Tools the model was actually offered (from the SDK's init message). None = not reported.
    available_tools: list[str] | None = None

    @property
    def completed(self) -> bool:
        return self.outcome == "completed"

    @property
    def tool_names(self) -> list[str]:
        return [c.name for c in self.tool_calls]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
