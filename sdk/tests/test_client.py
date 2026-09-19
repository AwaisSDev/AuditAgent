import asyncio
import atexit
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tracyn.client import Tracyn
from tracyn.exceptions import ApprovalDeniedError, ApprovalTimeoutError
from tracyn.policy import DEFAULT_POLICY_YAML


def _make_agent(monkeypatch):
    """A Tracyn with the background network thread neutered: events are
    captured in a list instead of being queued for a real HTTP POST, and no
    policy fetch hits the network (policy_yaml is passed explicitly)."""
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml="rules: []")
    events = []
    monkeypatch.setattr(agent, "_enqueue_event", lambda **fields: events.append(fields))
    return agent, events


def test_track_logs_completed_event_on_success(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="add")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5
    assert len(events) == 1
    assert events[0]["status"] == "completed"
    assert events[0]["inputs"] == {"a": 2, "b": 3}
    assert events[0]["output"] == 5


def test_track_logs_error_event_and_reraises_on_failure(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="boom")
    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        boom()

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["output"]["error"] == "ValueError"
    assert "kaboom" in events[0]["output"]["message"]


def test_track_async_logs_completed_event_on_success(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="add")
    async def add(a, b):
        return a + b

    assert asyncio.run(add(2, 3)) == 5
    assert len(events) == 1
    assert events[0]["status"] == "completed"


def test_track_async_logs_error_event_and_reraises_on_failure(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="boom")
    async def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        asyncio.run(boom())

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["output"]["error"] == "ValueError"


def test_registers_atexit_hook_so_events_flush_on_normal_process_exit(monkeypatch):
    registered = []
    monkeypatch.setattr(atexit, "register", lambda fn: registered.append(fn))

    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml="rules: []")

    assert agent.close in registered
    agent.close()


def test_close_is_idempotent(monkeypatch):
    # atexit will call close() even if the caller already called it manually
    # (e.g. in a `finally` block) — this must not raise or hang.
    agent, _events = _make_agent(monkeypatch)

    agent.close()
    agent.close()

    assert not agent._thread.is_alive()


def test_fetch_policy_falls_back_to_default_on_a_network_error(monkeypatch):
    monkeypatch.setattr(atexit, "register", lambda fn: None)
    with patch("tracyn.client.httpx.get", side_effect=httpx.ConnectError("no network")):
        agent = Tracyn(api_key="test", agent_name="test-agent")

    # DEFAULT_POLICY_YAML requires approval for any "external" action.
    assert agent.policy.requires_approval("external", "anything") is True
    agent.close()


def test_track_runs_the_function_and_logs_when_approved(monkeypatch):
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml=DEFAULT_POLICY_YAML)
    events = []
    monkeypatch.setattr(agent, "_enqueue_event", lambda **fields: events.append(fields))
    monkeypatch.setattr(agent, "_request_approval_sync", lambda *a, **kw: {"status": "approved", "id": "appr-1", "decision_by": "alice"})

    @agent.track(action_type="external", action_name="send_refund")
    def send_refund(amount):
        return {"ok": True, "amount": amount}

    result = send_refund(50)

    assert result == {"ok": True, "amount": 50}
    statuses = [e["status"] for e in events]
    assert statuses == ["approved", "completed"]
    agent.close()


def test_track_raises_approval_denied_and_never_runs_the_function(monkeypatch):
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml=DEFAULT_POLICY_YAML)
    monkeypatch.setattr(agent, "_enqueue_event", lambda **fields: None)
    monkeypatch.setattr(agent, "_request_approval_sync", lambda *a, **kw: {"status": "rejected", "id": "appr-1", "decision_by": "alice", "decision_note": "too risky"})

    calls = []

    @agent.track(action_type="external", action_name="send_refund")
    def send_refund(amount):
        calls.append(amount)
        return "should not run"

    with pytest.raises(ApprovalDeniedError, match="too risky"):
        send_refund(50)

    assert calls == []
    agent.close()


def test_track_raises_approval_timeout(monkeypatch):
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml=DEFAULT_POLICY_YAML)
    monkeypatch.setattr(agent, "_enqueue_event", lambda **fields: None)
    monkeypatch.setattr(agent, "_request_approval_sync", lambda *a, **kw: {"status": "denied_timeout", "id": "appr-1"})

    @agent.track(action_type="external", action_name="send_refund")
    def send_refund(amount):
        return amount

    with pytest.raises(ApprovalTimeoutError):
        send_refund(50)
    agent.close()


def test_track_async_runs_and_raises_denied_the_same_way(monkeypatch):
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml=DEFAULT_POLICY_YAML)
    monkeypatch.setattr(agent, "_enqueue_event", lambda **fields: None)

    async def _approval(*a, **kw):
        return {"status": "rejected", "id": "appr-1", "decision_by": "alice", "decision_note": None}

    monkeypatch.setattr(agent, "_request_approval_async", _approval)

    @agent.track(action_type="external", action_name="send_refund")
    async def send_refund(amount):
        return amount

    with pytest.raises(ApprovalDeniedError):
        asyncio.run(send_refund(50))
    agent.close()


def test_cost_fn_populates_cost_usd(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="call_llm", cost_fn=lambda output: output["tokens"] * 0.001)
    def call_llm():
        return {"tokens": 100}

    call_llm()

    assert events[0]["cost_usd"] == 0.1


def test_cost_fn_exception_falls_back_to_none(monkeypatch):
    agent, events = _make_agent(monkeypatch)

    @agent.track(action_type="internal", action_name="call_llm", cost_fn=lambda output: 1 / 0)
    def call_llm():
        return {"tokens": 100}

    call_llm()  # must not raise even though cost_fn blows up

    assert events[0]["cost_usd"] is None


def test_send_with_retry_succeeds_on_first_attempt():
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml="rules: []")
    fake_client = MagicMock()
    fake_client.post.return_value = MagicMock(status_code=202)

    agent._send_with_retry(fake_client, {"action_name": "x"})

    assert fake_client.post.call_count == 1
    agent.close()


def test_send_with_retry_retries_then_succeeds():
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml="rules: []")
    fake_client = MagicMock()
    fake_client.post.side_effect = [httpx.ConnectError("boom"), MagicMock(status_code=202)]

    with patch("time.sleep"):
        agent._send_with_retry(fake_client, {"action_name": "x"})

    assert fake_client.post.call_count == 2
    agent.close()


def test_send_with_retry_warns_to_stderr_after_exhausting_attempts(capsys):
    agent = Tracyn(api_key="test", agent_name="test-agent", policy_yaml="rules: []")
    fake_client = MagicMock()
    fake_client.post.side_effect = httpx.ConnectError("persistent outage")

    with patch("time.sleep"):
        agent._send_with_retry(fake_client, {"action_name": "send_refund"}, attempts=2)

    captured = capsys.readouterr()
    assert "send_refund" in captured.err
    assert "WARNING" in captured.err
    assert fake_client.post.call_count == 2
    agent.close()


def test_flush_returns_once_the_queue_drains(monkeypatch):
    agent, _events = _make_agent(monkeypatch)
    # The background flush thread is real here (only _enqueue_event is
    # faked above), so avoid a real network call for the item this test
    # puts directly on the queue.
    monkeypatch.setattr(agent, "_send_with_retry", lambda client, event: None)
    agent._queue.put_nowait({"action_name": "x"})

    # The real flush loop thread drains the queue in the background; give it
    # a generous deadline and confirm flush() actually waits for that, not
    # just returning immediately regardless of queue state.
    start = time.monotonic()
    agent.flush(timeout=2.0)
    assert agent._queue.empty()
    assert time.monotonic() - start < 2.0
    agent.close()
