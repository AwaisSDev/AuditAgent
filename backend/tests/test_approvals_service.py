"""Covers the compare-and-swap fix in apply_decision: a decision must only
be applied once, even if two callers (e.g. a Slack click racing a dashboard
click) both see the approval as still pending."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

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
        if "workspace_id" in self.filters and row.get("workspace_id") != self.filters["workspace_id"]:
            # Same idea as the status guard above, but for tenant scoping:
            # a workspace_id filter that doesn't match the row must behave
            # like "not found", not silently ignore the filter.
            return _FakeResult(None if self.op == "select" else [])
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


def _pending_approval(approval_id="a1", workspace_id="ws-1"):
    return {
        "id": approval_id,
        "workspace_id": workspace_id,
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


@pytest.mark.anyio
async def test_apply_decision_merges_edited_inputs_into_requested_action(monkeypatch):
    rows = {"a1": _pending_approval()}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    result = await apply_decision(
        "a1",
        "approved",
        decision_by="alice@example.com",
        edited_action={"inputs_preview": {"amount": 10}},
    )

    # The edit merges into (doesn't replace) the original requested_action.
    assert result["requested_action"] == {"agent_name": "bot", "action_name": "refund", "inputs_preview": {"amount": 10}}


class _RaceQuery(_FakeQuery):
    """Simulates a genuine race: by the time the conditional UPDATE's WHERE
    clause is evaluated, another caller has already flipped the row's status
    -- distinct from the sequential two-call race the tests above exercise,
    where the second call's own SELECT already sees the new status."""

    def execute(self):
        if self.op == "update":
            self.table.rows["a1"]["status"] = "rejected"  # a concurrent decision "wins" here
        return super().execute()


class _RaceApprovalsTable(_FakeApprovalsTable):
    def update(self, payload):
        return _RaceQuery(self, "update", payload)


class _RaceDb(_FakeDb):
    def table(self, name):
        assert name == "approvals"
        return _RaceApprovalsTable(self._rows)


@pytest.mark.anyio
async def test_apply_decision_detects_a_concurrent_update_at_the_database_level(monkeypatch):
    rows = {"a1": _pending_approval()}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _RaceDb(rows))

    with pytest.raises(ApprovalAlreadyDecidedError):
        await apply_decision("a1", "approved", decision_by="alice@example.com")


@pytest.mark.anyio
async def test_apply_decision_updates_the_slack_message_when_one_exists(monkeypatch):
    rows = {"a1": {**_pending_approval(), "slack_channel": "C123", "slack_message_ts": "1700000000.0001"}}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))
    mock_update = AsyncMock()
    monkeypatch.setattr(approvals_service, "update_message_with_decision", mock_update)

    await apply_decision("a1", "approved", decision_by="alice@example.com", decision_note="looks fine")

    mock_update.assert_awaited_once()
    channel, ts, summary = mock_update.await_args.args
    assert channel == "C123"
    assert ts == "1700000000.0001"
    assert "Approved" in summary
    assert "alice@example.com" in summary
    assert "looks fine" in summary


@pytest.mark.anyio
async def test_apply_decision_skips_slack_update_when_no_message_was_posted(monkeypatch):
    rows = {"a1": _pending_approval()}  # slack_channel/slack_message_ts are None
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))
    mock_update = AsyncMock()
    monkeypatch.setattr(approvals_service, "update_message_with_decision", mock_update)

    await apply_decision("a1", "rejected", decision_by="alice@example.com")

    mock_update.assert_not_awaited()


# -- Cross-tenant authorization ----------------------------------------------
#
# apply_decision is reachable two ways: the dashboard's decide endpoint
# (routers/approvals.py), which only proves the caller belongs to *some*
# workspace via require_workspace_member(workspace_id) -- not that
# approval_id itself belongs to that workspace -- and the Slack webhook
# (routers/slack.py), authenticated instead by Slack's own signature check
# on a button Tracyn posted itself. A missing workspace_id filter here
# would let any member of any workspace decide another tenant's approval by
# id, so the dashboard path must pass workspace_id through and have it
# enforced at the database-query level, not just the initial select.


@pytest.mark.anyio
async def test_apply_decision_rejects_an_approval_belonging_to_a_different_workspace(monkeypatch):
    rows = {"a1": _pending_approval(workspace_id="ws-victim")}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    with pytest.raises(ValueError):
        await apply_decision("a1", "approved", decision_by="attacker@example.com", workspace_id="ws-attacker")

    # The victim workspace's approval must be untouched.
    assert rows["a1"]["status"] == "pending"


@pytest.mark.anyio
async def test_apply_decision_succeeds_with_the_matching_workspace_id(monkeypatch):
    rows = {"a1": _pending_approval(workspace_id="ws-1")}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    result = await apply_decision("a1", "approved", decision_by="alice@example.com", workspace_id="ws-1")

    assert result["status"] == "approved"


@pytest.mark.anyio
async def test_apply_decision_without_a_workspace_id_still_works_for_the_slack_path(monkeypatch):
    rows = {"a1": _pending_approval(workspace_id="ws-1")}
    monkeypatch.setattr(approvals_service, "get_db", lambda: _FakeDb(rows))

    result = await apply_decision("a1", "approved", decision_by="@reviewer")

    assert result["status"] == "approved"
