"""Unit tests for the Whop billing service: the BillingNotConfiguredError
fail-closed behavior (same rationale as the Stripe client this replaces),
the plan<->plan-id mapping in both directions, checkout/membership calls
against a mocked httpx, and -- the part most worth actually exercising
rather than mocking away -- the Standard Webhooks signature verification,
checked against real HMAC-SHA256 signatures computed the same way Whop
computes them."""

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.whop_client import (
    BillingNotConfiguredError,
    create_checkout_session,
    get_membership,
    plan_for_whop_plan_id,
    verify_webhook,
    whop_plan_id_for,
)

_TEST_SECRET = "whsec_" + base64.b64encode(b"0" * 32).decode()


def _settings(**overrides):
    base = SimpleNamespace(
        whop_api_base_url="https://sandbox-api.whop.com/api/v1",
        whop_api_key="whop_test_fake",
        whop_webhook_secret=_TEST_SECRET,
        whop_plan_starter="plan_starter",
        whop_plan_pro="plan_pro",
        dashboard_base_url="https://app.example.com",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _sign(secret: str, webhook_id: str, timestamp: str, body: bytes) -> str:
    secret_bytes = base64.b64decode(secret[len("whsec_") :] if secret.startswith("whsec_") else secret)
    signed_content = f"{webhook_id}.{timestamp}.".encode() + body
    sig = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()
    return f"v1,{sig}"


def test_whop_plan_id_for_returns_the_configured_id(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    assert whop_plan_id_for("starter") == "plan_starter"


def test_whop_plan_id_for_rejects_an_unknown_plan(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    with pytest.raises(ValueError):
        whop_plan_id_for("nonexistent")


def test_whop_plan_id_for_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings(whop_plan_starter=""))
    with pytest.raises(BillingNotConfiguredError):
        whop_plan_id_for("starter")


def test_plan_for_whop_plan_id_maps_both_directions(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    assert plan_for_whop_plan_id("plan_pro") == "pro"
    assert plan_for_whop_plan_id("plan_unknown") is None


def test_create_checkout_session_raises_when_billing_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings(whop_api_key=""))
    with pytest.raises(BillingNotConfiguredError):
        create_checkout_session("ws-1", "starter", "user@example.com")


def test_create_checkout_session_posts_the_plan_id_and_metadata(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    fake_response = MagicMock()
    fake_response.json.return_value = {"purchase_url": "https://sandbox.whop.com/checkout/ch_xyz"}
    fake_response.raise_for_status = MagicMock()

    with patch("app.services.whop_client.httpx.post", return_value=fake_response) as mock_post:
        url = create_checkout_session("ws-1", "starter", "user@example.com")

    assert url == "https://sandbox.whop.com/checkout/ch_xyz"
    assert mock_post.call_args.args[0].endswith("/checkout_configurations")
    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"]["plan_id"] == "plan_starter"
    assert kwargs["json"]["mode"] == "payment"
    assert kwargs["json"]["metadata"] == {"workspace_id": "ws-1", "plan": "starter"}
    assert kwargs["headers"]["Authorization"] == "Bearer whop_test_fake"


def test_create_checkout_session_resolves_a_relative_purchase_url(monkeypatch):
    # Confirmed live: the API returns purchase_url as a path relative to
    # sandbox.whop.com/whop.com, not the api./sandbox-api. host requests are
    # made against -- this must not be handed to the browser as-is.
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    fake_response = MagicMock()
    fake_response.json.return_value = {"purchase_url": "/checkout/ch_xyz/"}
    fake_response.raise_for_status = MagicMock()

    with patch("app.services.whop_client.httpx.post", return_value=fake_response):
        url = create_checkout_session("ws-1", "starter", "user@example.com")

    assert url == "https://sandbox.whop.com/checkout/ch_xyz/"


def test_get_membership_fetches_by_id(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    fake_response = MagicMock()
    fake_response.json.return_value = {"id": "mem_1"}
    fake_response.raise_for_status = MagicMock()

    with patch("app.services.whop_client.httpx.get", return_value=fake_response) as mock_get:
        result = get_membership("mem_1")

    assert result == {"id": "mem_1"}
    assert mock_get.call_args.args[0].endswith("/memberships/mem_1")


def test_verify_webhook_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings(whop_webhook_secret=""))
    with pytest.raises(BillingNotConfiguredError):
        verify_webhook(b"{}", "msg_1", str(int(time.time())), "v1,bogus")


def test_verify_webhook_accepts_a_ws_prefixed_secret_used_as_raw_bytes(monkeypatch):
    # This is the actual bug hit live: a "ws_"-prefixed secret whose
    # remainder isn't valid base64 (previously: base64-decoding the whole
    # "ws_..." string raised "Incorrect padding" on every single delivery).
    # Covers the case where the key is just the raw bytes after the prefix.
    secret = "ws_07d33-not-valid-base64-f4"
    settings = _settings(whop_webhook_secret=secret)
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: settings)
    body = b'{"type": "membership.activated"}'
    timestamp = str(int(time.time()))
    stripped = secret[len("ws_") :]
    signed_content = f"msg_1.{timestamp}.".encode() + body
    sig = base64.b64encode(hmac.new(stripped.encode(), signed_content, hashlib.sha256).digest()).decode()

    event = verify_webhook(body, "msg_1", timestamp, f"v1,{sig}")

    assert event["type"] == "membership.activated"


def test_verify_webhook_accepts_a_correctly_signed_payload(monkeypatch):
    settings = _settings()
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: settings)
    body = json.dumps({"type": "membership.activated", "data": {"id": "mem_1"}}).encode()
    timestamp = str(int(time.time()))
    sig = _sign(settings.whop_webhook_secret, "msg_1", timestamp, body)

    event = verify_webhook(body, "msg_1", timestamp, sig)

    assert event["type"] == "membership.activated"


def test_verify_webhook_accepts_one_matching_signature_among_several(monkeypatch):
    # The header can carry more than one "v1,<sig>" entry (e.g. during a
    # secret rotation) -- any match should be accepted.
    settings = _settings()
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: settings)
    body = b'{"type": "x"}'
    timestamp = str(int(time.time()))
    sig = _sign(settings.whop_webhook_secret, "msg_1", timestamp, body)

    event = verify_webhook(body, "msg_1", timestamp, f"v1,not-the-real-one {sig}")

    assert event == {"type": "x"}


def test_verify_webhook_rejects_a_wrong_signature(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    timestamp = str(int(time.time()))

    with pytest.raises(ValueError):
        verify_webhook(b"{}", "msg_1", timestamp, "v1," + base64.b64encode(b"wrong").decode())


def test_verify_webhook_rejects_a_tampered_body(monkeypatch):
    settings = _settings()
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: settings)
    timestamp = str(int(time.time()))
    sig = _sign(settings.whop_webhook_secret, "msg_1", timestamp, b'{"a": 1}')

    with pytest.raises(ValueError):
        verify_webhook(b'{"a": 2}', "msg_1", timestamp, sig)


def test_verify_webhook_rejects_a_stale_timestamp(monkeypatch):
    settings = _settings()
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: settings)
    old_timestamp = str(int(time.time()) - 3600)
    body = b"{}"
    sig = _sign(settings.whop_webhook_secret, "msg_1", old_timestamp, body)

    with pytest.raises(ValueError):
        verify_webhook(body, "msg_1", old_timestamp, sig)


def test_verify_webhook_rejects_missing_headers(monkeypatch):
    monkeypatch.setattr("app.services.whop_client.get_settings", lambda: _settings())
    with pytest.raises(ValueError):
        verify_webhook(b"{}", "", "123", "")
