"""Registration policy: which tools may exist in a given deployment.

This is deterministic code, not a prompt instruction. In Phase 1 only read-only tools
may be registered at all, so a side-effecting tool cannot be added by accident before
the approval gate (Phase 3) exists.
"""

from __future__ import annotations

from assistant.core.tooling import RiskLevel, ToolSpec

PHASE1_ALLOWED_RISKS: frozenset[RiskLevel] = frozenset({RiskLevel.READ_ONLY})


class PolicyViolation(Exception):
    """Raised when code tries to do something a policy forbids."""


def check_registrable(spec: ToolSpec, allowed_risks: frozenset[RiskLevel]) -> None:
    if spec.risk not in allowed_risks:
        allowed = ", ".join(sorted(r.value for r in allowed_risks))
        raise PolicyViolation(
            f"tool {spec.name!r} has risk {spec.risk.value!r}, but this deployment only allows: "
            f"{allowed}. Side-effecting tools need an approval gate first."
        )
