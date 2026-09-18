"""Integration tests for POST /v1/events — F1's entry point. Covers the
happy path (staged + a background job enqueued), the monthly event-limit
enforcement, and the "Redis isn't configured yet" 503 rather than a
silent drop or an unhandled exception."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import WorkspaceKeyAuth, get_api_key_auth

WORKSPACE_ID = "ws-1"

EVENT_PAYLOAD = {
    "agent_name": "billing-bot",
    "action_type": "external",
    "action_name": "send_refund",
    "inputs": {"amount": 49.99},
}


class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, table, op, payload=None, count_mode=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.count_mode = count_mode
        self.filters = {}
        self.gte_filters = {}
        self._single = False

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def gte(self, field, value):
        self.gte_filters[field] = value
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            row = {"id": f"row-{len(rows) + 1}", "created_at": datetime.now(timezone.utc).isoformat(), **self.payload}
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if all(r.get(k) == v for k, v in self.filters.items())]
        for field, bound in self.gte_filters.items():
            matches = [r for r in matches if r.get(field, "") >= bound]

        if self.count_mode == "exact":
            return _FakeResult(matches, count=len(matches))
        if self._single:
            return _FakeResult(matches[0] if matches else None)
        return _FakeResult(matches)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **kw):
        return _FakeQuery(self, "select", count_mode=kw.get("count"))

    def insert(self, payload):
        return _FakeQuery(self, "insert", payload)


class _FakeDb:
    def __init__(self, plan="starter"):
        self._tables = {
            "workspaces": {WORKSPACE_ID: {"id": WORKSPACE_ID, "plan": plan}},
            "events": {},
            "event_intake": {},
        }

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args):
        self.enqueued.append((name, args))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.ingest.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_api_key_auth] = lambda: WorkspaceKeyAuth(workspace_id=WORKSPACE_ID, api_key_id="key-1")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_ingest_accepts_and_enqueues_a_job(client, monkeypatch):
    pool = _FakeArqPool()

    async def _get_pool():
        return pool

    monkeypatch.setattr("app.routers.ingest.get_arq_pool", _get_pool)

    resp = client.post("/v1/events", json=EVENT_PAYLOAD, headers={"Authorization": "Bearer al_live_test"})

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["accepted"] is True
    assert pool.enqueued == [("process_event_intake", (body["intake_id"],))]


def test_ingest_returns_503_when_redis_is_not_configured(client, monkeypatch):
    async def _get_pool():
        return None

    monkeypatch.setattr("app.routers.ingest.get_arq_pool", _get_pool)

    resp = client.post("/v1/events", json=EVENT_PAYLOAD, headers={"Authorization": "Bearer al_live_test"})

    assert resp.status_code == 503


def test_ingest_blocked_once_monthly_event_limit_reached(client, fake_db, monkeypatch):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "free"  # limit of 2,500
    now = datetime.now(timezone.utc)
    for i in range(2500):
        fake_db._tables["events"][f"evt-{i}"] = {
            "id": f"evt-{i}",
            "workspace_id": WORKSPACE_ID,
            "created_at": now.isoformat(),
        }

    async def _get_pool():
        return _FakeArqPool()

    monkeypatch.setattr("app.routers.ingest.get_arq_pool", _get_pool)

    resp = client.post("/v1/events", json=EVENT_PAYLOAD, headers={"Authorization": "Bearer al_live_test"})

    assert resp.status_code == 402
    assert "limit" in resp.json()["detail"].lower()


def test_ingest_ignores_events_from_before_this_month_for_the_limit(client, fake_db, monkeypatch):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "free"
    last_month = datetime.now(timezone.utc) - timedelta(days=40)
    # More than the free limit (2,500): only meaningful proof that old
    # events are excluded if this many would otherwise trip it.
    for i in range(3000):
        fake_db._tables["events"][f"evt-{i}"] = {
            "id": f"evt-{i}",
            "workspace_id": WORKSPACE_ID,
            "created_at": last_month.isoformat(),
        }
    pool = _FakeArqPool()

    async def _get_pool():
        return pool

    monkeypatch.setattr("app.routers.ingest.get_arq_pool", _get_pool)

    resp = client.post("/v1/events", json=EVENT_PAYLOAD, headers={"Authorization": "Bearer al_live_test"})

    assert resp.status_code == 202, resp.text


def test_ingest_requires_an_api_key(fake_db):
    with TestClient(app) as c:
        resp = c.post("/v1/events", json=EVENT_PAYLOAD)
    assert resp.status_code == 401
