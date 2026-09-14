"""Unit tests for the Stripe billing service: the BillingNotConfiguredError
fail-closed behavior (a real bug this session fixed — see the class's own
docstring for why a bare, unhandled Stripe error was worse than this), the
plan<->price-id mapping in both directions, and checkout/webhook calls
against a mocked Stripe SDK."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.stripe_client import (
    BillingNotConfiguredError,
    construct_webhook_event,
    create_checkout_session,
    plan_for_price_id,
    price_id_for_plan,
)


def _settings(**overrides):
    base = SimpleNamespace(
        stripe_secret_key="sk_test_fake",
        stripe_webhook_secret="whsec_fake",
        stripe_price_starter="price_starter",
        stripe_price_growth="price_growth",
        stripe_price_enterprise="price_enterprise",
        dashboard_base_url="https://app.example.com",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_price_id_for_plan_returns_the_configured_id(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings())
    assert price_id_for_plan("starter") == "price_starter"


def test_price_id_for_plan_rejects_an_unknown_plan(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings())
    with pytest.raises(ValueError):
        price_id_for_plan("nonexistent")


def test_price_id_for_plan_raises_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings(stripe_price_starter=""))
    with pytest.raises(BillingNotConfiguredError):
        price_id_for_plan("starter")


def test_plan_for_price_id_maps_both_directions(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings())
    assert plan_for_price_id("price_growth") == "growth"
    assert plan_for_price_id("price_unknown") is None


def test_create_checkout_session_raises_when_billing_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings(stripe_secret_key=""))
    with pytest.raises(BillingNotConfiguredError):
        create_checkout_session("ws-1", "starter", "user@example.com")


def test_create_checkout_session_returns_the_session_url(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings())
    fake_session = SimpleNamespace(url="https://checkout.stripe.com/session/xyz")

    with patch("app.services.stripe_client.stripe.checkout.Session.create", return_value=fake_session) as mock_create:
        url = create_checkout_session("ws-1", "starter", "user@example.com")

    assert url == "https://checkout.stripe.com/session/xyz"
    kwargs = mock_create.call_args.kwargs
    assert kwargs["client_reference_id"] == "ws-1"
    assert kwargs["line_items"] == [{"price": "price_starter", "quantity": 1}]
    assert kwargs["metadata"] == {"workspace_id": "ws-1", "plan": "starter"}


def test_construct_webhook_event_raises_when_billing_not_configured(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings(stripe_secret_key=""))
    with pytest.raises(BillingNotConfiguredError):
        construct_webhook_event(b"{}", "sig")


def test_construct_webhook_event_delegates_to_stripe_sdk(monkeypatch):
    monkeypatch.setattr("app.services.stripe_client.get_settings", lambda: _settings())
    fake_event = {"type": "checkout.session.completed"}

    with patch("app.services.stripe_client.stripe.Webhook.construct_event", return_value=fake_event) as mock_construct:
        event = construct_webhook_event(b'{"id": "evt_1"}', "sig_header_value")

    assert event == fake_event
    mock_construct.assert_called_once_with(b'{"id": "evt_1"}', "sig_header_value", "whsec_fake")
