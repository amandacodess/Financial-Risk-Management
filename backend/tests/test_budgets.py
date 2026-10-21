"""Budgets through the HTTP API (in-memory repository)."""

import pytest


def make(client, category_id, month="2026-10", amount="5000"):
    return client.post("/api/budgets", json={"category_id": category_id, "month": month, "amount": amount})


def test_create_list_update_delete(client, repo):
    food = repo.category_id("Food")
    r = make(client, food)
    assert r.status_code == 201
    b = r.json()
    assert b == {"id": b["id"], "category_id": food, "category": "Food", "month": "2026-10", "amount": 5000}

    make(client, food, month="2026-11")
    assert [x["month"] for x in client.get("/api/budgets?month=2026-10").json()] == ["2026-10"]
    assert len(client.get("/api/budgets").json()) == 2

    r = client.put(f"/api/budgets/{b['id']}", json={"amount": "6500.25"})
    assert r.status_code == 200 and r.json()["amount"] == 6500.25

    assert client.delete(f"/api/budgets/{b['id']}").status_code == 204
    assert client.get("/api/budgets?month=2026-10").json() == []


def test_duplicate_budget_same_category_and_month(client, repo):
    food = repo.category_id("Food")
    assert make(client, food).status_code == 201
    r = make(client, food, amount="1")
    assert r.status_code == 409
    assert r.json() == {"error": "A budget for this category and month already exists"}
    # A different month or category is fine.
    assert make(client, food, month="2026-11").status_code == 201
    assert make(client, repo.category_id("Bills")).status_code == 201


def test_budget_requires_existing_expense_category(client, repo):
    assert make(client, 99999).status_code == 422
    r = make(client, repo.category_id("Salary"))
    assert r.status_code == 422
    assert r.json()["error"] == "category_id does not exist or is not an expense category"


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "2026-10-01", "October", ""])
def test_budget_month_format(client, repo, month):
    r = make(client, repo.category_id("Food"), month=month)
    assert r.status_code == 422 and r.json()["error"] == "month: month must be in YYYY-MM format"


@pytest.mark.parametrize("amount", ["0", "-100", "12.345"])
def test_budget_amount_validation(client, repo, amount):
    assert make(client, repo.category_id("Food"), amount=amount).status_code == 422


def test_missing_budget_is_404(client):
    assert client.put("/api/budgets/777", json={"amount": "1"}).status_code == 404
    assert client.delete("/api/budgets/777").status_code == 404


def test_deleting_category_removes_its_budgets(client, repo):
    food = repo.category_id("Food")
    make(client, food)
    assert client.delete(f"/api/categories/{food}").status_code == 204
    assert client.get("/api/budgets").json() == []
