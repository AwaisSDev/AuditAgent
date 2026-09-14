"""Integration tests for the billing router: checkout-session creation
(including both failure paths that this session's fix turned from an
unhandled 500 into a real error the browser can show), and the webhook
handler for all three subscribed event types."""

from unittest.mock import patch

import pytest
import stripe as stripe_sdk
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, require_workspace_member
from app.services.stripe_client import BillingNotConfiguredError

WORKSPACE_ID = "ws-1"


class _FakeQuery:
    def __init__(self, table, op, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters = {}

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def execute(self):
        rows = self.table.rows

        if self.op == "upsert":
            key = self.payload["workspace_id"]
            rows.setdefault("subscriptions", {})[key] = {**rows.get("subscriptions", {}).get(key, {}), **self.payload}
            return None

        if self.op == "update":
            matches = [r for r in rows.get("workspaces", {}).values() if all(r.get(k) == v for k, v in self.filters.items())]
            for r in matches:
                r.update(self.payload)
            return None

        raise AssertionError(f"unhandled op {self.op}")


class _FakeTable:
    def __init__(self, all_rows, name):
        self.all_rows = all_rows
        self.name = name

    @property
    def rows(self):
        return self.all_rows

    def upsert(self, payload, on_conflict=None):
        return _FakeQuery(self, "upsert", payload)

    def update(self, payload):
        q = _FakeQuery(self, "update", payload)
        q._table_name = self.name
        return q


class _FakeDb:
    def __init__(self):
        self._tables = {"subscriptions": {}, "workspaces": {WORKSPACE_ID: {"id": WORKSPACE_ID, "plan": "free"}}}

    def table(self, name):
        return _FakeTable(self._tables, name)


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDb()
    monkeypatch.setattr("app.routers.billing.get_db", lambda: db)
    return db


@pytest.fixture
def client(fake_db):
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="owner@example.com")
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_checkout_requires_the_user_to_have_an_email(monkeypatch):
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email=None)
    try:
        with TestClient(app) as c:
            resp = c.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_checkout_surfaces_billing_not_configured_as_503(client):
    with patch("app.routers.billing.create_checkout_session", side_effect=BillingNotConfiguredError("no key")):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    assert resp.status_code == 503


def test_checkout_surfaces_a_stripe_error_as_502(client):
    stripe_error = stripe_sdk.error.StripeError("Your card was declined.")
    with patch("app.routers.billing.create_checkout_session", side_effect=stripe_error):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    assert resp.status_code == 502
    assert "declined" in resp.json()["detail"]


def test_checkout_returns_the_session_url_on_success(client):
    with patch("app.routers.billing.create_checkout_session", return_value="https://checkout.stripe.com/xyz"):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    assert resp.status_code == 200
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/xyz"


def test_webhook_rejects_an_invalid_signature(fake_db):
    with patch("app.routers.billing.construct_webhook_event", side_effect=ValueError("bad signature")):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "bogus"})
    assert resp.status_code == 400


def test_webhook_checkout_completed_activates_the_plan(fake_db):
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"workspace_id": WORKSPACE_ID, "plan": "starter"},
                "customer": "cus_123",
                "subscription": "sub_123",
            }
        },
    }
    with patch("app.routers.billing.construct_webhook_event", return_value=event):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "starter"
    assert fake_db._tables["subscriptions"][WORKSPACE_ID]["status"] == "active"


def test_webhook_subscription_deleted_downgrades_to_free(fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "growth"
    event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "metadata": {"workspace_id": WORKSPACE_ID},
                "customer": "cus_123",
                "id": "sub_123",
                "status": "canceled",
                "items": {"data": []},
            }
        },
    }
    with patch("app.routers.billing.construct_webhook_event", return_value=event):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "free"


def test_webhook_ignores_unrelated_event_types(fake_db):
    event = {"type": "invoice.paid", "data": {"object": {}}}
    with patch("app.routers.billing.construct_webhook_event", return_value=event):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/webhook", content=b"{}", headers={"stripe-signature": "sig"})
    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "free"
