import os

import pytest

# Unit tests must never reach a real database, whatever the shell has exported.
# Moved aside only so the integration tests can refuse to run against it.
if "DATABASE_URL" in os.environ:
    os.environ["LEDGER_APP_DATABASE_URL"] = os.environ.pop("DATABASE_URL")

from fastapi.testclient import TestClient  # noqa: E402

from config import get_today  # noqa: E402
from main import app  # noqa: E402
from tests.fakes import TODAY, FakeRepository, register  # noqa: E402


@pytest.fixture
def repo():
    return FakeRepository()


@pytest.fixture
def client(repo):
    """API client wired to the in-memory repository, a fixed 'today', and
    logged in as a freshly registered user (the repository's first user)."""
    app.state.repo = repo
    app.dependency_overrides[get_today] = lambda: TODAY
    with TestClient(app) as c:
        c.headers.update(register(c))
        yield c
    app.dependency_overrides.clear()
    app.state.repo = None


@pytest.fixture
def other(client):
    """A second, separate account on the same API and repository."""
    c = TestClient(app)
    c.headers.update(register(c, name="Ravi Other", email="ravi@example.com"))
    return c
