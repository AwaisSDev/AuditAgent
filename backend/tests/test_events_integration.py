"""Integration tests for the events router: timeline filtering/pagination,
the export.csv route (and that it really isn't shadowed by /events/{id} at
the HTTP layer, not just in the route table), and a single-event fetch."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, require_workspace_member

WORKSPACE_ID = "ws-1"


def _event(**overrides):
    base = {
        "id": "evt-1",
        "workspace_id": WORKSPACE_ID,
        "agent_id": "agent-1",
        "action_type": "external",
        "action_name": "send_refund",
        "inputs_redacted": {},
        "output_redacted": None,
        "model": None,
        "prompt_hash": None,
        "cost_usd": None,
        "latency_ms": None,
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "row_hash": "hash-1",
        "prev_hash": "hash-0",
    }
    base.update(overrides)
    return base


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self.conds = []
        self.order_field = None
        self.order_desc = False
        self.range_bounds = None
        self.limit_n = None
        self._single = False

    def eq(self, field, value):
        self.conds.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.conds.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self.conds.append(("lte", field, value))
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def range(self, start, end):
        self.range_bounds = (start, end)
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
            elif op == "lte":
                matches = [r for r in matches if r.get(field, "") <= value]

        if self.order_field is not None:
            matches = sorted(matches, key=lambda r: r.get(self.order_field), reverse=self.order_desc)
        if self.range_bounds is not None:
            start, end = self.range_bounds
            matches = matches[start : end + 1]
        if self.limit_n is not None:
            matches = matches[: self.limit_n]

        if self._single:
            return _FakeResult(matches[0] if matches else None)
        return _FakeResult(matches)


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_kw):
        return _FakeQuery(self.rows)


class _FakeDb:
    def __init__(self):
        self._tables = {"events": {}}

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.events.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_events_orders_newest_first_and_respects_workspace_scope(client, fake_db):
    older = _event(id="evt-old", created_at="2026-01-01T00:00:00+00:00")
    newer = _event(id="evt-new", created_at="2026-02-01T00:00:00+00:00")
    other_ws = _event(id="evt-other", workspace_id="ws-2", created_at="2026-03-01T00:00:00+00:00")
    fake_db._tables["events"] = {e["id"]: e for e in (older, newer, other_ws)}

    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/events")
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()]
    assert ids == ["evt-new", "evt-old"]


def test_list_events_filters_by_status(client, fake_db):
    completed = _event(id="evt-1", status="completed")
    rejected = _event(id="evt-2", status="rejected")
    fake_db._tables["events"] = {e["id"]: e for e in (completed, rejected)}

    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/events", params={"status": "rejected"})
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()]
    assert ids == ["evt-2"]


def test_get_single_event(client, fake_db):
    fake_db._tables["events"]["evt-1"] = _event(id="evt-1")
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/events/evt-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "evt-1"


def test_export_csv_route_is_not_shadowed_by_the_event_id_route(client, fake_db):
    fake_db._tables["events"]["evt-1"] = _event(id="evt-1")
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/events/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "evt-1" in resp.text
