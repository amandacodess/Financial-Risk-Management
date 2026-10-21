"""Accounts, sessions, and isolation between users (in-memory repository)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import hash_password, token_hash, verify_password
from main import app
from tests.fakes import PASSWORD, tx

DATA_ENDPOINTS = [
    ("get", "/api/categories"), ("get", "/api/transactions"), ("post", "/api/transactions"),
    ("get", "/api/budgets"), ("post", "/api/budgets"), ("get", "/api/dashboard/summary"),
    ("get", "/api/risks"), ("get", "/api/analytics/monthly"), ("get", "/api/goals"),
    ("get", "/api/settings"), ("put", "/api/settings"), ("get", "/api/auth/me"),
]


# --- password hashing ----------------------------------------------------------

def test_password_hash_roundtrip_and_salting():
    h1, h2 = hash_password("s3cret-pass"), hash_password("s3cret-pass")
    assert h1.startswith("scrypt$") and h1 != h2  # random salt per hash
    assert "s3cret-pass" not in h1
    assert verify_password("s3cret-pass", h1) and not verify_password("wrong-pass", h1)


@pytest.mark.parametrize("stored", ["", "plain", "bcrypt$1$2$3$a$b", "scrypt$x$y$z$!!$!!"])
def test_malformed_hash_never_verifies(stored):
    assert verify_password("anything", stored) is False


# --- register / login / logout ----------------------------------------------------

def test_register_returns_token_and_user_without_password(client, repo):
    r = TestClient(app).post("/api/auth/register",
                             json={"name": " Meera ", "email": " Meera@Example.COM ", "password": PASSWORD})
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"token", "user"} and len(body["token"]) >= 40
    assert body["user"]["name"] == "Meera" and body["user"]["email"] == "meera@example.com"
    assert "password" not in r.text and "scrypt" not in r.text
    stored = next(u for u in repo.users.values() if u["email"] == "meera@example.com")
    assert stored["password_hash"].startswith("scrypt$")
    # Only the token's hash is kept server-side.
    assert body["token"] not in repo.sessions and token_hash(body["token"]) in repo.sessions


def test_new_account_gets_default_categories_and_settings(client):
    names = {c["name"] for c in client.get("/api/categories").json()}
    assert {"Food", "Bills", "Salary", "Freelance"} <= names
    assert client.get("/api/settings").json() == {"savings_target": 0}


def test_duplicate_email_is_409_case_insensitive(client):
    r = client.post("/api/auth/register",
                    json={"name": "Again", "email": "ASHA@example.com", "password": PASSWORD})
    assert r.status_code == 409 and r.json() == {"error": "An account with that email already exists"}


@pytest.mark.parametrize("body,field", [
    ({"name": "A", "email": "not-an-email", "password": PASSWORD}, "email"),
    ({"name": "A", "email": "a@b", "password": PASSWORD}, "email"),
    ({"name": "A", "email": "a@example.com", "password": "short"}, "password"),
    ({"name": "   ", "email": "a@example.com", "password": PASSWORD}, "name"),
    ({"email": "a@example.com", "password": PASSWORD}, "name"),
    ({"name": "A", "email": "a@example.com", "password": "x" * 129}, "password"),
])
def test_register_validation(client, body, field):
    r = TestClient(app).post("/api/auth/register", json=body)
    assert r.status_code == 422 and r.json()["error"].startswith(f"{field}:")


def test_login_success_and_me(client):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": "Asha@Example.com", "password": PASSWORD})
    assert r.status_code == 200
    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.status_code == 200 and me.json()["email"] == "asha@example.com"


@pytest.mark.parametrize("email,password", [
    ("asha@example.com", "wrong password"),
    ("nobody@example.com", PASSWORD),
])
def test_login_failure_gives_one_message_for_both_cases(client, email, password):
    r = TestClient(app).post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401 and r.json() == {"error": "Email or password is incorrect"}


def test_logout_ends_only_that_session(client):
    second = TestClient(app)
    token = second.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).json()["token"]
    second.headers["Authorization"] = f"Bearer {token}"
    assert second.post("/api/auth/logout").status_code == 204
    assert second.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 200  # the other session is untouched
    assert second.post("/api/auth/logout").status_code == 204  # idempotent


def test_expired_session_is_rejected(client, repo):
    for s in repo.sessions.values():
        s["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    r = client.get("/api/transactions")
    assert r.status_code == 401 and r.json() == {"error": "Please log in to continue"}


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc", "Bearer not-a-real-token"])
def test_missing_or_bad_token_is_401(client, header):
    c = TestClient(app)
    headers = {} if header is None else {"Authorization": header}
    assert c.get("/api/transactions", headers=headers).status_code == 401


@pytest.mark.parametrize("method,path", DATA_ENDPOINTS)
def test_every_data_endpoint_requires_login(client, method, path):
    r = getattr(TestClient(app), method)(path, **({"json": {}} if method in ("post", "put") else {}))
    assert r.status_code == 401


def test_health_stays_public(client):
    assert TestClient(app).get("/api/health").status_code == 200


# --- isolation between accounts --------------------------------------------------

def test_accounts_see_only_their_own_data(client, other, repo):
    food = repo.category_id("Food")
    mine = client.post("/api/transactions", json=tx(amount="250", category_id=food)).json()
    client.post("/api/budgets", json={"category_id": food, "month": "2026-10", "amount": "1000"})
    client.post("/api/goals", json={"name": "Laptop", "target_amount": "50000"})

    assert other.get("/api/transactions").json() == []
    assert other.get("/api/budgets").json() == []
    assert other.get("/api/goals").json() == []
    s = other.get("/api/dashboard/summary?month=2026-10").json()
    assert s["expenses"] == 0 and s["categories"] == [] and s["risks"] == []
    # Each account has its own copy of the default categories.
    assert {c["id"] for c in other.get("/api/categories").json()}.isdisjoint(
        {c["id"] for c in client.get("/api/categories").json()})
    assert client.get("/api/transactions").json()[0]["id"] == mine["id"]


def test_cannot_touch_another_accounts_records(client, other, repo):
    food = repo.category_id("Food")
    t = client.post("/api/transactions", json=tx(category_id=food)).json()
    b = client.post("/api/budgets", json={"category_id": food, "month": "2026-10", "amount": "1"}).json()
    g = client.post("/api/goals", json={"name": "Trip", "target_amount": "100"}).json()

    other_food = repo.category_id("Food", user_id=max(repo.users))
    assert other.put(f"/api/transactions/{t['id']}", json=tx(category_id=other_food)).status_code == 404
    assert other.delete(f"/api/transactions/{t['id']}").status_code == 404
    assert other.put(f"/api/budgets/{b['id']}", json={"amount": "5"}).status_code == 404
    assert other.delete(f"/api/budgets/{b['id']}").status_code == 404
    assert other.delete(f"/api/goals/{g['id']}").status_code == 404
    assert other.post(f"/api/goals/{g['id']}/contributions",
                      json={"amount": "1", "date": "2026-10-01"}).status_code == 404
    assert other.delete(f"/api/categories/{food}").status_code == 404
    # Nothing changed for the owner.
    assert client.get("/api/transactions").json()[0]["amount"] == 100
    assert client.get("/api/budgets").json()[0]["amount"] == 1


def test_cannot_file_under_another_accounts_category(client, other, repo):
    food = repo.category_id("Food")  # the first account's
    r = other.post("/api/transactions", json=tx(category_id=food))
    assert r.status_code == 422 and "does not exist" in r.json()["error"]
    r = other.post("/api/budgets", json={"category_id": food, "month": "2026-10", "amount": "1"})
    assert r.status_code == 422


def test_same_names_allowed_in_different_accounts(client, other):
    assert client.post("/api/categories", json={"name": "Rent", "type": "expense"}).status_code == 201
    assert other.post("/api/categories", json={"name": "Rent", "type": "expense"}).status_code == 201
    assert client.post("/api/goals", json={"name": "Car", "target_amount": "1"}).status_code == 201
    assert other.post("/api/goals", json={"name": "Car", "target_amount": "1"}).status_code == 201


def test_settings_are_per_account(client, other):
    client.put("/api/settings", json={"savings_target": "9000"})
    assert other.get("/api/settings").json() == {"savings_target": 0}
