"""Integration tests: the real SQL in database.py and sql/schema.sql against PostgreSQL.

Skipped unless TEST_DATABASE_URL is set. Point it at a disposable database
(a local PostgreSQL, or a separate Supabase project) — never production.

Safety: every run creates its own schema named ledger_test_<random>, builds
the tables there from sql/schema.sql, and drops only that schema at the end.
Nothing in the public schema is read or written. The run refuses to start if
TEST_DATABASE_URL equals DATABASE_URL.
"""

import os
import secrets
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from config import get_today
from database import PostgresRepository
from main import app
from tests.fakes import TODAY, register, tx

TEST_URL = os.getenv("TEST_DATABASE_URL")
SCHEMA_SQL = (Path(__file__).resolve().parents[2] / "sql" / "schema.sql").read_text(encoding="utf-8")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL not set"),
]


@pytest.fixture(scope="module")
def conninfo():
    if TEST_URL == os.getenv("LEDGER_APP_DATABASE_URL"):
        pytest.fail("TEST_DATABASE_URL must not be the application's DATABASE_URL")
    schema = f"ledger_test_{secrets.token_hex(4)}"
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(f"CREATE SCHEMA {schema}")
    scoped = make_conninfo(TEST_URL, options=f"-c search_path={schema}")
    try:
        with psycopg.connect(scoped, autocommit=True) as conn:
            conn.execute(SCHEMA_SQL)
        yield scoped
    finally:
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA {schema} CASCADE")


@pytest.fixture(scope="module")
def pg_repo(conninfo):
    repo = PostgresRepository(conninfo)
    repo.open()
    yield repo
    repo.close()


@pytest.fixture
def api(pg_repo, conninfo):
    """A logged-in client for a fresh account, on an emptied test schema."""
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("TRUNCATE users RESTART IDENTITY CASCADE")
    app.state.repo = pg_repo
    app.dependency_overrides[get_today] = lambda: TODAY
    client = TestClient(app)  # no `with`: the lifespan must not close our pool
    client.headers.update(register(client))
    client.uid = client.get("/api/auth/me").json()["id"]
    yield client
    app.dependency_overrides.clear()
    app.state.repo = None


@pytest.fixture
def other(api):
    client = TestClient(app)
    client.headers.update(register(client, name="Ravi Other", email="ravi@example.com"))
    client.uid = client.get("/api/auth/me").json()["id"]
    return client


def cat(api, name):
    return next(c["id"] for c in api.get("/api/categories").json() if c["name"] == name)


def sql(conninfo, statement, params=None):
    with psycopg.connect(conninfo, autocommit=True) as conn:
        return conn.execute(statement, params).fetchall()


# --- schema ------------------------------------------------------------------

def test_schema_is_rerunnable_without_touching_data(api, conninfo):
    count = "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM categories), (SELECT count(*) FROM settings)"
    before = sql(conninfo, count)
    assert before == [(1, 10, 1)]  # one account: its 10 default categories and settings row
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL)
    assert sql(conninfo, count) == before


def test_rls_enabled_on_every_table(conninfo):
    rows = sql(conninfo, """SELECT c.relname, c.relrowsecurity FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE n.nspname = current_schema() AND c.relkind = 'r'""")
    assert len(rows) == 8 and all(enabled for _, enabled in rows)


@pytest.mark.parametrize("statement", [
    "INSERT INTO transactions (user_id, type, amount, category_id, date) VALUES ({uid}, 'expense', 0, {food}, '2026-10-01')",
    "INSERT INTO transactions (user_id, type, amount, category_id, date) VALUES ({uid}, 'expense', -1, {food}, '2026-10-01')",
    "INSERT INTO transactions (user_id, type, amount, category_id, date) VALUES ({uid}, 'refund', 1, {food}, '2026-10-01')",
    "INSERT INTO budgets (user_id, category_id, month, amount) VALUES ({uid}, {food}, '2026-10-15', 100)",
    "INSERT INTO budgets (user_id, category_id, month, amount) VALUES ({uid}, {food}, '2026-10-01', 0)",
    "INSERT INTO categories (user_id, name, type) VALUES ({uid}, '   ', 'expense')",
    "INSERT INTO users (name, email, password_hash) VALUES ('X', 'not-an-email', 'h')",
])
def test_database_constraints_reject_invalid_rows(api, conninfo, statement):
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(conninfo, statement.format(food=cat(api, "Food"), uid=api.uid))


def test_database_refuses_cross_account_links(api, other, conninfo):
    """Even bypassing the API, one account's rows cannot point at another's."""
    food = cat(api, "Food")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        sql(conninfo, "INSERT INTO transactions (user_id, type, amount, category_id, date) "
                      "VALUES (%s, 'expense', 1, %s, '2026-10-01')", (other.uid, food))
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        sql(conninfo, "INSERT INTO budgets (user_id, category_id, month, amount) "
                      "VALUES (%s, %s, '2026-10-01', 1)", (other.uid, food))
    goal = api.post("/api/goals", json={"name": "Trip", "target_amount": "100"}).json()["id"]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        sql(conninfo, "INSERT INTO contributions (user_id, goal_id, amount, date) "
                      "VALUES (%s, %s, 1, '2026-10-01')", (other.uid, goal))


def test_duplicate_email_rejected_by_database(api, conninfo):
    with pytest.raises(psycopg.errors.UniqueViolation):
        sql(conninfo, "INSERT INTO users (name, email, password_hash) VALUES ('X', 'ASHA@example.com', 'h')")


def test_accounts_and_sessions_over_real_sql(api, other, conninfo):
    assert api.post("/api/auth/register", json={"name": "Dup", "email": "Asha@example.com",
                                                "password": "correct horse battery"}).status_code == 409
    bad = TestClient(app).post("/api/auth/login", json={"email": "asha@example.com", "password": "nope-nope"})
    assert bad.status_code == 401
    # Stored token is a SHA-256 hex digest, never the token itself.
    token = api.headers["Authorization"].split()[1]
    hashes = [r[0] for r in sql(conninfo, "SELECT token_hash FROM sessions")]
    assert token not in hashes and all(len(h) == 64 for h in hashes)
    assert sql(conninfo, "SELECT count(*) FROM users WHERE password_hash LIKE 'scrypt$%%'") == [(2,)]
    # Isolation through the real queries.
    api.post("/api/transactions", json=tx(category_id=cat(api, "Food")))
    assert other.get("/api/transactions").json() == []
    assert other.get("/api/dashboard/summary?month=2026-10").json()["expenses"] == 0
    # An expired session stops working.
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 second' WHERE user_id = %s",
                     (other.uid,))
    assert other.get("/api/auth/me").status_code == 401
    # Logout removes the session row.
    assert api.post("/api/auth/logout").status_code == 204
    assert api.get("/api/auth/me").status_code == 401


def test_numeric_keeps_exact_cents(api, conninfo):
    food = cat(api, "Food")
    for amount in ("0.10", "0.20"):
        api.post("/api/transactions", json=tx(amount=amount, category_id=food))
    assert sql(conninfo, "SELECT sum(amount) FROM transactions") == [(Decimal("0.30"),)]
    assert api.get("/api/dashboard/summary?month=2026-10").json()["expenses"] == 0.3


# --- API over real SQL -------------------------------------------------------

def test_transaction_crud(api):
    food = cat(api, "Food")
    r = api.post("/api/transactions", json=tx(amount="249.50", category_id=food, description="Lunch"))
    assert r.status_code == 201
    t = r.json()
    assert (t["amount"], t["category"], t["date"]) == (249.5, "Food", "2026-10-05")
    r = api.put(f"/api/transactions/{t['id']}", json=tx(amount="10", category_id=food, on="2026-10-06"))
    assert r.status_code == 200 and r.json()["amount"] == 10
    assert api.delete(f"/api/transactions/{t['id']}").status_code == 204
    assert api.delete(f"/api/transactions/{t['id']}").status_code == 404
    assert api.put(f"/api/transactions/{t['id']}", json=tx(category_id=food)).status_code == 404


def test_month_filter_boundaries(api):
    food, salary = cat(api, "Food"), cat(api, "Salary")
    for on in ("2026-09-30", "2026-10-01", "2026-10-31"):
        api.post("/api/transactions", json=tx(amount="1", category_id=food, on=on))
    api.post("/api/transactions", json=tx("income", "1", salary, "2026-11-01"))
    dates = [t["date"] for t in api.get("/api/transactions?month=2026-10").json()]
    assert dates == ["2026-10-31", "2026-10-01"]


def test_category_type_enforced_by_database(api):
    r = api.post("/api/transactions", json=tx("expense", category_id=cat(api, "Salary")))
    assert r.status_code == 422 and "not an expense category" in r.json()["error"]
    assert api.post("/api/transactions", json=tx(category_id=999999)).status_code == 422
    # Changing only the type on update must also be refused.
    t = api.post("/api/transactions", json=tx(category_id=cat(api, "Food"))).json()
    assert api.put(f"/api/transactions/{t['id']}", json=tx("income", category_id=cat(api, "Food"))).status_code == 422


def test_budgets_unique_and_expense_only(api):
    food = cat(api, "Food")
    body = {"category_id": food, "month": "2026-10", "amount": "5000"}
    assert api.post("/api/budgets", json=body).status_code == 201
    r = api.post("/api/budgets", json=body)
    assert r.status_code == 409 and r.json()["error"] == "A budget for this category and month already exists"
    assert api.post("/api/budgets", json={**body, "category_id": cat(api, "Salary")}).status_code == 422
    assert api.get("/api/budgets?month=2026-10").json()[0]["month"] == "2026-10"


def test_category_delete_rules(api):
    used = api.post("/api/categories", json={"name": "it-used", "type": "expense"}).json()["id"]
    budgeted = api.post("/api/categories", json={"name": "it-budgeted", "type": "expense"}).json()["id"]
    api.post("/api/transactions", json=tx(category_id=used))
    api.post("/api/budgets", json={"category_id": budgeted, "month": "2026-10", "amount": "1"})
    assert api.delete(f"/api/categories/{used}").status_code == 409
    assert api.delete(f"/api/categories/{budgeted}").status_code == 204  # budget cascades
    assert api.get("/api/budgets").json() == []
    assert api.post("/api/categories", json={"name": "IT-USED", "type": "expense"}).status_code == 409


def test_summary_from_database(api):
    food, bills, salary = cat(api, "Food"), cat(api, "Bills"), cat(api, "Salary")
    api.post("/api/transactions", json=tx("income", "1000", salary, "2026-10-01"))
    api.post("/api/transactions", json=tx("expense", "850", food, "2026-10-02"))
    api.post("/api/transactions", json=tx("expense", "300", bills, "2026-10-03"))
    api.post("/api/transactions", json=tx("expense", "600", food, "2026-09-10"))
    api.post("/api/budgets", json={"category_id": food, "month": "2026-10", "amount": "1000"})
    api.post("/api/budgets", json={"category_id": bills, "month": "2026-10", "amount": "250"})
    s = api.get("/api/dashboard/summary?month=2026-10").json()
    assert (s["income"], s["expenses"], s["net_cash_flow"], s["savings_rate_pct"]) == (1000, 1150, -150, -15)
    assert {l["category"]: l["status"] for l in s["categories"]} == {"Food": "warning", "Bills": "exceeded"}
    assert s["forecast"] == [{"category_id": food, "category": "Food", "predicted": 600}]
    assert [r["code"] for r in s["risks"]][:2] == ["budget_exceeded", "negative_cash_flow"]
    monthly = api.get("/api/analytics/monthly?months=2").json()["months"]
    assert [(m["month"], m["expenses"]) for m in monthly] == [("2026-09", 600), ("2026-10", 1150)]


def test_goal_contributions_cascade(api, conninfo):
    g = api.post("/api/goals", json={"name": "Trip", "target_amount": "1000"}).json()
    api.post(f"/api/goals/{g['id']}/contributions", json={"amount": "250", "date": "2026-10-01"})
    assert api.get("/api/goals").json()[0]["saved"] == 250
    assert api.post("/api/goals/999999/contributions",
                    json={"amount": "1", "date": "2026-10-01"}).status_code == 404
    api.delete(f"/api/goals/{g['id']}")
    assert sql(conninfo, "SELECT count(*) FROM contributions") == [(0,)]


def test_settings_roundtrip(api):
    assert api.put("/api/settings", json={"savings_target": "7500.50"}).json() == {"savings_target": 7500.5}
    assert api.get("/api/settings").json() == {"savings_target": 7500.5}


def test_health_and_unreachable_database(api):
    assert api.get("/api/health").json() == {"status": "ok", "database": "ok"}
    dead = PostgresRepository("postgresql://nobody@127.0.0.1:1/none?connect_timeout=1", timeout=2)
    dead.open()
    try:
        app.state.repo = dead
        r = api.get("/api/transactions")
        assert r.status_code == 503 and r.json() == {"error": "Database unavailable"}
        assert api.get("/api/health").status_code == 503
    finally:
        dead.close()


def test_recovers_after_database_drops_idle_connections(api, pg_repo, conninfo):
    """Supabase's pooler closes idle connections; the next request must still work."""
    assert api.get("/api/transactions").status_code == 200
    with psycopg.connect(TEST_URL, autocommit=True) as admin:
        killed = admin.execute(
            "SELECT count(*) FROM (SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
            "AND application_name = '' AND state = 'idle') t").fetchone()[0]
    assert killed >= 1  # the pool's idle connection(s) really were dropped
    r = api.get("/api/transactions")
    assert r.status_code == 200, r.text
