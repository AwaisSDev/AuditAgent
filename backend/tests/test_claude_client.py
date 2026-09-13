"""Covers the graceful-degradation fix in draft_answer: one question's LLM
failure (or no API key at all) must produce a fallback answer, never an
unhandled exception that would abort every other question in the same
questionnaire (see worker/tasks.py::process_questionnaire's single
try/except around the whole file)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import claude_client
from app.services.claude_client import draft_answer

CANDIDATES = [
    {"id": "evt_1", "action_type": "external", "action_name": "send_email", "status": "completed", "created_at": "2026-01-01T00:00:00Z"},
]


def _settings(api_key: str) -> SimpleNamespace:
    return SimpleNamespace(anthropic_api_key=api_key, anthropic_sonnet_model="claude-sonnet-4-6")


@pytest.mark.anyio
async def test_draft_answer_degrades_gracefully_with_no_api_key(monkeypatch):
    monkeypatch.setattr(claude_client, "get_settings", lambda: _settings(""))

    result = await draft_answer("Do you log all actions?", CANDIDATES)

    assert result.cited_event_ids == []
    assert "manually" in result.answer.lower()


@pytest.mark.anyio
async def test_draft_answer_degrades_gracefully_on_api_error(monkeypatch):
    monkeypatch.setattr(claude_client, "get_settings", lambda: _settings("sk-ant-fake"))

    with patch("app.services.claude_client.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("simulated Anthropic outage"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        result = await draft_answer("Do you log all actions?", CANDIDATES)

    assert result.cited_event_ids == []
    assert "manually" in result.answer.lower()


@pytest.mark.anyio
async def test_draft_answer_parses_a_successful_response(monkeypatch):
    monkeypatch.setattr(claude_client, "get_settings", lambda: _settings("sk-ant-fake"))

    fake_block = SimpleNamespace(type="text", text='{"answer": "Yes, logged automatically.", "cited_event_ids": ["evt_1", "evt_bogus"]}')
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.claude_client.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_answer("Do you log all actions?", CANDIDATES)

    assert result.answer == "Yes, logged automatically."
    # A cited id that isn't one of the real candidates must be dropped.
    assert result.cited_event_ids == ["evt_1"]


@pytest.mark.anyio
async def test_draft_answer_degrades_gracefully_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(claude_client, "get_settings", lambda: _settings("sk-ant-fake"))

    fake_block = SimpleNamespace(type="text", text="not json at all")
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.claude_client.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_answer("Do you log all actions?", CANDIDATES)

    assert result.cited_event_ids == []
    assert "manually" in result.answer.lower()
