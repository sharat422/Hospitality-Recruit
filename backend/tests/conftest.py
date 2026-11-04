"""
Shared test fixtures for the HospRecruit backend test suite.

Strategy
--------
We override FastAPI's dependency injection for every test so that:
  - `get_supabase_client` returns a controllable `MockSupabase` instance.
  - `get_current_user`    returns a hardcoded user dict.

MockSupabase mimics the Supabase Python client's fluent query-builder
interface.  Each call to `.table(name)` returns a fresh `TableChain` whose
`.execute()` result can be configured per table in the fixture.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.dependencies import get_supabase_admin_client, get_supabase_client
from app.core.security import get_current_user

# ---------------------------------------------------------------------------
# Fixed test IDs
# ---------------------------------------------------------------------------

EMPLOYEE_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
ADMIN_ID    = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER_ID    = "ffffffff-ffff-ffff-ffff-ffffffffffff"


# ---------------------------------------------------------------------------
# Minimal Supabase fluent-builder mock
# ---------------------------------------------------------------------------

class _ExecuteResult:
    """Mimics the object returned by supabase's .execute()."""
    def __init__(self, data: list[dict], count: int | None = None):
        self.data  = data
        self.count = count if count is not None else len(data)


class TableChain:
    """
    Fluent builder that always returns itself until .execute() is called.
    Holds a *reference* to the shared results list in MockSupabase so that
    successive calls to .table(same_name) all advance the same pointer.
    """
    def __init__(self, results_ref: list[list[dict]]):
        self._results = results_ref  # shared reference — intentionally NOT a copy

    # All builder methods return self so any chaining works.
    def select(self, *a, **kw):  return self
    def eq(self, *a, **kw):      return self
    def neq(self, *a, **kw):     return self
    def ilike(self, *a, **kw):   return self
    def is_(self, *a, **kw):     return self
    def limit(self, *a, **kw):   return self
    def update(self, *a, **kw):  return self
    def insert(self, *a, **kw):  return self
    def delete(self, *a, **kw):  return self
    def upsert(self, *a, **kw):  return self
    @property
    def not_(self):              return self
    def order(self, *a, **kw):   return self
    def in_(self, *a, **kw):     return self
    def gte(self, *a, **kw):     return self
    def lte(self, *a, **kw):     return self
    def lt(self, *a, **kw):      return self
    def or_(self, *a, **kw):     return self

    def execute(self):
        data = self._results.pop(0) if self._results else []
        return _ExecuteResult(data)


class MockSupabase:
    """
    Lightweight Supabase client mock.

    Usage::

        sb = MockSupabase()
        sb.configure("users", [{"id": EMPLOYEE_ID, "role": "hiring_manager"}])
        sb.configure("employee_upi_details", [])  # no existing record
        # ...then pass sb as the get_supabase_client override
    """
    def __init__(self):
        self._table_results: dict[str, list[list[dict]]] = {}

    def configure(self, table: str, *call_results: list[dict]) -> "MockSupabase":
        """
        Set the ordered responses for successive .execute() calls on `table`.
        Each positional arg after `table` is the `data` list for one call.

        Example::

            sb.configure("employee_upi_details",
                         [],            # first execute() → no existing row
                         [{"id": "x"}]) # second execute() → inserted row
        """
        self._table_results[table] = list(call_results)
        return self

    def table(self, name: str) -> TableChain:
        if name not in self._table_results:
            self._table_results[name] = [[]]
        return TableChain(self._table_results[name])  # pass the live list, not a copy


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

def _make_client(user_payload: dict, supabase: MockSupabase) -> TestClient:
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    app.dependency_overrides[get_supabase_admin_client] = lambda: supabase
    app.dependency_overrides[get_current_user]    = lambda: user_payload
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    app.dependency_overrides.clear()


@pytest.fixture
def employee_user():
    return {"sub": EMPLOYEE_ID, "email": "emp@hotel.in"}


@pytest.fixture
def admin_user():
    return {"sub": ADMIN_ID, "email": "admin@hotel.in"}


@pytest.fixture
def other_user():
    return {"sub": OTHER_ID, "email": "other@hotel.in"}


@pytest.fixture
def mock_supabase():
    return MockSupabase()


@pytest.fixture
def client_as_employee(employee_user, mock_supabase):
    c = _make_client(employee_user, mock_supabase)
    yield c, mock_supabase
    _clear()


@pytest.fixture
def client_as_admin(admin_user, mock_supabase):
    c = _make_client(admin_user, mock_supabase)
    yield c, mock_supabase
    _clear()


@pytest.fixture
def client_as_other(other_user, mock_supabase):
    c = _make_client(other_user, mock_supabase)
    yield c, mock_supabase
    _clear()
