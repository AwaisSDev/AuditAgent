"""Unit tests for app/worker/tasks.py — this module had zero automated
coverage despite being the core F1/F3/F4 pipeline (event processing,
approval timeout sweeping, questionnaire drafting, audit-chain sealing); it
had only been exercised by manual live testing this session, not by
anything that runs in CI on every push."""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.claude_client import DraftedAnswer
from app.worker.tasks import (
    GENESIS_HASH,
    _get_or_create_agent,
    _question_keywords,
    compute_audit_checkpoints,
    process_event_intake,
    process_questionnaire,
    sweep_expired_approvals,
)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Mimics enough of supabase-py's fluent query builder for tasks.py's
    call patterns: eq/lt/gt/lte + limit + order, and `.single()` returning a
    dict instead of a list — matching real supabase-py, not a heuristic."""

    def __init__(self, table, op, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.conds: list[tuple[str, str, object]] = []
        self.order_field = None
        self.order_desc = False
        self.limit_n = None
        self.is_single = False

    def eq(self, field, value):
        self.conds.append((field, "eq", value))
        return self

    def lt(self, field, value):
        self.conds.append((field, "lt", value))
        return self

    def gt(self, field, value):
        self.conds.append((field, "gt", value))
        return self

    def lte(self, field, value):
        self.conds.append((field, "lte", value))
        return self

    def gte(self, field, value):
        self.conds.append((field, "gte", value))
        return self

    def or_(self, filter_str):
        # Not parsed — tests that need OR-matched candidates pre-seed rows
        # that also satisfy the other conditions instead.
        return self

    def order(self, field, desc=False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def single(self):
        self.is_single = True
        return self

    def _matches(self, row):
        for field, op, value in self.conds:
            rv = row.get(field)
            if op == "eq" and rv != value:
                return False
            if op == "lt" and not (rv < value):
                return False
            if op == "gt" and not (rv > value):
                return False
            if op == "lte" and not (rv <= value):
                return False
            if op == "gte" and not (rv >= value):
                return False
        return True

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            row = {"id": f"row-{len(rows) + 1}", **self.payload}
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = [r for r in rows.values() if self._matches(r)]

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        # select
        if self.order_field is not None:
            matches = sorted(matches, key=lambda r: r.get(self.order_field), reverse=self.order_desc)
        if self.limit_n is not None:
            matches = matches[: self.limit_n]
        if self.is_single:
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


class _FakeBucket:
    def __init__(self, content: bytes):
        self.content = content

    def download(self, _path):
        return self.content


class _FakeStorage:
    def __init__(self, content: bytes = b"dummy file bytes"):
        self._bucket = _FakeBucket(content)

    def from_(self, _bucket_name):
        return self._bucket


class _FakeDb:
    def __init__(self, tables=None, storage_content: bytes = b"dummy file bytes"):
        self._tables = tables or {}
        self.storage = _FakeStorage(storage_content)

    def table(self, name):
        return self._tables.setdefault(name, _FakeTable({}))


# -- _question_keywords: pure function, no DB -------------------------------


def test_question_keywords_extracts_meaningful_words():
    kws = _question_keywords("Do you keep a record of actions taken by automated systems?")
    assert "record" in kws
    assert "actions" in kws
    assert "automated" in kws
    assert "systems" in kws


def test_question_keywords_drops_stopwords_and_short_words():
    kws = _question_keywords("What does your company do with this data?")
    # "what", "does", "your", "company", "with", "this" are all stopwords;
    # "data" is only 4 letters, below the 5-letter minimum.
    assert kws == []


def test_question_keywords_caps_at_five_and_dedupes():
    kws = _question_keywords("logging logging approval approval encryption retention deletion redaction masking")
    assert len(kws) <= 5
    assert len(kws) == len(set(kws))


# -- _get_or_create_agent -----------------------------------------------------


def test_get_or_create_agent_returns_existing_agent_id():
    db = _FakeDb()
    db.table("agents").rows["a1"] = {"id": "a1", "workspace_id": "ws-1", "name": "billing-bot"}

    agent_id = _get_or_create_agent(db, "ws-1", "billing-bot")

    assert agent_id == "a1"
    assert len(db.table("agents").rows) == 1  # no duplicate created


def test_get_or_create_agent_creates_a_new_agent_when_none_exists():
    db = _FakeDb()

    agent_id = _get_or_create_agent(db, "ws-1", "new-bot")

    created = db.table("agents").rows[agent_id]
    assert created["workspace_id"] == "ws-1"
    assert created["name"] == "new-bot"


def test_get_or_create_agent_scopes_by_workspace():
    # Same agent name in a different workspace must not collide.
    db = _FakeDb()
    db.table("agents").rows["a1"] = {"id": "a1", "workspace_id": "ws-other", "name": "shared-name"}

    agent_id = _get_or_create_agent(db, "ws-1", "shared-name")

    assert agent_id != "a1"
    assert db.table("agents").rows[agent_id]["workspace_id"] == "ws-1"


# -- sweep_expired_approvals --------------------------------------------------


@pytest.mark.anyio
async def test_sweep_marks_expired_pending_approvals_as_denied_timeout(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    db = _FakeDb()
    db.table("approvals").rows["appr-1"] = {
        "id": "appr-1",
        "workspace_id": "ws-1",
        "status": "pending",
        "expires_at": past,
        "slack_channel": None,
        "slack_message_ts": None,
        "requested_action": {"agent_name": "bot", "action_name": "send_email"},
    }
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1", "notify_email": None}
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.update_message_with_decision", AsyncMock())
    monkeypatch.setattr("app.worker.tasks.send_timeout_notice", lambda *a, **kw: None)

    await sweep_expired_approvals(ctx=None)

    assert db.table("approvals").rows["appr-1"]["status"] == "denied_timeout"
    assert db.table("approvals").rows["appr-1"]["decided_at"] is not None


@pytest.mark.anyio
async def test_sweep_ignores_approvals_not_yet_expired(monkeypatch):
    future = (datetime.now(timezone.utc) + timedelta(minutes=25)).isoformat()
    db = _FakeDb()
    db.table("approvals").rows["appr-1"] = {
        "id": "appr-1",
        "workspace_id": "ws-1",
        "status": "pending",
        "expires_at": future,
        "slack_channel": None,
        "slack_message_ts": None,
        "requested_action": {},
    }
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.update_message_with_decision", AsyncMock())
    monkeypatch.setattr("app.worker.tasks.send_timeout_notice", lambda *a, **kw: None)

    await sweep_expired_approvals(ctx=None)

    assert db.table("approvals").rows["appr-1"]["status"] == "pending"


@pytest.mark.anyio
async def test_sweep_notifies_slack_when_approval_was_posted_there(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    db = _FakeDb()
    db.table("approvals").rows["appr-1"] = {
        "id": "appr-1",
        "workspace_id": "ws-1",
        "status": "pending",
        "expires_at": past,
        "slack_channel": "C123",
        "slack_message_ts": "1234.5678",
        "requested_action": {"agent_name": "bot", "action_name": "send_email"},
    }
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1", "notify_email": None}
    slack_mock = AsyncMock()
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.update_message_with_decision", slack_mock)
    monkeypatch.setattr("app.worker.tasks.send_timeout_notice", lambda *a, **kw: None)

    await sweep_expired_approvals(ctx=None)

    slack_mock.assert_awaited_once()
    args = slack_mock.await_args.args
    assert args[0] == "C123"
    assert args[1] == "1234.5678"


@pytest.mark.anyio
async def test_sweep_emails_fallback_when_no_slack_and_workspace_has_notify_email(monkeypatch):
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    db = _FakeDb()
    db.table("approvals").rows["appr-1"] = {
        "id": "appr-1",
        "workspace_id": "ws-1",
        "status": "pending",
        "expires_at": past,
        "slack_channel": None,
        "slack_message_ts": None,
        "requested_action": {"agent_name": "billing-bot", "action_name": "send_refund"},
    }
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1", "notify_email": "ops@example.com"}
    email_calls = []
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.update_message_with_decision", AsyncMock())
    monkeypatch.setattr("app.worker.tasks.send_timeout_notice", lambda *a, **kw: email_calls.append(a))

    await sweep_expired_approvals(ctx=None)

    assert email_calls == [("ops@example.com", "billing-bot", "send_refund")]


# -- process_event_intake: the core F3 redact -> classify -> insert pipeline -


def _patch_intake_dependencies(monkeypatch, db, redact_calls=None):
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.redact_pii", lambda v, calls=redact_calls: (calls.append(v) if calls is not None else None) or v)
    monkeypatch.setattr("app.worker.tasks.redact_with_llm", AsyncMock(side_effect=lambda d: d))


@pytest.mark.anyio
async def test_process_event_intake_redacts_and_inserts_a_completed_event(monkeypatch):
    db = _FakeDb()
    db.table("event_intake").rows["intake-1"] = {
        "id": "intake-1",
        "status": "queued",
        "workspace_id": "ws-1",
        "payload": {
            "agent_name": "billing-bot",
            "action_type": "external",
            "action_name": "send_refund",
            "inputs": {"to": "customer@example.com"},
            "output": {"result": "ok"},
            "model": "claude-3",
            "cost_usd": 0.01,
            "latency_ms": 120,
            "status": "completed",
        },
    }
    redact_calls: list = []
    _patch_intake_dependencies(monkeypatch, db, redact_calls)

    await process_event_intake(ctx=None, intake_id="intake-1")

    intake = db.table("event_intake").rows["intake-1"]
    assert intake["status"] == "done"
    assert intake["processed_at"] is not None

    events = list(db.table("events").rows.values())
    assert len(events) == 1
    event = events[0]
    assert event["workspace_id"] == "ws-1"
    assert event["action_name"] == "send_refund"
    assert event["inputs_redacted"] == {"to": "customer@example.com"}
    assert event["output_redacted"] == {"result": "ok"}
    assert event["cost_usd"] == 0.01

    agents = list(db.table("agents").rows.values())
    assert len(agents) == 1
    assert agents[0]["name"] == "billing-bot"
    assert event["agent_id"] == agents[0]["id"]

    # Both inputs and output were passed through PII redaction.
    assert {"to": "customer@example.com"} in redact_calls
    assert {"result": "ok"} in redact_calls


@pytest.mark.anyio
async def test_process_event_intake_reuses_an_existing_agent(monkeypatch):
    db = _FakeDb()
    db.table("agents").rows["agent-1"] = {"id": "agent-1", "workspace_id": "ws-1", "name": "billing-bot"}
    db.table("event_intake").rows["intake-1"] = {
        "id": "intake-1",
        "status": "queued",
        "workspace_id": "ws-1",
        "payload": {
            "agent_name": "billing-bot",
            "action_type": "external",
            "action_name": "send_refund",
            "inputs": {},
            "output": None,
        },
    }
    _patch_intake_dependencies(monkeypatch, db)

    await process_event_intake(ctx=None, intake_id="intake-1")

    assert len(db.table("agents").rows) == 1  # no duplicate agent created
    event = list(db.table("events").rows.values())[0]
    assert event["agent_id"] == "agent-1"


@pytest.mark.anyio
async def test_process_event_intake_links_the_event_to_its_approval(monkeypatch):
    db = _FakeDb()
    db.table("approvals").rows["appr-1"] = {"id": "appr-1", "status": "approved", "event_id": None}
    db.table("event_intake").rows["intake-1"] = {
        "id": "intake-1",
        "status": "queued",
        "workspace_id": "ws-1",
        "payload": {
            "agent_name": "billing-bot",
            "action_type": "external",
            "action_name": "send_refund",
            "inputs": {},
            "output": None,
            "approval_id": "appr-1",
        },
    }
    _patch_intake_dependencies(monkeypatch, db)

    await process_event_intake(ctx=None, intake_id="intake-1")

    event_id = list(db.table("events").rows.values())[0]["id"]
    assert db.table("approvals").rows["appr-1"]["event_id"] == event_id


@pytest.mark.anyio
async def test_process_event_intake_is_a_noop_for_an_already_processed_intake(monkeypatch):
    db = _FakeDb()
    db.table("event_intake").rows["intake-1"] = {"id": "intake-1", "status": "done", "workspace_id": "ws-1", "payload": {}}
    _patch_intake_dependencies(monkeypatch, db)

    await process_event_intake(ctx=None, intake_id="intake-1")

    assert "events" not in db._tables or not db.table("events").rows
    assert db.table("event_intake").rows["intake-1"]["status"] == "done"


@pytest.mark.anyio
async def test_process_event_intake_marks_error_and_reraises_on_failure(monkeypatch):
    db = _FakeDb()
    db.table("event_intake").rows["intake-1"] = {
        "id": "intake-1",
        "status": "queued",
        "workspace_id": "ws-1",
        "payload": {"agent_name": "bot", "action_type": "external", "action_name": "x", "inputs": {}, "output": None},
    }
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)

    def boom(_v):
        raise ValueError("redaction service unavailable")

    monkeypatch.setattr("app.worker.tasks.redact_pii", boom)

    with pytest.raises(ValueError, match="redaction service unavailable"):
        await process_event_intake(ctx=None, intake_id="intake-1")

    intake = db.table("event_intake").rows["intake-1"]
    assert intake["status"] == "error"
    assert "redaction service unavailable" in intake["error_message"]
    # Never left stuck on "processing" — a hung status a human could never fix.
    assert intake["status"] != "processing"


# -- compute_audit_checkpoints: daily hash-chain sealing ----------------------


@pytest.mark.anyio
async def test_compute_audit_checkpoints_creates_the_first_checkpoint(monkeypatch):
    db = _FakeDb()
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1"}
    db.table("events").rows["e1"] = {"id": "e1", "workspace_id": "ws-1", "row_hash": "aaa", "created_at": "2020-01-01T00:00:00+00:00"}
    db.table("events").rows["e2"] = {"id": "e2", "workspace_id": "ws-1", "row_hash": "bbb", "created_at": "2020-01-02T00:00:00+00:00"}
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)

    await compute_audit_checkpoints(ctx=None)

    checkpoints = list(db.table("audit_chain").rows.values())
    assert len(checkpoints) == 1
    cp = checkpoints[0]
    assert cp["workspace_id"] == "ws-1"
    assert cp["event_count"] == 2
    assert cp["prev_checkpoint_hash"] == GENESIS_HASH
    assert cp["checkpoint_hash"] == hashlib.sha256(("aaa" + "bbb" + GENESIS_HASH).encode()).hexdigest()


@pytest.mark.anyio
async def test_compute_audit_checkpoints_chains_onto_the_previous_checkpoint(monkeypatch):
    db = _FakeDb()
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1"}
    db.table("audit_chain").rows["cp-0"] = {
        "id": "cp-0",
        "workspace_id": "ws-1",
        "period_end": "2020-06-01T00:00:00+00:00",
        "checkpoint_hash": "existing-hash",
    }
    db.table("events").rows["e1"] = {"id": "e1", "workspace_id": "ws-1", "row_hash": "ccc", "created_at": "2020-06-02T00:00:00+00:00"}
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)

    await compute_audit_checkpoints(ctx=None)

    new_checkpoints = [r for r in db.table("audit_chain").rows.values() if r["id"] != "cp-0"]
    assert len(new_checkpoints) == 1
    cp = new_checkpoints[0]
    assert cp["period_start"] == "2020-06-01T00:00:00+00:00"
    assert cp["prev_checkpoint_hash"] == "existing-hash"
    assert cp["checkpoint_hash"] == hashlib.sha256(("ccc" + "existing-hash").encode()).hexdigest()


@pytest.mark.anyio
async def test_compute_audit_checkpoints_skips_a_workspace_with_no_new_events(monkeypatch):
    db = _FakeDb()
    db.table("workspaces").rows["ws-1"] = {"id": "ws-1"}
    # No events at all for this workspace.
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)

    await compute_audit_checkpoints(ctx=None)

    assert "audit_chain" not in db._tables or not db.table("audit_chain").rows


# -- process_questionnaire: F4 parse -> match evidence -> draft answers ------


def _patch_questionnaire_dependencies(monkeypatch, db, questions, drafted=None):
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)
    monkeypatch.setattr("app.worker.tasks.parse_questionnaire", lambda _bytes, _file_type: questions)
    monkeypatch.setattr(
        "app.worker.tasks.draft_answer",
        AsyncMock(return_value=drafted or DraftedAnswer(answer="Yes, see cited events.", cited_event_ids=["e1"])),
    )


@pytest.mark.anyio
async def test_process_questionnaire_drafts_an_answer_per_question_and_marks_ready(monkeypatch):
    db = _FakeDb()
    db.table("questionnaires").rows["q1"] = {
        "id": "q1",
        "workspace_id": "ws-1",
        "storage_path": "ws-1/q1.csv",
        "file_type": "csv",
        "status": "processing",
    }
    db.table("events").rows["e1"] = {"id": "e1", "workspace_id": "ws-1", "action_type": "external", "action_name": "send_refund"}
    _patch_questionnaire_dependencies(
        monkeypatch, db, questions=["Do you log all agent actions?", "Is customer PII redacted before storage?"]
    )

    await process_questionnaire(ctx=None, questionnaire_id="q1")

    assert db.table("questionnaires").rows["q1"]["status"] == "ready"

    answers = list(db.table("answers").rows.values())
    assert len(answers) == 2
    assert {a["question_text"] for a in answers} == {"Do you log all agent actions?", "Is customer PII redacted before storage?"}
    assert all(a["draft_answer"] == "Yes, see cited events." for a in answers)
    assert all(a["workspace_id"] == "ws-1" for a in answers)

    links = list(db.table("evidence_links").rows.values())
    assert len(links) == 2  # one citation per answer
    assert all(link["event_id"] == "e1" for link in links)
    answer_ids = {a["id"] for a in answers}
    assert {link["answer_id"] for link in links} == answer_ids


@pytest.mark.anyio
async def test_process_questionnaire_falls_back_to_recent_events_when_a_question_has_no_keywords(monkeypatch):
    db = _FakeDb()
    db.table("questionnaires").rows["q1"] = {
        "id": "q1",
        "workspace_id": "ws-1",
        "storage_path": "ws-1/q1.csv",
        "file_type": "csv",
        "status": "processing",
    }
    db.table("events").rows["e1"] = {"id": "e1", "workspace_id": "ws-1", "action_type": "external", "action_name": "send_refund"}
    # Every word here is either a stopword or under the 5-letter minimum, so
    # _question_keywords returns [] — this exercises the "no keywords ->
    # fall back to most-recent-events" branch specifically, rather than the
    # keyword-matched branch.
    _patch_questionnaire_dependencies(monkeypatch, db, questions=["What does this do?"])

    await process_questionnaire(ctx=None, questionnaire_id="q1")

    answers = list(db.table("answers").rows.values())
    assert len(answers) == 1
    links = list(db.table("evidence_links").rows.values())
    assert links[0]["event_id"] == "e1"


@pytest.mark.anyio
async def test_process_questionnaire_is_a_noop_when_the_questionnaire_is_missing(monkeypatch):
    db = _FakeDb()
    _patch_questionnaire_dependencies(monkeypatch, db, questions=["Do you log all agent actions?"])

    await process_questionnaire(ctx=None, questionnaire_id="does-not-exist")

    assert "answers" not in db._tables or not db.table("answers").rows


@pytest.mark.anyio
async def test_process_questionnaire_marks_error_and_reraises_when_parsing_fails(monkeypatch):
    db = _FakeDb()
    db.table("questionnaires").rows["q1"] = {
        "id": "q1",
        "workspace_id": "ws-1",
        "storage_path": "ws-1/q1.csv",
        "file_type": "csv",
        "status": "processing",
    }
    monkeypatch.setattr("app.worker.tasks.get_db", lambda: db)

    def boom(_bytes, _file_type):
        raise ValueError("unrecognized file format")

    monkeypatch.setattr("app.worker.tasks.parse_questionnaire", boom)

    with pytest.raises(ValueError, match="unrecognized file format"):
        await process_questionnaire(ctx=None, questionnaire_id="q1")

    q = db.table("questionnaires").rows["q1"]
    assert q["status"] == "error"
    assert "unrecognized file format" in q["error_message"]
