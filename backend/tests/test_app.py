"""Cross-cutting behaviour: health, failure handling, error shape, CORS, read-only mode, goals."""

import pytest
from fastapi.testclient import TestClient

from config import get_config, get_today
from main import app
from tests.fakes import TODAY, BrokenRepository, DownRepository


@pytest.fixture
def client_with(request):
    """TestClient around whatever repository the test passes in."""
    clients = []

    def make(repo, raise_server_exceptions=True):
        app.state.repo = repo
        app.dependency_overrides[get_today] = lambda: TODAY
        # A token, so requests get past the login check and reach the repository.
        c = TestClient(app, raise_server_exceptions=raise_server_exceptions,
                       headers={"Authorization": "Bearer some-token"})
        clients.append(c)
        return c

    yield make
    app.dependency_overrides.clear()
    app.state.repo = None


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "database": "ok"}


def test_health_reports_database_down(client_with):
    r = client_with(DownRepository()).get("/api/health")
    assert r.status_code == 503 and r.json()["database"] == "unavailable"


def test_health_without_database_configured(client_with):
    r = client_with(None).get("/api/health")
    assert r.status_code == 503


def test_database_down_returns_503_not_a_crash(client_with):
    c = client_with(DownRepository())
    for url in ("/api/transactions", "/api/dashboard/summary", "/api/budgets", "/api/risks"):
        r = c.get(url)
        assert r.status_code == 503 and r.json() == {"error": "Database unavailable"}


def test_unconfigured_database_returns_503(client_with):
    r = client_with(None).get("/api/transactions")
    assert r.status_code == 503 and "DATABASE_URL" in r.json()["error"]


def test_unexpected_error_does_not_leak_details(client_with):
    r = client_with(BrokenRepository(), raise_server_exceptions=False).get("/api/transactions")
    assert r.status_code == 500
    assert r.json() == {"error": "Internal server error"}
    assert "FAKE-NOT-A-SECRET" not in r.text and "Traceback" not in r.text


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"error": "Not Found"}


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/transactions", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/transactions", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_read_only_mode_blocks_writes(client, repo, monkeypatch):
    monkeypatch.setenv("ALLOW_WRITES", "false")
    get_config.cache_clear()
    try:
        r = client.post("/api/categories", json={"name": "X", "type": "expense"})
        assert r.status_code == 403 and r.json() == {"error": "This deployment is read-only"}
        assert client.get("/api/categories").status_code == 200
    finally:
        monkeypatch.delenv("ALLOW_WRITES")
        get_config.cache_clear()


# --- savings goals and settings ---------------------------------------------

def test_goal_lifecycle(client):
    r = client.post("/api/goals", json={"name": "Laptop", "target_amount": "60000",
                                        "target_date": "2027-04-01"})
    assert r.status_code == 201
    g = r.json()
    assert g["pace"] == "unknown" and g["months_left"] == 6 and g["required_per_month"] == 10000

    r = client.post(f"/api/goals/{g['id']}/contributions",
                    json={"amount": "15000", "date": "2026-10-01"})
    assert r.status_code == 201 and r.json()["amount"] == 15000

    [listed] = client.get("/api/goals").json()
    assert listed["saved"] == 15000 and listed["percent_complete"] == 25 and listed["pace"] == "ahead"

    assert client.post("/api/goals", json={"name": "laptop", "target_amount": "1"}).status_code == 409
    assert client.delete(f"/api/goals/{g['id']}").status_code == 204
    assert client.get("/api/goals").json() == []


def test_contribution_to_missing_goal(client):
    r = client.post("/api/goals/999/contributions", json={"amount": "1", "date": "2026-10-01"})
    assert r.status_code == 404 and r.json() == {"error": "Goal not found"}


def test_settings(client):
    assert client.get("/api/settings").json() == {"savings_target": 0}
    assert client.put("/api/settings", json={"savings_target": "5000"}).json() == {"savings_target": 5000}
    assert client.put("/api/settings", json={"savings_target": "-1"}).status_code == 422
