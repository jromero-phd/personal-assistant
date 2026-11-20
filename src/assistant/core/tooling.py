"""The tool contract: what every tool must declare, and the shape of every result.

This module is a leaf (it imports nothing from the rest of the project) so that
core/, tools/ and policies/ can all depend on it without import cycles.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class RiskLevel(str, Enum):
    """Declared side-effect level of a tool. Policies key off this, not off the prompt."""

    READ_ONLY = "read_only"  # no external effect; safe to run unattended
    REVERSIBLE = "reversible"  # has an effect that can be undone (e.g. a draft, a hold)
    IRREVERSIBLE = "irreversible"  # payments, sent messages, bookings


class ErrorCategory(str, Enum):
    """Why a tool failed. The agent recovers differently for each category."""

    TRANSIENT = "transient"  # timeout / service blip: retrying may work
    VALIDATION = "validation"  # the input was wrong: fix it and retry
    PERMISSION = "permission"  # not allowed: do not retry, explain
    BUSINESS = "business"  # a rule said no (limit, policy): do not retry, explain
    INTERNAL = "internal"  # our bug or broken data: do not retry, report


Envelope = dict[str, Any]
Handler = Callable[[dict[str, Any]], Envelope]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
_MIN_DESCRIPTION_CHARS = 80  # a one-liner is almost never enough to pick between tools


def ok(data: Any) -> Envelope:
    """Success. A valid empty result is still ok (data may be an empty list/count of 0)."""
    return {"ok": True, "data": data}


def err(category: ErrorCategory, message: str, *, retryable: bool | None = None) -> Envelope:
    """Failure with enough structure for the agent to choose a recovery.

    `retryable` defaults to True only for transient errors.
    """
    if retryable is None:
        retryable = category is ErrorCategory.TRANSIENT
    return {
        "ok": False,
        "error": {"category": category.value, "retryable": retryable, "message": message},
    }


@dataclass(frozen=True)
class ToolSpec:
    """One tool: a strict schema, a declared risk level, and a handler returning an Envelope."""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk: RiskLevel
    handler: Handler

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(f"tool name {self.name!r} must be snake_case, 3-41 chars")
        if len(self.description) < _MIN_DESCRIPTION_CHARS:
            raise ValueError(
                f"tool {self.name!r}: description too short ({len(self.description)} chars). "
                "Say what it does, input formats, edge cases, and when NOT to use it."
            )
        schema = self.input_schema
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError(
                f"tool {self.name!r}: input_schema must be an object schema with "
                "additionalProperties=false"
            )
        if not isinstance(self.risk, RiskLevel):
            raise TypeError(f"tool {self.name!r}: risk must be a RiskLevel")
