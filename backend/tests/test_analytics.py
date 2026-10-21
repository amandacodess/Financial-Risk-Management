"""Pure calculation tests: no database, no HTTP."""

from datetime import date
from decimal import Decimal as D

import pytest

from services import analytics as a

W, X = D(80), D(100)  # default warning / exceeded thresholds


def row(month, type, cat, amount, name=None):
    return {"month": month, "type": type, "category_id": cat,
            "category": name or f"cat{cat}", "amount": D(amount)}


# --- months and dates --------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("2026-10", date(2026, 10, 1)),
    ("2026-01", date(2026, 1, 1)),
    ("1999-12", date(1999, 12, 1)),
])
def test_parse_month(value, expected):
    assert a.parse_month(value) == expected


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "2026-1", "26-10", "2026/10", "", "2026-10-01", "abcd-ef"])
def test_parse_month_rejects_malformed(value):
    with pytest.raises(ValueError):
        a.parse_month(value)


def test_add_months_crosses_year_boundaries():
    assert a.add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert a.add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert a.add_months(date(2026, 3, 1), -14) == date(2025, 1, 1)


def test_month_range_is_half_open():
    assert a.month_range(date(2026, 2, 1)) == (date(2026, 2, 1), date(2026, 3, 1))


# --- income, expenses, net cash flow, savings rate ---------------------------

def test_figures_basic():
    f = a.figures(D("50000.00"), D("32000.50"))
    assert f["net_cash_flow"] == D("17999.50")
    assert f["savings_rate_pct"] == D("36.0")


def test_figures_negative_cash_flow():
    f = a.figures(D("1000"), D("1500"))
    assert f["net_cash_flow"] == D("-500")
    assert f["savings_rate_pct"] == D("-50.0")


def test_figures_zero_income_has_no_rate():
    f = a.figures(D("0"), D("1200"))
    assert f["net_cash_flow"] == D("-1200")
    assert f["savings_rate_pct"] is None


def test_figures_empty_period():
    f = a.figures(D("0"), D("0"))
    assert f == {"income": 0, "expenses": 0, "net_cash_flow": 0, "savings_rate_pct": None}


def test_decimal_sums_are_exact():
    # 0.1 + 0.2 in floating point is 0.30000000000000004.
    rows = [row(date(2026, 10, 1), "expense", 1, "0.10"), row(date(2026, 10, 1), "expense", 2, "0.20")]
    _, expenses, _ = a.month_totals(rows, date(2026, 10, 1))
    assert expenses == D("0.30")


def test_month_totals_only_counts_the_month():
    oct_, sep = date(2026, 10, 1), date(2026, 9, 1)
    rows = [
        row(oct_, "income", 9, "5000"), row(oct_, "expense", 1, "700"),
        row(sep, "expense", 1, "999"), row(sep, "income", 9, "999"),
    ]
    income, expenses, spent = a.month_totals(rows, oct_)
    assert (income, expenses) == (D("5000"), D("700"))
    assert spent == {1: {"category": "cat1", "amount": D("700")}}


# --- budget utilization ------------------------------------------------------

@pytest.mark.parametrize("spent,status,util", [
    ("0", "ok", "0.0"),
    ("79.99", "ok", "80.0"),       # rounds for display to 80.0 but is below 80
    ("80", "warning", "80.0"),     # exactly 80% -> warning
    ("100", "warning", "100.0"),   # exactly 100% -> at limit, not over
    ("100.01", "exceeded", "100.0"),
    ("150", "exceeded", "150.0"),
])
def test_budget_line_thresholds(spent, status, util):
    budgets = [{"category_id": 1, "category": "Food", "amount": D("100")}]
    spent_map = {1: {"category": "Food", "amount": D(spent)}} if D(spent) else {}
    [line] = a.budget_lines(budgets, spent_map, W, X)
    assert line["status"] == status
    assert line["utilization_pct"] == D(util)
    assert line["remaining"] == D("100") - D(spent)


def test_budget_status_boundaries():
    assert a.budget_status(None, W, X) == "no_budget"
    assert a.budget_status(D("79.99"), W, X) == "ok"
    assert a.budget_status(D("80"), W, X) == "warning"
    assert a.budget_status(D("100"), W, X) == "warning"
    assert a.budget_status(D("100.001"), W, X) == "exceeded"


def test_spending_without_budget_is_listed_as_no_budget():
    [line] = a.budget_lines([], {2: {"category": "Transport", "amount": D("40")}}, W, X)
    assert line == {"category_id": 2, "category": "Transport", "budget": None, "spent": D("40"),
                    "remaining": None, "utilization_pct": None, "status": "no_budget"}


def test_budget_lines_sorted_by_spend():
    budgets = [{"category_id": 1, "category": "A", "amount": D("10")},
               {"category_id": 2, "category": "B", "amount": D("10")}]
    spent = {2: {"category": "B", "amount": D("5")}}
    assert [l["category"] for l in a.budget_lines(budgets, spent, W, X)] == ["B", "A"]


def test_pct_zero_or_missing_whole():
    assert a.pct(D("10"), D("0")) is None
    assert a.pct(D("0"), D("0")) is None


# --- pace projection ---------------------------------------------------------

def test_pace_current_month():
    p = a.pace(D("1000"), date(2026, 10, 1), date(2026, 10, 10))
    assert p == {"days_elapsed": 10, "days_in_month": 31, "projected_expenses": D("3100.00")}


def test_pace_past_month_projects_actual():
    p = a.pace(D("1234.56"), date(2026, 2, 1), date(2026, 10, 20))
    assert p == {"days_elapsed": 28, "days_in_month": 28, "projected_expenses": D("1234.56")}


def test_pace_future_month_has_no_elapsed_days():
    p = a.pace(D("0"), date(2026, 12, 1), date(2026, 10, 20))
    assert p["days_elapsed"] == 0 and p["projected_expenses"] == 0


def test_pace_leap_february():
    assert a.pace(D("0"), date(2028, 2, 1), date(2028, 2, 29))["days_in_month"] == 29


# --- forecast and monthly series ---------------------------------------------

def test_forecast_averages_over_active_months():
    jul, aug, sep, oct_ = (date(2026, m, 1) for m in (7, 8, 9, 10))
    rows = [
        row(jul, "expense", 1, "300", "Food"), row(aug, "expense", 1, "600", "Food"),
        row(sep, "expense", 1, "900", "Food"), row(sep, "expense", 2, "90", "Fun"),
        row(oct_, "expense", 1, "99999", "Food"),  # the target month itself is excluded
        row(sep, "income", 3, "5000", "Salary"),   # income is not forecast
    ]
    assert a.forecast(rows, oct_) == [
        {"category_id": 1, "category": "Food", "predicted": D("600.00")},
        {"category_id": 2, "category": "Fun", "predicted": D("30.00")},
    ]


def test_forecast_with_one_month_of_history_is_not_divided_by_three():
    rows = [row(date(2026, 9, 1), "expense", 1, "300")]
    assert a.forecast(rows, date(2026, 10, 1))[0]["predicted"] == D("300.00")


def test_forecast_empty():
    assert a.forecast([], date(2026, 10, 1)) == []


def test_monthly_series_fills_empty_months_and_orders_oldest_first():
    rows = [row(date(2026, 9, 1), "income", 9, "1000"), row(date(2026, 9, 1), "expense", 1, "250")]
    series = a.monthly_series(rows, date(2026, 10, 1), 3)
    assert [m["month"] for m in series] == ["2026-08", "2026-09", "2026-10"]
    assert series[0]["savings_rate_pct"] is None
    assert series[1]["net_cash_flow"] == D("750") and series[1]["savings_rate_pct"] == D("75.0")


def test_average_savings_rate_skips_months_without_income():
    series = [{"savings_rate_pct": D("50")}, {"savings_rate_pct": None}, {"savings_rate_pct": D("10")}]
    assert a.average_savings_rate(series) == D("30.0")
    assert a.average_savings_rate([{"savings_rate_pct": None}]) is None


# --- savings goals (ported from the Go tests) --------------------------------

TODAY = date(2026, 10, 20)


def goal(target="1200", target_date=None):
    return {"id": 1, "name": "Laptop", "target_amount": D(target), "target_date": target_date}


def test_goal_complete():
    g = a.goal_progress(goal(), D("1500"), date(2026, 1, 1), TODAY)
    assert g["pace"] == "complete" and g["remaining"] == 0 and g["percent_complete"] == 100


def test_goal_without_deadline():
    g = a.goal_progress(goal(), D("300"), date(2026, 10, 1), TODAY)
    assert g["pace"] == "none" and g["months_left"] is None and g["percent_complete"] == D("25.0")


def test_goal_deadline_but_no_contributions():
    g = a.goal_progress(goal(target_date=date(2027, 4, 1)), D("0"), None, TODAY)
    assert g["pace"] == "unknown" and g["months_left"] == 6 and g["required_per_month"] == D("200.00")


def test_goal_ahead_and_behind():
    # Funded since August (3 months counting October): 900 / 3 = 300 a month.
    ahead = a.goal_progress(goal("1500", date(2027, 1, 15)), D("900"), date(2026, 8, 5), TODAY)
    assert ahead["observed_per_month"] == D("300.00") and ahead["required_per_month"] == D("200.00")
    assert ahead["pace"] == "ahead"
    behind = a.goal_progress(goal("3000", date(2027, 1, 15)), D("900"), date(2026, 8, 5), TODAY)
    assert behind["pace"] == "behind"


def test_goal_past_deadline_owes_everything_now():
    g = a.goal_progress(goal(target_date=date(2026, 5, 1)), D("200"), date(2026, 1, 1), TODAY)
    assert g["months_left"] == 0 and g["required_per_month"] == D("1000") and g["pace"] == "behind"
