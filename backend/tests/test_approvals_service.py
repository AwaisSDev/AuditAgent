"""Covers the compare-and-swap fix in apply_decision: a decision must only
be applied once, even if two callers (e.g. a Slack click racing a dashboard
click) both see the approval as still pending."""

from datetime import datetime, timezone

import pytest

from app.services import approvals_service
from app.services.approvals_service import ApprovalAlreadyDecidedError, apply_decision


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Minimal stand-in for the postgrest fluent query builder: tracks the
    `eq` filters applied so `update()` can honor a `status = pending` guard
    the same way a real conditional UPDATE would."""

    def __init__(self, table: "_FakeApprovalsTable", op: str, payload: dict | None = None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters: dict = {}

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def single(self):
        return self

    def execute(self):
        row = self.table.rows.get(self.filters.get("id"))
        if row is None:
            return _FakeResult(None if self.op == "select" else [])
        if "status" in self.filters and row["status"] != self.filters["status"]:
            # The conditional UPDATE's WHERE clause matches nothing — this is
            # exactly the compare-and-swap this test is verifying.
            return _FakeResult([])
        if self.op == "update":
            row.update(self.payload)
        return _FakeResult(row if self.op == "select" else [dict(row)])


class _FakeApprovalsTable:
    def __init__(self, rows: dict):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return _FakeQuery(self, "select")

    def update(self, payload):
        return _FakeQuery(self, "update", payload)


class _FakeDb:
    def __init__(self, rows: dict):
        self._rows = rows

    def table(self, name):
        assert name == "approvals"
        return _FakeApprovalsTable(self._rows)


def _pending_approval(approval_id="a1"):
    return {
        "id": approval_id,
        "status": "pending",
        "requested_action": {"agent_name": "bot", "action_name": "refund"},
        "slack_channel": None,
        "slack_message_ts": None,
        "decision_by": None,
        "decision_note": None,
        "decided_at": None,
    }


@pytest.mark.anyio
async def test_apply_decision_succeeds_on_a_pending_approval(monkeypatch):
    rows = {"a1": _pending_approval()}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    result = await apply_decision("a1", "approved", decision_by="alice@example.com")

    assert result["status"] == "approved"
    assert result["decision_by"] == "alice@example.com"
    assert rows["a1"]["status"] == "approved"


@pytest.mark.anyio
async def test_apply_decision_rejects_a_second_decision_on_the_same_approval(monkeypatch):
    rows = {"a1": _pending_approval()}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    await apply_decision("a1", "approved", decision_by="alice@example.com")

    with pytest.raises(ApprovalAlreadyDecidedError):
        await apply_decision("a1", "rejected", decision_by="bob@example.com")

    # The first decision must stand — the second caller's write never lands.
    assert rows["a1"]["status"] == "approved"
    assert rows["a1"]["decision_by"] == "alice@example.com"


@pytest.mark.anyio
async def test_apply_decision_raises_for_unknown_approval(monkeypatch):
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb({}))

    with pytest.raises(ValueError):
        await apply_decision("does-not-exist", "approved", decision_by="alice@example.com")
