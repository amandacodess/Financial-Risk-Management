"""Transactions and categories through the HTTP API (in-memory repository)."""

import pytest

from tests.fakes import tx


def test_create_list_update_delete(client, repo):
    food = repo.category_id("Food")

    r = client.post("/api/transactions", json=tx(amount="249.50", category_id=food, description="Lunch"))
    assert r.status_code == 201
    created = r.json()
    assert created == {"id": created["id"], "type": "expense", "amount": 249.5, "category_id": food,
                       "category": "Food", "date": "2026-10-05", "description": "Lunch"}
    assert isinstance(created["amount"], float)  # a JSON number, not a string

    listed = client.get("/api/transactions").json()
    assert [t["id"] for t in listed] == [created["id"]]

    r = client.put(f"/api/transactions/{created['id']}",
                   json=tx(amount="300", category_id=food, on="2026-10-06", description="Dinner"))
    assert r.status_code == 200
    assert r.json()["amount"] == 300 and r.json()["description"] == "Dinner"

    assert client.delete(f"/api/transactions/{created['id']}").status_code == 204
    assert client.get("/api/transactions").json() == []


def test_list_filters_by_month_type_and_category(client, repo):
    food, bills, salary = (repo.category_id(n) for n in ("Food", "Bills", "Salary"))
    client.post("/api/transactions", json=tx("expense", "10", food, "2026-09-30"))   # last day of Sept
    client.post("/api/transactions", json=tx("expense", "20", food, "2026-10-01"))   # first day of Oct
    client.post("/api/transactions", json=tx("expense", "30", bills, "2026-10-31"))  # last day of Oct
    client.post("/api/transactions", json=tx("income", "40", salary, "2026-11-01"))  # first day of Nov

    def amounts(query):
        return [t["amount"] for t in client.get(f"/api/transactions?{query}").json()]

    assert amounts("month=2026-10") == [30, 20]  # newest first; boundaries excluded
    assert amounts("month=2026-10&category_id=%d" % food) == [20]
    assert amounts("type=income") == [40]
    assert amounts("month=2026-12") == []


def test_income_uses_income_category(client, repo):
    r = client.post("/api/transactions", json=tx("income", "50000", repo.category_id("Salary")))
    assert r.status_code == 201 and r.json()["category"] == "Salary"


@pytest.mark.parametrize("amount", ["0", "-5", "0.001", "abc", None, "1e12", "NaN", "Infinity"])
def test_invalid_amounts_rejected(client, repo, amount):
    r = client.post("/api/transactions", json=tx(amount=amount, category_id=repo.category_id("Food")))
    assert r.status_code == 422
    assert r.json()["error"].startswith("amount:")


@pytest.mark.parametrize("type", ["transfer", "EXPENSE", "", None])
def test_invalid_type_rejected(client, repo, type):
    r = client.post("/api/transactions", json=tx(type=type, category_id=repo.category_id("Food")))
    assert r.status_code == 422 and r.json()["error"].startswith("type:")


@pytest.mark.parametrize("on", ["2026-02-30", "2026-13-01", "05/10/2026", "", 1700000000, "2026-10-05T10:00:00"])
def test_malformed_dates_rejected(client, repo, on):
    r = client.post("/api/transactions", json=tx(category_id=repo.category_id("Food"), on=on))
    assert r.status_code == 422 and r.json()["error"].startswith("date:")


def test_unknown_field_rejected(client, repo):
    body = {**tx(category_id=repo.category_id("Food")), "ammount": "5"}
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 422 and "ammount" in r.json()["error"]


def test_description_too_long(client, repo):
    r = client.post("/api/transactions", json=tx(category_id=repo.category_id("Food"), description="x" * 201))
    assert r.status_code == 422


def test_malformed_json(client):
    r = client.post("/api/transactions", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"] == "Request body is not valid JSON"


def test_missing_category_reference(client):
    r = client.post("/api/transactions", json=tx(category_id=99999))
    assert r.status_code == 422
    assert r.json()["error"] == "category_id does not exist or is not an expense category"


def test_category_type_must_match(client, repo):
    r = client.post("/api/transactions", json=tx("expense", category_id=repo.category_id("Salary")))
    assert r.status_code == 422 and "not an expense category" in r.json()["error"]


@pytest.mark.parametrize("method", ["put", "delete"])
def test_missing_transaction_is_404(client, repo, method):
    kwargs = {"json": tx(category_id=repo.category_id("Food"))} if method == "put" else {}
    r = getattr(client, method)("/api/transactions/424242", **kwargs)
    assert r.status_code == 404 and r.json() == {"error": "Transaction not found"}


def test_non_numeric_id_is_422(client):
    assert client.delete("/api/transactions/abc").status_code == 422


# --- categories --------------------------------------------------------------

def test_categories_list_with_usage(client, repo):
    food = repo.category_id("Food")
    client.post("/api/transactions", json=tx(category_id=food))
    cats = {c["name"]: c for c in client.get("/api/categories").json()}
    assert cats["Food"]["transaction_count"] == 1 and cats["Salary"]["type"] == "income"
    assert {c["type"] for c in client.get("/api/categories?type=income").json()} == {"income"}


def test_category_create_and_duplicate(client):
    r = client.post("/api/categories", json={"name": "  Rent ", "type": "expense"})
    assert r.status_code == 201 and r.json()["name"] == "Rent"
    dup = client.post("/api/categories", json={"name": "rent", "type": "expense"})
    assert dup.status_code == 409
    # The same name is allowed for the other type.
    assert client.post("/api/categories", json={"name": "Rent", "type": "income"}).status_code == 201


def test_category_delete_blocked_while_in_use(client, repo):
    food = repo.category_id("Food")
    created = client.post("/api/transactions", json=tx(category_id=food)).json()
    r = client.delete(f"/api/categories/{food}")
    assert r.status_code == 409 and r.json()["error"] == "Category is used by existing transactions"
    client.delete(f"/api/transactions/{created['id']}")
    assert client.delete(f"/api/categories/{food}").status_code == 204
    assert client.delete(f"/api/categories/{food}").status_code == 404


def test_blank_category_name_rejected(client):
    assert client.post("/api/categories", json={"name": "   ", "type": "expense"}).status_code == 422
