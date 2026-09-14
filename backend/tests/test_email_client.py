"""Covers the Resend email fallback: both functions must no-op cleanly when
RESEND_API_KEY isn't configured (a valid, common state before a workspace's
admin sets up email), rather than crashing the caller (sweep_expired_approvals,
approvals_service)."""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.email_client import send_approval_email, send_timeout_notice


def _settings(api_key: str) -> SimpleNamespace:
    return SimpleNamespace(resend_api_key=api_key, email_from="noreply@example.com")


def test_send_approval_email_noops_without_api_key(monkeypatch):
    monkeypatch.setattr("app.services.email_client.get_settings", lambda: _settings(""))
    with patch("app.services.email_client.resend.Emails.send") as mock_send:
        send_approval_email("user@example.com", "appr-1", "bot", "send_email", "https://app.example.com")
    mock_send.assert_not_called()


def test_send_timeout_notice_noops_without_api_key(monkeypatch):
    monkeypatch.setattr("app.services.email_client.get_settings", lambda: _settings(""))
    with patch("app.services.email_client.resend.Emails.send") as mock_send:
        send_timeout_notice("user@example.com", "bot", "send_email")
    mock_send.assert_not_called()


def test_send_approval_email_sends_with_expected_content(monkeypatch):
    monkeypatch.setattr("app.services.email_client.get_settings", lambda: _settings("re_fake_key"))
    with patch("app.services.email_client.resend.Emails.send") as mock_send:
        send_approval_email("user@example.com", "appr-1", "billing-bot", "send_refund", "https://app.example.com")

    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    assert payload["to"] == ["user@example.com"]
    assert "billing-bot" in payload["subject"]
    assert "appr-1" in payload["html"]


def test_send_timeout_notice_sends_with_expected_content(monkeypatch):
    monkeypatch.setattr("app.services.email_client.get_settings", lambda: _settings("re_fake_key"))
    with patch("app.services.email_client.resend.Emails.send") as mock_send:
        send_timeout_notice("user@example.com", "billing-bot", "send_refund")

    mock_send.assert_called_once()
    payload = mock_send.call_args[0][0]
    assert "Auto-denied" in payload["subject"]
    assert "billing-bot" in payload["html"]
