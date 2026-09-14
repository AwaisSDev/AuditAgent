"""Integration tests for the policies router: the SDK-facing read endpoint
falls back to the default policy when a workspace has none yet, the
dashboard-facing endpoints create-on-first-read, and an update with
malformed YAML is rejected with a 400 rather than corrupting the stored
policy or crashing."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, WorkspaceKeyAuth, get_api_key_auth, require_workspace_member
from app.services.policy_engine import DEFAULT_POLICY_YAML

WORKSPACE_ID = "ws-1"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table, op, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters = {}
        self.limit_n = None

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            row = {
                "id": f"row-{len(rows) + 1}",
                "is_active": True,
                "name": "default",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **self.payload,
            }
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if all(r.get(k) == v for k, v in self.filters.items())]
        if self.limit_n is not None:
            matches = matches[: self.limit_n]

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

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
        self._tables = {"policies": {}}

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.policies.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_api_key_auth] = lambda: WorkspaceKeyAuth(workspace_id=WORKSPACE_ID, api_key_id="key-1")
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="owner@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_sdk_policy_endpoint_falls_back_to_default_when_none_stored(client):
    resp = client.get("/v1/sdk/policy", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200
    assert resp.json()["rules_yaml"] == DEFAULT_POLICY_YAML


def test_get_policy_creates_default_on_first_read(client, fake_db):
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/policy")
    assert resp.status_code == 200
    assert resp.json()["rules_yaml"] == DEFAULT_POLICY_YAML
    assert len(fake_db._tables["policies"]) == 1

    # A second read must not create a duplicate active policy.
    resp2 = client.get(f"/v1/workspaces/{WORKSPACE_ID}/policy")
    assert resp2.json()["id"] == resp.json()["id"]
    assert len(fake_db._tables["policies"]) == 1


def test_update_policy_with_valid_yaml(client):
    new_yaml = "rules:\n  - match:\n      action_name: send_refund\n    require_approval: true\n"
    resp = client.put(f"/v1/workspaces/{WORKSPACE_ID}/policy", json={"name": "prod", "rules_yaml": new_yaml})
    assert resp.status_code == 200, resp.text
    assert resp.json()["rules_yaml"] == new_yaml

    # Fetching afterward reflects the update, not the default.
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/policy")
    assert resp.json()["rules_yaml"] == new_yaml


def test_update_policy_rejects_malformed_yaml(client, fake_db):
    resp = client.put(f"/v1/workspaces/{WORKSPACE_ID}/policy", json={"rules_yaml": "not: valid: policy: yaml: [["})
    assert resp.status_code == 400
    # Nothing should have been written for a rejected update.
    assert fake_db._tables["policies"] == {}


def test_sdk_policy_endpoint_requires_an_api_key(fake_db):
    with TestClient(app) as c:
        resp = c.get("/v1/sdk/policy")
    assert resp.status_code == 401
