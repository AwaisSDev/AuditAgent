"""Integration tests for the agents + API keys routers through the real
FastAPI app — plan-limit enforcement on agent creation, and the full API
key lifecycle (create once, list without secrets, revoke)."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, require_workspace_member

WORKSPACE_ID = "ws-1"


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

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def single(self):
        self._single = True
        return self

    def order(self, *_a, **_kw):
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            # Mirrors supabase/schema.sql's defaults for these two tables —
            # a real insert wouldn't require the caller to supply them.
            row = {
                "id": f"row-{len(rows) + 1}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_active": True,
                "last_used_at": None,
                "revoked_at": None,
                **self.payload,
            }
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if all(r.get(k) == v for k, v in self.filters.items())]

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        if self.count_mode == "exact":
            return _FakeResult(matches, count=len(matches))
        if getattr(self, "_single", False):
            return _FakeResult(matches[0] if matches else None)
        return _FakeResult(matches)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **kw):
        return _FakeQuery(self, "select", count_mode=kw.get("count"))

    def insert(self, payload):
        return _FakeQuery(self, "insert", payload)

    def update(self, payload):
        return _FakeQuery(self, "update", payload)


class _FakeDb:
    def __init__(self, plan="starter"):
        self._tables = {
            "agents": {},
            "api_keys": {},
            "workspaces": {WORKSPACE_ID: {"id": WORKSPACE_ID, "plan": plan}},
        }

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.agents.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="owner@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_and_list_agent(client):
    resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/agents", json={"name": "billing-bot", "description": "handles refunds"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["name"] == "billing-bot"

    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_agent_creation_blocked_once_plan_limit_reached(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "free"  # limit of 1
    resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/agents", json={"name": "first-bot"})
    assert resp.status_code == 201

    resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/agents", json={"name": "second-bot"})
    assert resp.status_code == 402
    assert "limit" in resp.json()["detail"].lower()


def test_unlimited_plan_allows_many_agents(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "enterprise"  # unlimited
    for i in range(3):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/agents", json={"name": f"bot-{i}"})
        assert resp.status_code == 201


def test_api_key_lifecycle(client):
    resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/api-keys", json={"name": "prod-key"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["full_key"].startswith("al_")
    key_id = body["id"]

    # The list endpoint must never expose the full key or its hash.
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/api-keys")
    assert resp.status_code == 200
    listed = resp.json()[0]
    assert "full_key" not in listed
    assert "key_hash" not in listed
    assert listed["key_prefix"] == body["key_prefix"]

    resp = client.delete(f"/v1/workspaces/{WORKSPACE_ID}/api-keys/{key_id}")
    assert resp.status_code == 204
