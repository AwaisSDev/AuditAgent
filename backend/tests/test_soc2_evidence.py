"""Unit tests for compute_live_evidence's aggregation/formatting logic --
given known rows in each table, does the resulting evidence text actually
say the right numbers? Uses a minimal fake postgrest-style query builder
that ignores filter arguments and just returns whatever rows were seeded
for that table, since this module's own SQL-level filtering isn't what's
under test here (it's the arithmetic and string formatting on the result)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.soc2_evidence import compute_live_evidence

WORKSPACE_ID = "ws-1"


class _FakeResult:
    def __init__(self, data, is_count):
        self.data = data
        self.count = len(data) if is_count else None


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._is_count = False

    def select(self, *_a, count=None, **_kw):
        self._is_count = count == "exact"
        return self

    def eq(self, *_a, **_kw):
        return self

    def gte(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    @property
    def not_(self):
        return self

    def is_(self, *_a, **_kw):
        return self

    def execute(self):
        return _FakeResult(self._rows, self._is_count)


class _FakeDb:
    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables

    def table(self, name):
        return _FakeQuery(self._tables.get(name, []))


def _base_tables(**overrides) -> dict[str, list[dict]]:
    tables = {
        "api_keys": [],
        "workspace_members": [],
        "events": [],
        "approvals": [],
        "policies": [{"updated_at": "2026-09-01T00:00:00+00:00"}],
        "policy_history": [],
        "agents": [],
        "audit_chain": [],
        "answers": [],
    }
    tables.update(overrides)
    return tables


@pytest.mark.anyio
async def test_cc61_counts_keys_and_revocations():
    db = _FakeDb(
        _base_tables(
            api_keys=[
                {"revoked_at": None, "last_used_at": "2026-09-19T12:00:00+00:00"},
                {"revoked_at": "2026-09-10T00:00:00+00:00", "last_used_at": None},
                {"revoked_at": None, "last_used_at": None},
            ]
        )
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "3 API key(s)" in evidence["CC6.1"]
    assert "1 revoked" in evidence["CC6.1"]


@pytest.mark.anyio
async def test_cc61_handles_no_keys():
    db = _FakeDb(_base_tables())
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert evidence["CC6.1"] == "No API keys created yet."


@pytest.mark.anyio
async def test_cc63_summarizes_roles():
    db = _FakeDb(
        _base_tables(workspace_members=[{"role": "owner"}, {"role": "member"}, {"role": "member"}])
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "1 owner" in evidence["CC6.3"]
    assert "2 member" in evidence["CC6.3"]


@pytest.mark.anyio
async def test_cc73_counts_rejected_and_timed_out_separately():
    db = _FakeDb(
        _base_tables(
            approvals=[
                {"status": "approved"},
                {"status": "rejected"},
                {"status": "rejected"},
                {"status": "denied_timeout"},
            ]
        )
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "2 rejected" in evidence["CC7.3"]
    assert "1 auto-denied" in evidence["CC7.3"]
    assert "3 stopped action(s)" in evidence["CC7.3"]


@pytest.mark.anyio
async def test_pi11_reports_no_checkpoint_when_none_computed_yet():
    db = _FakeDb(_base_tables())
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert evidence["PI1.1"] == "No checkpoint computed yet."
    assert evidence["CC4.1"] == "No checkpoint computed yet."


@pytest.mark.anyio
async def test_pi11_cites_the_real_checkpoint_hash_and_event_count():
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    db = _FakeDb(
        _base_tables(
            audit_chain=[{"period_end": recent, "event_count": 421, "checkpoint_hash": "abc123def456ghi789"}]
        )
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "421 event(s)" in evidence["PI1.1"]
    assert "abc123def456" in evidence["PI1.1"]
    assert "2h ago" in evidence["PI1.1"]


@pytest.mark.anyio
async def test_cc81_counts_real_policy_history_not_just_current_version():
    db = _FakeDb(
        _base_tables(
            policy_history=[{"id": "h1"}, {"id": "h2"}, {"id": "h3"}],
        )
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "3 policy change(s)" in evidence["CC8.1"]


@pytest.mark.anyio
async def test_p11_distinguishes_drafted_from_approved_answers():
    db = _FakeDb(
        _base_tables(
            answers=[{"status": "draft"}, {"status": "approved"}, {"status": "approved"}],
        )
    )
    evidence = await compute_live_evidence(db, WORKSPACE_ID)
    assert "3 evidence-pack answer(s) drafted" in evidence["P1.1"]
    assert "2 reviewed and approved" in evidence["P1.1"]
