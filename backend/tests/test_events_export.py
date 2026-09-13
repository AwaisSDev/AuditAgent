import csv
import io
import json

from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, require_workspace_member
from app.services.events_export import build_events_csv

EVENTS = [
    {
        "id": "evt_1",
        "created_at": "2026-09-13T21:32:00+00:00",
        "agent_id": "agent_1",
        "action_type": "internal",
        "action_name": "summarize_ticket",
        "status": "completed",
        "model": "claude-haiku-4-5",
        "cost_usd": 0.0012,
        "latency_ms": 340,
        "inputs_redacted": {"ticket_text": "[REDACTED]"},
        "output_redacted": "Summary of: ...",
        "prompt_hash": "abc123",
        "prev_hash": "0" * 64,
        "row_hash": "f" * 64,
    },
    {
        "id": "evt_2",
        "created_at": "2026-09-13T21:33:00+00:00",
        "agent_id": None,
        "action_type": "external",
        "action_name": "send_refund_email",
        "status": "error",
        "model": None,
        "cost_usd": None,
        "latency_ms": None,
        "inputs_redacted": {},
        "output_redacted": None,
        "prompt_hash": None,
        "prev_hash": "f" * 64,
        "row_hash": "e" * 64,
    },
]


def test_build_events_csv_has_header_and_every_row():
    content = build_events_csv(EVENTS)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    assert rows[0][0] == "id"
    assert len(rows) == 3  # header + 2 events


def test_build_events_csv_includes_hash_chain_columns():
    content = build_events_csv(EVENTS)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    header = rows[0]
    prev_hash_col = header.index("prev_hash")
    row_hash_col = header.index("row_hash")
    assert rows[1][prev_hash_col] == "0" * 64
    assert rows[1][row_hash_col] == "f" * 64
    # The chain: row 2's prev_hash matches row 1's row_hash.
    assert rows[2][prev_hash_col] == rows[1][row_hash_col]


def test_build_events_csv_serializes_redacted_payloads_as_json():
    content = build_events_csv(EVENTS)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    header = rows[0]
    inputs_col = header.index("inputs_redacted")
    assert json.loads(rows[1][inputs_col]) == {"ticket_text": "[REDACTED]"}


def test_build_events_csv_handles_null_fields_without_crashing():
    content = build_events_csv(EVENTS)
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    header = rows[0]
    assert rows[2][header.index("agent_id")] == ""
    assert rows[2][header.index("model")] == ""
    assert rows[2][header.index("cost_usd")] == ""
    assert rows[2][header.index("output_redacted")] == ""


def test_build_events_csv_handles_empty_list():
    content = build_events_csv([])
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    assert len(rows) == 1  # header only


def test_export_route_is_not_shadowed_by_the_event_id_route(monkeypatch):
    """GET /events/export.csv and GET /events/{event_id} share a path shape
    at the same segment ("export.csv" is a valid event_id syntactically) —
    this guards the route registration order in routers/events.py so the
    static export route keeps winning."""

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def eq(self, *_a, **_kw):
            return self

        def order(self, *_a, **_kw):
            return self

        def limit(self, *_a, **_kw):
            return self

        def execute(self):
            return _FakeResult(self._rows)

    class _FakeTable:
        def __init__(self, rows):
            self._rows = rows

        def select(self, *_a, **_kw):
            return _FakeQuery(self._rows)

    class _FakeDb:
        def table(self, _name):
            return _FakeTable(EVENTS)

    monkeypatch.setattr("app.routers.events.get_db", lambda: _FakeDb())
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    try:
        with TestClient(app) as client:
            resp = client.get("/v1/workspaces/ws-1/events/export.csv", headers={"Authorization": "Bearer session"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(resp.text)))
    assert len(rows) == 3  # header + 2 events
