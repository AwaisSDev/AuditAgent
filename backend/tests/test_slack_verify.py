"""Covers Slack request-signature verification: the webhook route
(routers/slack.py) trusts this to reject forged/replayed requests, so both
the "not configured" and the actual signature-check paths need coverage."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.slack_verify import verify_slack_request


def test_verify_slack_request_fails_closed_without_signing_secret(monkeypatch):
    monkeypatch.setattr(
        "app.services.slack_verify.get_settings",
        lambda: SimpleNamespace(slack_signing_secret=""),
    )
    assert verify_slack_request(b"body", "1700000000", "v0=deadbeef") is False


def test_verify_slack_request_delegates_to_signature_verifier(monkeypatch):
    monkeypatch.setattr(
        "app.services.slack_verify.get_settings",
        lambda: SimpleNamespace(slack_signing_secret="shhh"),
    )
    fake_verifier = MagicMock()
    fake_verifier.is_valid.return_value = True

    with patch("app.services.slack_verify.SignatureVerifier", return_value=fake_verifier) as mock_cls:
        result = verify_slack_request(b"body", "1700000000", "v0=deadbeef")

    mock_cls.assert_called_once_with("shhh")
    fake_verifier.is_valid.assert_called_once_with(body=b"body", timestamp="1700000000", signature="v0=deadbeef")
    assert result is True


def test_verify_slack_request_rejects_a_bad_signature(monkeypatch):
    monkeypatch.setattr(
        "app.services.slack_verify.get_settings",
        lambda: SimpleNamespace(slack_signing_secret="shhh"),
    )
    fake_verifier = MagicMock()
    fake_verifier.is_valid.return_value = False

    with patch("app.services.slack_verify.SignatureVerifier", return_value=fake_verifier):
        result = verify_slack_request(b"body", "1700000000", "v0=forged")

    assert result is False
