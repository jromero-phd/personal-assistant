"""Concrete tools. Each tool module exposes a build_*_tools(data_dir) factory."""

from __future__ import annotations

from pathlib import Path

from assistant.core.registry import ToolRegistry
from assistant.tools.calendar import build_calendar_tools
from assistant.tools.expenses import build_expense_tools


def default_registry(data_dir: Path) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register_all(build_calendar_tools(data_dir))
    registry.register_all(build_expense_tools(data_dir))
    return registry
