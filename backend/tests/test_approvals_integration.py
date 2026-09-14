"""End-to-end integration tests for the approval flow through the real
FastAPI app: request -> poll status -> decide -> status again — the same
three endpoints the SDK and dashboard actually call, exercised together
through real routing, dependency injection, and response serialization
(not just the service-layer unit tests in test_approvals_service.py).

Auth is overridden (no real Supabase JWT/API key needed), and Supabase
itself is replaced with an in-memory fake — this is what actually differs
from the live testing done manually against a real Supabase project earlier
in development; this suite is what runs in CI on every push.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, WorkspaceKeyAuth, get_api_key_auth, get_current_user, require_workspace_member

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
        self._single = False

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def single(self):
        self._single = True
        return self

    def limit(self, _n):
        return self

    def order(self, *_a, **_kw):
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            # Mirrors supabase/schema.sql's `approvals` table defaults — a
            # real insert wouldn't require the caller to supply these.
            row = {
                "id": f"row-{len(rows) + 1}",
                "workspace_id": WORKSPACE_ID,
                "event_id": None,
                "agent_id": None,
                "status": "pending",
                "decision_by": None,
                "decision_note": None,
                "slack_channel": None,
                "slack_message_ts": None,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "decided_at": None,
                **self.payload,
            }
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if all(r.get(k) == v for k, v in self.filters.items())]

        if self.op == "select":
            if self._single:
                return _FakeResult(matches[0] if matches else None)
            return _FakeResult(matches)

        if self.op == "update":
            if not matches:
                return _FakeResult([])
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        raise AssertionError(f"unhandled op {self.op}")


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
        self._tables = {"approvals": {}, "workspaces": {WORKSPACE_ID: {"id": WORKSPACE_ID, "slack_channel_id": None, "notify_email": None}}}

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.approvals.get_db", lambda: db)
    monkeypatch.setattr("app.services.approvals_service.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_api_key_auth] = lambda: WorkspaceKeyAuth(workspace_id=WORKSPACE_ID, api_key_id="key-1")
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_full_approval_lifecycle_through_the_real_app(client):
    # 1. SDK-side: request an approval.
    resp = client.post(
        "/v1/approvals/request",
        json={"agent_name": "billing-bot", "action_type": "external", "action_name": "send_refund", "inputs_preview": {"amount": 49.99}},
        headers={"Authorization": "Bearer al_live_test"},
    )
    assert resp.status_code == 200, resp.text
    approval_id = resp.json()["approval_id"]
    assert resp.json()["status"] == "pending"

    # 2. SDK-side: poll status — still pending.
    resp = client.get(f"/v1/approvals/{approval_id}/status", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    # 3. Dashboard-side: a human approves it.
    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals/{approval_id}/decide",
        json={"decision": "approved", "decision_note": "looks fine"},
        headers={"Authorization": "Bearer dashboard-session"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"
    assert resp.json()["decision_by"] == "reviewer@example.com"

    # 4. SDK-side: next poll sees the real decision.
    resp = client.get(f"/v1/approvals/{approval_id}/status", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decision_note"] == "looks fine"

    # 5. A second decision attempt on the same approval is rejected, not
    # silently overwritten (the race-condition guard, exercised through the
    # actual HTTP endpoint this time).
    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals/{approval_id}/decide",
        json={"decision": "rejected"},
        headers={"Authorization": "Bearer dashboard-session"},
    )
    assert resp.status_code == 409


def test_deciding_an_unknown_approval_returns_404(client):
    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals/does-not-exist/decide",
        json={"decision": "approved"},
        headers={"Authorization": "Bearer dashboard-session"},
    )
    assert resp.status_code == 404


def test_polling_status_for_an_unknown_approval_returns_404(client):
    resp = client.get("/v1/approvals/does-not-exist/status", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 404


def test_request_approval_requires_an_api_key(fake_db):
    # No dependency override here — exercises the real get_api_key_auth,
    # which rejects the request before ever touching the database since no
    # Authorization header is sent at all.
    with TestClient(app) as c:
        resp = c.post(
            "/v1/approvals/request",
            json={"agent_name": "x", "action_type": "external", "action_name": "y", "inputs_preview": {}},
        )
    assert resp.status_code == 401


def test_request_approval_posts_to_slack_and_stores_the_message_ref(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["slack_channel_id"] = "C123"

    with patch("app.routers.approvals.post_approval_request", new=AsyncMock(return_value=("C123", "1700000000.0001"))) as mock_post:
        resp = client.post(
            "/v1/approvals/request",
            json={"agent_name": "billing-bot", "action_type": "external", "action_name": "send_refund", "inputs_preview": {}},
            headers={"Authorization": "Bearer al_live_test"},
        )

    assert resp.status_code == 200, resp.text
    mock_post.assert_awaited_once()
    approval_id = resp.json()["approval_id"]
    stored = fake_db._tables["approvals"][approval_id]
    assert stored["slack_channel"] == "C123"
    assert stored["slack_message_ts"] == "1700000000.0001"


def test_request_approval_falls_back_to_email_when_no_slack_channel(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["notify_email"] = "ops@example.com"

    with patch("app.routers.approvals.send_approval_email") as mock_email:
        resp = client.post(
            "/v1/approvals/request",
            json={"agent_name": "billing-bot", "action_type": "external", "action_name": "send_refund", "inputs_preview": {}},
            headers={"Authorization": "Bearer al_live_test"},
        )

    assert resp.status_code == 200, resp.text
    mock_email.assert_called_once()
    args = mock_email.call_args.args
    assert args[0] == "ops@example.com"


def test_list_approvals_filters_by_status(client, fake_db):
    client.post(
        "/v1/approvals/request",
        json={"agent_name": "bot-a", "action_type": "external", "action_name": "send_email", "inputs_preview": {}},
        headers={"Authorization": "Bearer al_live_test"},
    )
    second = client.post(
        "/v1/approvals/request",
        json={"agent_name": "bot-b", "action_type": "external", "action_name": "send_refund", "inputs_preview": {}},
        headers={"Authorization": "Bearer al_live_test"},
    ).json()
    client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/approvals/{second['approval_id']}/decide",
        json={"decision": "approved"},
        headers={"Authorization": "Bearer dashboard-session"},
    )

    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/approvals", params={"status": "approved"})
    assert resp.status_code == 200
    statuses = {a["status"] for a in resp.json()}
    assert statuses == {"approved"}
