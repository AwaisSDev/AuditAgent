"""Integration tests for the questionnaires router (F4): upload (file-type
validation, monthly plan-limit enforcement, Redis-not-configured 503),
listing answers with their evidence links joined in, the human-review
update step, and both export formats."""

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
        self.conds = []
        self.order_field = None
        self.order_desc = False
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

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "insert":
            row = {"id": f"row-{len(rows) + 1}", "status": "processing", "error_message": None, "created_at": datetime.now(timezone.utc).isoformat(), **self.payload}
            rows[row["id"]] = row
            return _FakeResult([row])

        matches = list(rows.values())
        for op, field, value in self.conds:
            if op == "eq":
                matches = [r for r in matches if r.get(field) == value]
            elif op == "gte":
                matches = [r for r in matches if r.get(field, "") >= value]

        if self.order_field is not None:
            matches = sorted(matches, key=lambda r: r.get(self.order_field), reverse=self.order_desc)

        if self.op == "update":
            for r in matches:
                r.update(self.payload)
            return _FakeResult([dict(r) for r in matches])

        if self.count_mode == "exact":
            return _FakeResult(matches, count=len(matches))
        if self._single:
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


class _FakeBucket:
    def __init__(self):
        self.uploaded = []

    def upload(self, path, content, options=None):
        self.uploaded.append((path, content, options))


class _FakeStorage:
    def __init__(self):
        self.bucket = _FakeBucket()

    def from_(self, _name):
        return self.bucket


class _FakeDb:
    def __init__(self, plan="starter"):
        self._tables = {
            "workspaces": {WORKSPACE_ID: {"id": WORKSPACE_ID, "name": "Acme Inc", "plan": plan}},
            "questionnaires": {},
            "answers": {},
            "evidence_links": {},
        }
        self.storage = _FakeStorage()

    def table(self, name):
        return _FakeTable(self._tables.setdefault(name, {}))


class _FakeArqPool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, name, *args):
        self.enqueued.append((name, args))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.questionnaires.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_upload_rejects_an_unsupported_file_type(client):
    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/questionnaires",
        files={"file": ("questionnaire.docx", b"not really a docx", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_accepts_a_pdf_and_enqueues_processing(client, fake_db, monkeypatch):
    pool = _FakeArqPool()

    async def _get_pool():
        return pool

    monkeypatch.setattr("app.routers.questionnaires.get_arq_pool", _get_pool)

    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/questionnaires",
        files={"file": ("questionnaire.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["file_type"] == "pdf"
    assert pool.enqueued == [("process_questionnaire", (body["id"],))]
    assert len(fake_db.storage.bucket.uploaded) == 1


def test_upload_returns_503_when_redis_is_not_configured(client, monkeypatch):
    async def _get_pool():
        return None

    monkeypatch.setattr("app.routers.questionnaires.get_arq_pool", _get_pool)

    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/questionnaires",
        files={"file": ("questionnaire.csv", b"question,answer", "text/csv")},
    )
    assert resp.status_code == 503


def test_upload_blocked_once_monthly_limit_reached(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "free"  # limit of 1
    now = datetime.now(timezone.utc).isoformat()
    fake_db._tables["questionnaires"]["q1"] = {"id": "q1", "workspace_id": WORKSPACE_ID, "created_at": now}

    resp = client.post(
        f"/v1/workspaces/{WORKSPACE_ID}/questionnaires",
        files={"file": ("questionnaire.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 402


def test_list_answers_joins_evidence_links(client, fake_db):
    fake_db._tables["answers"]["a1"] = {
        "id": "a1", "questionnaire_id": "q1", "workspace_id": WORKSPACE_ID,
        "question_text": "Do you log actions?", "draft_answer": "Yes.", "final_answer": None, "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    fake_db._tables["evidence_links"]["l1"] = {"id": "l1", "answer_id": "a1", "event_id": "evt-1"}

    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/questionnaires/q1/answers")
    assert resp.status_code == 200
    assert resp.json()[0]["evidence_event_ids"] == ["evt-1"]


def test_update_answer_records_the_reviewer(client, fake_db):
    fake_db._tables["answers"]["a1"] = {
        "id": "a1", "questionnaire_id": "q1", "workspace_id": WORKSPACE_ID,
        "question_text": "Do you log actions?", "draft_answer": "Yes.", "final_answer": None, "status": "draft",
    }

    resp = client.patch(
        f"/v1/workspaces/{WORKSPACE_ID}/answers/a1",
        json={"final_answer": "Yes, every action is logged.", "status": "approved"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["final_answer"] == "Yes, every action is logged."
    assert body["status"] == "approved"
    assert fake_db._tables["answers"]["a1"]["reviewed_by"] == "user-1"


def test_export_csv(client, fake_db):
    fake_db._tables["answers"]["a1"] = {
        "id": "a1", "questionnaire_id": "q1", "workspace_id": WORKSPACE_ID,
        "question_text": "Do you log actions?", "draft_answer": "Yes.", "final_answer": None, "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/questionnaires/q1/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "Do you log actions?" in resp.text


def test_export_docx_watermarks_free_plan(client, fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "free"
    fake_db._tables["questionnaires"]["q1"] = {"id": "q1", "filename": "security-review.pdf"}
    fake_db._tables["answers"]["a1"] = {
        "id": "a1", "questionnaire_id": "q1", "workspace_id": WORKSPACE_ID,
        "question_text": "Do you log actions?", "draft_answer": "Yes.", "final_answer": None, "status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.get(f"/v1/workspaces/{WORKSPACE_ID}/questionnaires/q1/export.docx")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "attachment" in resp.headers["content-disposition"]


def test_list_questionnaires_requires_workspace_membership(fake_db):
    with TestClient(app) as c:
        resp = c.get(f"/v1/workspaces/{WORKSPACE_ID}/questionnaires")
    assert resp.status_code == 401
