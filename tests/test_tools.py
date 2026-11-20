"""Tool handlers: exact outputs, structured errors, and the valid-empty-vs-error distinction."""

from pathlib import Path

import pytest

from assistant.tools.calendar import MAX_RANGE_DAYS, build_calendar_tools
from assistant.tools.expenses import build_expense_tools

DATA = Path(__file__).resolve().parents[1] / "data" / "sample"


@pytest.fixture
def cal():
    return build_calendar_tools(DATA)[0].handler


@pytest.fixture
def exp():
    return build_expense_tools(DATA)[0].handler


# ---------- calendar ----------


def test_calendar_single_day(cal):
    r = cal({"start_date": "2026-11-17", "end_date": "2026-11-17"})
    assert r["ok"] is True
    titles = [e["title"] for e in r["data"]["events"]]
    assert titles == ["Lunch with Maria", "Book club"]  # sorted by start time
    assert r["data"]["count"] == 2


def test_calendar_range_is_inclusive_and_sorted(cal):
    r = cal({"start_date": "2026-11-16", "end_date": "2026-11-18"})
    starts = [e["start"] for e in r["data"]["events"]]
    assert starts == sorted(starts)
    assert r["data"]["count"] == 6


def test_calendar_empty_window_is_ok_not_error(cal):
    r = cal({"start_date": "2027-03-01", "end_date": "2027-03-02"})
    assert r["ok"] is True
    assert r["data"]["count"] == 0 and r["data"]["events"] == []
    assert r["data"]["data_covers"]["first_event_date"] == "2026-11-09"


@pytest.mark.parametrize(
    "args",
    [
        {"start_date": "11/17/2026", "end_date": "2026-11-17"},  # wrong format
        {"start_date": "2026-11-17", "end_date": "tomorrow"},
        {"start_date": "2026-02-30", "end_date": "2026-03-01"},  # not a real date
        {"start_date": "2026-11-18", "end_date": "2026-11-17"},  # reversed
        {"start_date": "2026-01-01", "end_date": "2026-12-31"},  # too long
        {"start_date": 20261117, "end_date": "2026-11-17"},  # wrong type
    ],
)
def test_calendar_validation_errors_are_structured(cal, args):
    r = cal(args)
    assert r["ok"] is False
    assert r["error"]["category"] == "validation"
    assert r["error"]["retryable"] is False
    assert r["error"]["message"]


def test_calendar_max_range_boundary(cal):
    ok_end = "2026-12-31"  # 2026-11-01 .. 2026-12-31 is exactly 61 days
    assert cal({"start_date": "2026-11-01", "end_date": ok_end})["ok"] is True
    too_long = cal({"start_date": "2026-11-01", "end_date": "2027-01-02"})  # 63 days
    assert too_long["ok"] is False and str(MAX_RANGE_DAYS) in too_long["error"]["message"]


def test_calendar_missing_data_is_internal_error(tmp_path):
    handler = build_calendar_tools(tmp_path)[0].handler
    r = handler({"start_date": "2026-11-17", "end_date": "2026-11-17"})
    assert r["ok"] is False and r["error"]["category"] == "internal"
    assert r["error"]["retryable"] is False


# ---------- expenses ----------


def test_expenses_totals_are_exact(exp):
    r = exp({"month": "2026-10", "category": "dining"})
    assert r["ok"] is True
    assert r["data"]["total"] == 185.35
    assert r["data"]["count"] == 5
    assert set(r["data"]["by_category"]) == {"dining"}


def test_expenses_month_total_and_breakdown(exp):
    r = exp({"month": "2026-11"})
    d = r["data"]
    assert d["total"] == round(sum(e["amount"] for e in d["expenses"]), 2)
    assert abs(d["total"] - sum(d["by_category"].values())) < 0.005
    assert next(iter(d["by_category"])) == "housing"  # sorted by amount, largest first
    assert (
        max((e for e in d["expenses"] if e["category"] != "housing"), key=lambda e: e["amount"])[
            "merchant"
        ]
        == "Sky Airlines"
    )


def test_expenses_month_with_no_data_is_ok_with_zero(exp):
    r = exp({"month": "2026-01", "category": "groceries"})
    assert r["ok"] is True
    assert r["data"]["count"] == 0 and r["data"]["total"] == 0
    assert r["data"]["data_covers"] == {"first_month": "2026-10", "last_month": "2026-11"}


def test_expenses_unknown_category_lists_valid_ones(exp):
    r = exp({"month": "2026-10", "category": "Dining"})  # wrong case
    assert r["ok"] is False and r["error"]["category"] == "validation"
    assert "dining" in r["error"]["message"] and "groceries" in r["error"]["message"]


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "October", "2026-10-01", None, 202610])
def test_expenses_bad_month(exp, month):
    r = exp({"month": month})
    assert r["ok"] is False and r["error"]["category"] == "validation"


def test_expenses_malformed_data_is_internal_error(tmp_path):
    (tmp_path / "expenses.csv").write_text(
        "date,merchant,category,amount,note\n2026-10-01,X,housing,not-a-number,\n"
    )
    r = build_expense_tools(tmp_path)[0].handler({"month": "2026-10"})
    assert r["ok"] is False and r["error"]["category"] == "internal"


# ---------- tool descriptions (Domain 2.1) ----------


def test_descriptions_name_the_sibling_tool_and_formats():
    cal_spec = build_calendar_tools(DATA)[0]
    exp_spec = build_expense_tools(DATA)[0]
    assert "YYYY-MM-DD" in cal_spec.description and "get_expenses" in cal_spec.description
    assert "YYYY-MM" in exp_spec.description and "get_calendar_events" in exp_spec.description
