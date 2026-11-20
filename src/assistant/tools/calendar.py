"""get_calendar_events: read-only lookup over a local JSON calendar.

Division of labour (Domain 2 / ADR 0003):
  - CODE: date parsing and validation, range limits, filtering, sorting, structured errors.
  - MODEL: deciding WHEN to call this, and turning "next Tuesday" into a concrete date.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from assistant.core.tooling import Envelope, ErrorCategory, RiskLevel, ToolSpec, err, ok

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_RANGE_DAYS = 62

DESCRIPTION = (
    "List the user's calendar events that START between start_date and end_date, inclusive, "
    "sorted by start time. Use it for questions about schedule, appointments, meetings, "
    "what is on a given day, free time, or overlapping events. "
    "Both dates must be ISO format YYYY-MM-DD (example: 2026-11-17); for a single day pass the "
    "same date as start_date and end_date. The maximum range is 62 days. "
    "Event times are local time with no timezone. "
    "Returns: count, events (id, title, start, end, location, notes) and data_covers "
    "(date of the first and last event on the calendar). "
    "An empty events list with ok=true means nothing is scheduled in that window; it is not a "
    "failure. This tool has no spending information: use get_expenses for money questions."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "start_date": {"type": "string", "description": "First day to include, YYYY-MM-DD."},
        "end_date": {"type": "string", "description": "Last day to include, YYYY-MM-DD."},
    },
    "required": ["start_date", "end_date"],
    "additionalProperties": False,
}


def _parse_date(field: str, value: Any) -> date | Envelope:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return err(
            ErrorCategory.VALIDATION,
            f"{field} must be a date formatted YYYY-MM-DD (for example 2026-11-17); got {value!r}.",
        )
    try:
        return date.fromisoformat(value)
    except ValueError:
        return err(ErrorCategory.VALIDATION, f"{field} {value!r} is not a real calendar date.")


def build_calendar_tools(data_dir: Path) -> list[ToolSpec]:
    path = Path(data_dir) / "calendar.json"

    def handler(args: dict[str, Any]) -> Envelope:
        start = _parse_date("start_date", args.get("start_date"))
        if isinstance(start, dict):
            return start
        end = _parse_date("end_date", args.get("end_date"))
        if isinstance(end, dict):
            return end
        if end < start:
            return err(ErrorCategory.VALIDATION, "end_date must not be before start_date.")
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            return err(
                ErrorCategory.VALIDATION,
                f"Range too large: at most {MAX_RANGE_DAYS} days per call. Split it into smaller "
                "ranges.",
            )
        try:
            events = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return err(ErrorCategory.INTERNAL, "The calendar data source is not available.")
        except (json.JSONDecodeError, OSError):
            return err(ErrorCategory.INTERNAL, "The calendar data source could not be read.")

        in_range = [e for e in events if start <= date.fromisoformat(e["start"][:10]) <= end]
        in_range.sort(key=lambda e: e["start"])
        starts = sorted(e["start"][:10] for e in events)
        return ok(
            {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "count": len(in_range),
                "events": in_range,
                "data_covers": {
                    "first_event_date": starts[0] if starts else None,
                    "last_event_date": starts[-1] if starts else None,
                },
            }
        )

    return [
        ToolSpec(
            name="get_calendar_events",
            description=DESCRIPTION,
            input_schema=INPUT_SCHEMA,
            risk=RiskLevel.READ_ONLY,
            handler=handler,
        )
    ]
