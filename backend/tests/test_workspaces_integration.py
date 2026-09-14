"""Integration tests for the workspaces router: creation (which atomically
seeds a membership + default policy in one request), duplicate-name
slugging, and settings updates — through the real FastAPI app."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, get_current_user, require_workspace_member

USER_ID = "user-1"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table, op, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters = {}
        self.in_filter = None
        self._single = False

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def in_(self, field, values):
        self.in_filter = (field, set(values))
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            row = {"id": f"row-{len(rows) + 1}", "created_at": datetime.now(timezone.utc).isoformat(), "plan": "free", **self.payload}
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if all(r.get(k) == v for k, v in self.filters.items())]
        if self.in_filter:
            field, values = self.in_filter
            matches = [r for r in matches if r.get(field) in values]

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        if self._single:
            return _FakeResult(matches[0] if matches else None)
        return _FakeResult(matches)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_kw):
        return _FakeQuery(self, "select")

    def insert(self, payload):
        return _FakeQuery(self, "insert", payload)

    def update(self, payload):
        return _FakeQuery(self, "update", payload)


class _FakeDb:
    def __init__(self):
        self._tables = {"workspaces": {}, "workspace_members": {}, "policies": {}}

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.workspaces.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER_ID, email="owner@example.com")
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id=USER_ID, email="owner@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_workspace_seeds_membership_and_default_policy(client, fake_db):
    resp = client.post("/v1/workspaces", json={"name": "Acme Inc"})
    assert resp.status_code == 201, resp.text
    ws = resp.json()
    assert ws["slug"] == "acme-inc"

    members = list(fake_db._tables["workspace_members"].values())
    assert len(members) == 1
    assert members[0]["workspace_id"] == ws["id"]
    assert members[0]["user_id"] == USER_ID
    assert members[0]["role"] == "owner"

    policies = list(fake_db._tables["policies"].values())
    assert len(policies) == 1
    assert policies[0]["workspace_id"] == ws["id"]


def test_create_workspace_dedupes_slug_on_name_collision(client):
    first = client.post("/v1/workspaces", json={"name": "Acme Inc"}).json()
    second = client.post("/v1/workspaces", json={"name": "Acme Inc"}).json()

    assert first["slug"] == "acme-inc"
    assert second["slug"] == "acme-inc-1"


def test_list_my_workspaces_returns_only_workspaces_the_user_belongs_to(client, fake_db):
    fake_db._tables["workspaces"]["ws-mine"] = {"id": "ws-mine", "name": "Mine", "slug": "mine", "plan": "free", "created_at": datetime.now(timezone.utc).isoformat()}
    fake_db._tables["workspaces"]["ws-other"] = {"id": "ws-other", "name": "Other", "slug": "other", "plan": "free", "created_at": datetime.now(timezone.utc).isoformat()}
    fake_db._tables["workspace_members"]["m1"] = {"workspace_id": "ws-mine", "user_id": USER_ID}

    resp = client.get("/v1/workspaces")
    assert resp.status_code == 200
    ids = [w["id"] for w in resp.json()]
    assert ids == ["ws-mine"]


def test_get_unknown_workspace_returns_404(client):
    resp = client.get("/v1/workspaces/does-not-exist")
    assert resp.status_code == 404


def test_update_workspace_settings(client, fake_db):
    ws = client.post("/v1/workspaces", json={"name": "Acme Inc"}).json()

    resp = client.patch(f"/v1/workspaces/{ws['id']}", json={"notify_email": "ops@acme.com"})
    assert resp.status_code == 200
    assert resp.json()["notify_email"] == "ops@acme.com"
