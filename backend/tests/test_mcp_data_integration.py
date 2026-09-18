"""Integration tests for the F6 MCP-server-facing endpoints: recent
actions, pending approvals, deciding an approval, ad-hoc questionnaire
drafting, and the compliance summary roll-up — all authenticated by API
key, not a signed-in user, since the MCP server is a headless
integration."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import WorkspaceKeyAuth, get_api_key_auth

WORKSPACE_ID = "ws-1"


class _FakeResult:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, rows, count_mode=None, op="select", payload=None):
        self._rows = rows
        self.count_mode = count_mode
        self.op = op
        self.payload = payload
        self.conds = []
        self.order_field = None
        self.order_desc = False
        self.limit_n = None
        self._single = False

    def eq(self, field, value):
        self.conds.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.conds.append(("gte", field, value))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        matches = list(self._rows.values())
        for op, field, value in self.conds:
            if op == "eq":
                matches = [r for r in matches if r.get(field) == value]
            elif op == "gte":
                matches = [r for r in matches if r.get(field, "") >= value]

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        if self.order_field is not None:
            matches = sorted(matches, key=lambda r: r.get(self.order_field), reverse=self.order_desc)
        if self.limit_n is not None:
            matches = matches[: self.limit_n]

        if self.count_mode == "exact":
            return _FakeResult(matches, count=len(matches))
        if self._single:
            return _FakeResult(matches[0] if matches else None)
        return _FakeResult(matches)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **kw):
        return _FakeQuery(self.rows, count_mode=kw.get("count"))

    def update(self, payload):
        return _FakeQuery(self.rows, op="update", payload=payload)


class _FakeDb:
    def __init__(self):
        self._tables = {"events": {}, "approvals": {}, "workspaces": {}, "audit_chain": {}, "api_keys": {}}

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.mcp_data.get_db", lambda: db)
    # decide_approval_via_mcp calls into apply_decision (approvals_service.py),
    # which does its own get_db() lookup -- same fake, so both see one
    # consistent set of tables.
    monkeypatch.setattr("app.services.approvals_service.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[get_api_key_auth] = lambda: WorkspaceKeyAuth(workspace_id=WORKSPACE_ID, api_key_id="key-1")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_recent_actions_scoped_to_workspace_and_ordered(client, fake_db):
    fake_db._tables["events"] = {
        "e1": {"id": "e1", "workspace_id": WORKSPACE_ID, "action_type": "external", "status": "completed", "created_at": "2026-01-01T00:00:00Z"},
        "e2": {"id": "e2", "workspace_id": WORKSPACE_ID, "action_type": "external", "status": "completed", "created_at": "2026-02-01T00:00:00Z"},
        "e3": {"id": "e3", "workspace_id": "ws-other", "action_type": "external", "status": "completed", "created_at": "2026-03-01T00:00:00Z"},
    }
    resp = client.get("/v1/mcp/recent-actions", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()]
    assert ids == ["e2", "e1"]


def _approval_row(id_: str, status: str, requested_at: str, **action_overrides):
    action = {"agent_name": "ops-bot", "action_type": "external", "action_name": "send_refund", "inputs_preview": {}}
    action.update(action_overrides)
    return {
        "id": id_,
        "workspace_id": WORKSPACE_ID,
        "status": status,
        "requested_at": requested_at,
        "decided_at": None,
        "decision_by": None,
        "decision_note": None,
        "requested_action": action,
    }


def test_pending_approvals_only_returns_pending(client, fake_db):
    fake_db._tables["approvals"] = {
        "a1": _approval_row("a1", "pending", "2026-01-01T00:00:00Z"),
        "a2": _approval_row("a2", "approved", "2026-01-02T00:00:00Z"),
    }
    resp = client.get("/v1/mcp/pending-approvals", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert [a["approval_id"] for a in body] == ["a1"]
    assert body[0]["agent_name"] == "ops-bot"
    assert "ops-bot wants to run send_refund" in body[0]["summary"]


def test_decide_approval_via_mcp_rejects_an_ordinary_key(client, fake_db):
    # client fixture's default WorkspaceKeyAuth has can_review=False (the
    # dataclass default) -- exactly an agent's own tracking key, which must
    # never be able to decide its own pending approval.
    fake_db._tables["approvals"]["a1"] = _approval_row("a1", "pending", "2026-01-01T00:00:00Z")

    resp = client.post(
        "/v1/mcp/approvals/a1/decide",
        json={"decision": "approved"},
        headers={"Authorization": "Bearer al_live_test"},
    )

    assert resp.status_code == 403
    assert fake_db._tables["approvals"]["a1"]["status"] == "pending"


def test_decide_approval_via_mcp_approves_with_a_reviewer_key(client, fake_db):
    app.dependency_overrides[get_api_key_auth] = lambda: WorkspaceKeyAuth(
        workspace_id=WORKSPACE_ID, api_key_id="key-1", can_review=True
    )
    fake_db._tables["api_keys"]["key-1"] = {"id": "key-1", "name": "my-claude-key"}
    fake_db._tables["approvals"]["a1"] = _approval_row("a1", "pending", "2026-01-01T00:00:00Z")

    resp = client.post(
        "/v1/mcp/approvals/a1/decide",
        json={"decision": "approved", "decision_note": "looks fine"},
        headers={"Authorization": "Bearer al_live_test"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["decision_by"] == "my-claude-key (via Claude)"
    assert fake_db._tables["approvals"]["a1"]["status"] == "approved"


def test_draft_questionnaire_answers(client, fake_db):
    fake_db._tables["events"]["e1"] = {
        "id": "e1", "workspace_id": WORKSPACE_ID, "action_type": "external",
        "action_name": "send_refund", "status": "completed", "created_at": "2026-01-01T00:00:00Z",
    }
    fake_answer = SimpleNamespace(answer="Yes, logged.", cited_event_ids=["e1"])
    with patch("app.routers.mcp_data.draft_answer", new=AsyncMock(return_value=fake_answer)):
        resp = client.post(
            "/v1/mcp/draft-questionnaire-answers",
            json=["Do you log refunds?"],
            headers={"Authorization": "Bearer al_live_test"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == [{"question": "Do you log refunds?", "answer": "Yes, logged.", "cited_event_ids": ["e1"]}]


def test_compliance_summary(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID] = {"id": WORKSPACE_ID, "plan": "pro", "slack_channel_id": "C123", "notify_email": None}
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    fake_db._tables["events"] = {
        "e1": {"id": "e1", "workspace_id": WORKSPACE_ID, "status": "completed", "created_at": now.isoformat()},
        "e2": {"id": "e2", "workspace_id": WORKSPACE_ID, "status": "rejected", "created_at": now.isoformat()},
        "e3": {"id": "e3", "workspace_id": WORKSPACE_ID, "status": "completed", "created_at": old.isoformat()},
    }
    fake_db._tables["approvals"]["a1"] = {"id": "a1", "workspace_id": WORKSPACE_ID, "status": "pending"}
    fake_db._tables["audit_chain"]["c1"] = {
        "workspace_id": WORKSPACE_ID, "period_end": now.isoformat(), "event_count": 2, "checkpoint_hash": "hash-1",
    }

    resp = client.get("/v1/mcp/compliance-summary", headers={"Authorization": "Bearer al_live_test"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan"] == "pro"
    assert body["approvals_configured"] is True
    assert body["events_last_30_days_by_status"] == {"completed": 1, "rejected": 1}
    assert body["pending_approvals"] == 1
    assert body["latest_audit_checkpoint"]["checkpoint_hash"] == "hash-1"


def test_mcp_endpoints_require_an_api_key(fake_db):
    with TestClient(app) as c:
        resp = c.get("/v1/mcp/recent-actions")
    assert resp.status_code == 401
