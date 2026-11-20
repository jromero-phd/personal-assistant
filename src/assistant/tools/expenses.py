"""get_expenses: read-only lookup over a local CSV of expenses.

Division of labour (Domain 2 / ADR 0003):
  - CODE: month/category validation, filtering, and ALL arithmetic (totals, per-category
    totals) using Decimal. The model never has to add numbers, so it cannot get them wrong.
  - MODEL: choosing the month/category from a free-form question and explaining the result.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from assistant.core.tooling import Envelope, ErrorCategory, RiskLevel, ToolSpec, err, ok

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

DESCRIPTION = (
    "Look up the user's recorded expenses for ONE calendar month, optionally narrowed to one "
    "category. Use it for questions about spending, how much was spent, biggest purchases, "
    "or where money went. "
    "month must be formatted YYYY-MM (example: 2026-10); a multi-month question needs one call "
    "per month. category is optional and exact-match lowercase (examples: groceries, dining, "
    "housing, transport, utilities, subscriptions, shopping, health, travel, entertainment, "
    "personal_care); an unknown category returns a validation error listing the valid ones. "
    "Returns: total and by_category totals in dollars (already computed exactly, so do not "
    "re-add), count, the expenses (date, merchant, category, amount, note) and data_covers "
    "(first and last month with any data). "
    "A month with no expenses returns ok=true with count 0 and total 0; that means no data, "
    "not a failure. This tool has no calendar information: use get_calendar_events for "
    "schedule questions."
)

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "month": {"type": "string", "description": "Month to look up, YYYY-MM."},
        "category": {
            "type": "string",
            "description": "Optional category filter, lowercase exact match.",
        },
    },
    "required": ["month"],
    "additionalProperties": False,
}


def _load(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            try:
                rows.append(
                    {
                        "date": row["date"],
                        "merchant": row["merchant"],
                        "category": row["category"],
                        "amount": Decimal(row["amount"]),
                        "note": row.get("note") or "",
                    }
                )
            except (KeyError, InvalidOperation) as exc:
                raise ValueError(f"malformed expense row at line {line_no}") from exc
    return rows


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def build_expense_tools(data_dir: Path) -> list[ToolSpec]:
    path = Path(data_dir) / "expenses.csv"

    def handler(args: dict[str, Any]) -> Envelope:
        month = args.get("month")
        if not isinstance(month, str) or not _MONTH.match(month):
            return err(
                ErrorCategory.VALIDATION,
                f"month must be formatted YYYY-MM (for example 2026-10); got {month!r}.",
            )
        category = args.get("category")
        if category is not None and not isinstance(category, str):
            return err(ErrorCategory.VALIDATION, "category must be a string if provided.")
        try:
            rows = _load(path)
        except FileNotFoundError:
            return err(ErrorCategory.INTERNAL, "The expense data source is not available.")
        except (ValueError, OSError):
            return err(ErrorCategory.INTERNAL, "The expense data source could not be read.")

        known = sorted({r["category"] for r in rows})
        if category is not None and category not in known:
            return err(
                ErrorCategory.VALIDATION,
                f"Unknown category {category!r}. Valid categories: {', '.join(known)}.",
            )

        selected = [
            r
            for r in rows
            if r["date"].startswith(month) and (category is None or r["category"] == category)
        ]
        selected.sort(key=lambda r: (r["date"], r["merchant"]))
        by_cat: dict[str, Decimal] = defaultdict(Decimal)
        for r in selected:
            by_cat[r["category"]] += r["amount"]
        months = sorted({r["date"][:7] for r in rows})
        return ok(
            {
                "month": month,
                "category": category,
                "count": len(selected),
                "total": _money(sum((r["amount"] for r in selected), Decimal(0))),
                "by_category": {
                    c: _money(v) for c, v in sorted(by_cat.items(), key=lambda kv: -kv[1])
                },
                "expenses": [{**r, "amount": _money(r["amount"])} for r in selected],
                "data_covers": {
                    "first_month": months[0] if months else None,
                    "last_month": months[-1] if months else None,
                },
            }
        )

    return [
        ToolSpec(
            name="get_expenses",
            description=DESCRIPTION,
            input_schema=INPUT_SCHEMA,
            risk=RiskLevel.READ_ONLY,
            handler=handler,
        )
    ]
