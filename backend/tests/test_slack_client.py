"""Unit tests for the Slack approval-posting service: the no-op-without-a-
bot-token path for both functions (a valid state before a workspace admin
connects Slack), and the message content/shape sent to a mocked
AsyncWebClient."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.slack_client import post_approval_request, update_message_with_decision


def _settings(token: str) -> SimpleNamespace:
    return SimpleNamespace(slack_bot_token=token)


@pytest.mark.anyio
async def test_post_approval_request_noops_without_a_bot_token(monkeypatch):
    monkeypatch.setattr("app.services.slack_client.get_settings", lambda: _settings(""))
    result = await post_approval_request("C123", "appr-1", "billing-bot", "external", "send_refund", {"amount": 49.99})
    assert result is None


@pytest.mark.anyio
async def test_update_message_with_decision_noops_without_a_bot_token(monkeypatch):
    monkeypatch.setattr("app.services.slack_client.get_settings", lambda: _settings(""))
    # Should return cleanly, not raise, even with no client to call.
    await update_message_with_decision("C123", "1700000000.000100", "Approved by reviewer@example.com")


@pytest.mark.anyio
async def test_post_approval_request_posts_and_returns_channel_and_ts(monkeypatch):
    monkeypatch.setattr("app.services.slack_client.get_settings", lambda: _settings("xoxb-fake"))
    fake_response = {"channel": "C123", "ts": "1700000000.000100"}

    with patch("app.services.slack_client.AsyncWebClient") as mock_cls:
        mock_cls.return_value.chat_postMessage = AsyncMock(return_value=fake_response)
        result = await post_approval_request("C123", "appr-1", "billing-bot", "external", "send_refund", {"amount": 49.99})

    assert result == ("C123", "1700000000.000100")
    call_kwargs = mock_cls.return_value.chat_postMessage.call_args.kwargs
    assert call_kwargs["channel"] == "C123"
    action_block = call_kwargs["blocks"][1]
    assert action_block["block_id"] == "approval_appr-1"
    action_ids = [el["action_id"] for el in action_block["elements"]]
    assert action_ids == ["approve", "reject", "edit"]


@pytest.mark.anyio
async def test_update_message_with_decision_calls_chat_update(monkeypatch):
    monkeypatch.setattr("app.services.slack_client.get_settings", lambda: _settings("xoxb-fake"))

    with patch("app.services.slack_client.AsyncWebClient") as mock_cls:
        mock_cls.return_value.chat_update = AsyncMock(return_value={"ok": True})
        await update_message_with_decision("C123", "1700000000.000100", "Approved by reviewer@example.com")

    call_kwargs = mock_cls.return_value.chat_update.call_args.kwargs
    assert call_kwargs["channel"] == "C123"
    assert call_kwargs["ts"] == "1700000000.000100"
    assert call_kwargs["text"] == "Approved by reviewer@example.com"
