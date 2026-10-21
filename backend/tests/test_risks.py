"""Risk engine rules, directly and through /api/risks and /api/dashboard/summary."""

from datetime import date
from decimal import Decimal as D

import pytest

from services import analytics as a
from services.risk_engine import assess
from tests.fakes import tx

W, X = D(80), D(100)
MONTH = date(2026, 10, 1)


def run(income, spent_by_cat: dict, budgets: dict, today=date(2026, 10, 31), current=True):
    """Build the inputs the dashboard would and return the risk codes."""
    expenses = sum((D(v) for v in spent_by_cat.values()), D(0))
    fig = a.figures(D(income), expenses)
    spent = {cid: {"category": f"c{cid}", "amount": D(v)} for cid, v in spent_by_cat.items()}
    blist = [{"category_id": cid, "category": f"c{cid}", "amount": D(v)} for cid, v in budgets.items()]
    lines = a.budget_lines(blist, spent, W, X)
    total = sum((b["amount"] for b in blist), D(0))
    return assess(fig, lines, a.pace(expenses, MONTH, today), total, current)


def codes(risks):
    return [r["code"] for r in risks]


@pytest.mark.parametrize("spent,expected", [
    ("0", []),
    ("79.99", []),
    ("80", ["budget_warning"]),
    ("100", ["budget_warning"]),
    ("100.01", ["budget_exceeded"]),
    ("250", ["budget_exceeded"]),
])
def test_category_budget_rules(spent, expected):
    assert codes(run("10000", {1: spent}, {1: "100"})) == expected


def test_negative_cash_flow():
    risks = run("1000", {1: "1500"}, {})
    assert codes(risks) == ["negative_cash_flow"]
    assert risks[0]["severity"] == "critical" and risks[0]["value"] == D("-500")


def test_zero_income_with_spending_is_negative_cash_flow():
    [risk] = run("0", {1: "50"}, {})
    assert risk["code"] == "negative_cash_flow"
    assert "no income" in risk["message"]


def test_break_even_is_not_negative():
    assert run("500", {1: "500"}, {}) == []


def test_empty_month_has_no_risks_and_no_errors():
    assert run("0", {}, {}) == []


def test_zero_income_and_budget_but_no_spending():
    assert run("0", {}, {1: "100"}) == []


def test_projected_overspend_only_in_current_month():
    # Day 10 of 31 with 400 of a 1000 budget spent -> projects to 1240.
    mid_month = date(2026, 10, 10)
    assert "projected_overspend" in codes(run("5000", {1: "400"}, {1: "1000"}, today=mid_month))
    assert "projected_overspend" not in codes(
        run("5000", {1: "400"}, {1: "1000"}, today=mid_month, current=False))


def test_projected_overspend_not_repeated_once_already_over():
    risks = run("5000", {1: "1200"}, {1: "1000"}, today=date(2026, 10, 10))
    assert codes(risks) == ["budget_exceeded"]


def test_critical_risks_come_first():
    risks = run("100", {1: "85", 2: "300"}, {1: "100", 2: "200"})
    assert [r["severity"] for r in risks] == ["critical", "critical", "warning"]


def test_thresholds_are_configurable():
    fig = a.figures(D("1000"), D("60"))
    lines = a.budget_lines([{"category_id": 1, "category": "c", "amount": D("100")}],
                           {1: {"category": "c", "amount": D("60")}}, D(50), D(100))
    assert codes(assess(fig, lines, a.pace(D("60"), MONTH, date(2026, 10, 31)), D("100"), True)) \
        == ["budget_warning"]


# --- through the API ---------------------------------------------------------

def seed_month(client, repo):
    food, bills, salary = (repo.category_id(n) for n in ("Food", "Bills", "Salary"))
    client.post("/api/transactions", json=tx("income", "1000", salary, "2026-10-01"))
    client.post("/api/transactions", json=tx("expense", "850", food, "2026-10-02"))
    client.post("/api/transactions", json=tx("expense", "300", bills, "2026-10-03"))
    client.post("/api/budgets", json={"category_id": food, "month": "2026-10", "amount": "1000"})
    client.post("/api/budgets", json={"category_id": bills, "month": "2026-10", "amount": "250"})
    return food, bills


def test_summary_figures(client, repo):
    food, bills = seed_month(client, repo)
    s = client.get("/api/dashboard/summary?month=2026-10").json()
    assert (s["income"], s["expenses"], s["net_cash_flow"]) == (1000, 1150, -150)
    assert s["savings_rate_pct"] == -15
    assert s["budget_total"] == 1250 and s["budget_utilization_pct"] == 92
    lines = {l["category"]: l for l in s["categories"]}
    assert lines["Food"]["utilization_pct"] == 85 and lines["Food"]["status"] == "warning"
    assert lines["Bills"]["status"] == "exceeded" and lines["Bills"]["remaining"] == -50
    assert s["pace"] == {"days_elapsed": 20, "days_in_month": 31, "projected_expenses": 1782.5}
    assert codes(s["risks"]) == ["budget_exceeded", "negative_cash_flow", "budget_warning",
                                "projected_overspend"]


def test_summary_defaults_to_current_month(client):
    assert client.get("/api/dashboard/summary").json()["month"] == "2026-10"


def test_summary_empty_month(client):
    s = client.get("/api/dashboard/summary?month=2020-01").json()
    assert s["income"] == 0 and s["expenses"] == 0 and s["net_cash_flow"] == 0
    assert s["savings_rate_pct"] is None and s["budget_utilization_pct"] is None
    assert s["categories"] == [] and s["forecast"] == [] and s["risks"] == []


def test_summary_forecast_uses_previous_months(client, repo):
    food = repo.category_id("Food")
    client.post("/api/transactions", json=tx("expense", "300", food, "2026-09-15"))
    client.post("/api/transactions", json=tx("expense", "500", food, "2026-10-01"))
    s = client.get("/api/dashboard/summary?month=2026-10").json()
    assert s["forecast"] == [{"category_id": food, "category": "Food", "predicted": 300}]


def test_risks_endpoint(client, repo):
    seed_month(client, repo)
    r = client.get("/api/risks?month=2026-10").json()
    assert r["month"] == "2026-10"
    assert codes(r["risks"]) == ["budget_exceeded", "negative_cash_flow", "budget_warning",
                                "projected_overspend"]
    assert all(isinstance(x["message"], str) and x["message"] for x in r["risks"])


@pytest.mark.parametrize("url", ["/api/risks?month=2026-13", "/api/dashboard/summary?month=oct",
                                 "/api/analytics/monthly?end=2026-1"])
def test_malformed_month_is_422(client, url):
    r = client.get(url)
    assert r.status_code == 422 and r.json()["error"] == "month must be in YYYY-MM format"


def test_monthly_analytics(client, repo):
    salary, food = repo.category_id("Salary"), repo.category_id("Food")
    client.post("/api/transactions", json=tx("income", "2000", salary, "2026-09-30"))
    client.post("/api/transactions", json=tx("expense", "500", food, "2026-10-01"))
    body = client.get("/api/analytics/monthly?months=3").json()
    assert [m["month"] for m in body["months"]] == ["2026-08", "2026-09", "2026-10"]
    sep, oct_ = body["months"][1], body["months"][2]
    assert (sep["income"], sep["expenses"], sep["savings_rate_pct"]) == (2000, 0, 100)
    assert (oct_["net_cash_flow"], oct_["savings_rate_pct"]) == (-500, None)
    assert body["average_savings_rate_pct"] == 100


@pytest.mark.parametrize("months", [0, 25, -1])
def test_monthly_analytics_rejects_bad_range(client, months):
    assert client.get(f"/api/analytics/monthly?months={months}").status_code == 422


def test_exceeded_message_states_the_overage_not_a_rounded_percent():
    [risk] = run("10000", {1: "2000.01"}, {1: "2000"})
    assert risk["code"] == "budget_exceeded"
    assert "over budget by ₹0.01" in risk["message"] and "100.0%" not in risk["message"]
