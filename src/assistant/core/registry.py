"""Tool registry: the single list of tools the agent is allowed to have."""

from __future__ import annotations

from assistant.core.tooling import RiskLevel, ToolSpec
from assistant.policies.registration import (
    PHASE1_ALLOWED_RISKS,
    PolicyViolation,
    check_registrable,
)


class ToolRegistry:
    def __init__(self, allowed_risks: frozenset[RiskLevel] = PHASE1_ALLOWED_RISKS) -> None:
        self._allowed_risks = allowed_risks
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        check_registrable(spec, self._allowed_risks)  # raises PolicyViolation
        if spec.name in self._tools:
            raise PolicyViolation(f"duplicate tool name {spec.name!r}")
        self._tools[spec.name] = spec

    def register_all(self, specs: list[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools)


__all__ = ["PolicyViolation", "ToolRegistry"]
