import asyncio
import atexit

import pytest

from auditagent.client import AuditAgent


def _make_agent(monkeypatch):
    """An AuditAgent with the background network thread neutered: events are
    captured in a list instead of being queued for a real HTTP POST, and no
    policy fetch hits the network (policy_yaml is passed explicitly)."""
    agent = AuditAgent(api_key="test", agent_name="test-agent", policy_yaml="rules: []")
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

    agent = AuditAgent(api_key="test", agent_name="test-agent", policy_yaml="rules: []")

    assert agent.close in registered
    agent.close()


def test_close_is_idempotent(monkeypatch):
    # atexit will call close() even if the caller already called it manually
    # (e.g. in a `finally` block) — this must not raise or hang.
    agent, _events = _make_agent(monkeypatch)

    agent.close()
    agent.close()

    assert not agent._thread.is_alive()
