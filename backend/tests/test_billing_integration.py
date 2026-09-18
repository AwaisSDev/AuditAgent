"""Integration tests for the billing router: checkout-session creation
(including both failure paths that turn an unhandled 500 into a real
error the browser can show), and the Whop webhook handler."""

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import CurrentUser, require_workspace_member
from app.services.whop_client import BillingNotConfiguredError

WORKSPACE_ID = "ws-1"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table, op, payload=None):
        self.table = table
        self.name = table.name
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
            matches = [r for r in rows.get(self.name, {}).values() if all(r.get(k) == v for k, v in self.filters.items())]
            for r in matches:
                r.update(self.payload)
            return None

        if self.op == "select":
            table_rows = rows.get(self.name, {})
            matches = [r for r in table_rows.values() if all(r.get(k) == v for k, v in self.filters.items())]
            return _FakeResult(matches)

        raise AssertionError(f"unhandled op {self.op}")


class _FakeTable:
    def __init__(self, all_rows, name):
        self.all_rows = all_rows
        self.name = name

    @property
    def rows(self):
        return self.all_rows

    def select(self, *_a, **_kw):
        return _FakeQuery(self, "select")

    def upsert(self, payload, on_conflict=None):
        return _FakeQuery(self, "upsert", payload)

    def update(self, payload):
        return _FakeQuery(self, "update", payload)


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


def test_checkout_surfaces_a_whop_error_as_502(client):
    whop_error = httpx.HTTPStatusError("declined", request=httpx.Request("POST", "https://x"), response=httpx.Response(402, text="card declined"))
    with patch("app.routers.billing.create_checkout_session", side_effect=whop_error):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    assert resp.status_code == 502
    assert "declined" in resp.json()["detail"]


def test_checkout_returns_the_session_url_and_configuration_id_on_success(client):
    session = {"id": "ch_xyz", "purchase_url": "https://sandbox.whop.com/checkout/ch_xyz"}
    with patch("app.routers.billing.create_checkout_session", return_value=session):
        resp = client.post(f"/v1/workspaces/{WORKSPACE_ID}/billing/checkout", json={"plan": "starter"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["checkout_url"] == "https://sandbox.whop.com/checkout/ch_xyz"
    # Default whop_api_base_url (config.py) is the sandbox endpoint.
    assert body["environment"] == "sandbox"
    assert body["checkout_configuration_id"] == "ch_xyz"


def _whop_headers():
    return {"webhook-id": "msg_1", "webhook-timestamp": "1700000000", "webhook-signature": "v1,sig"}


def test_webhook_rejects_an_invalid_signature(fake_db):
    with patch("app.routers.billing.verify_webhook", side_effect=ValueError("bad signature")):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())
    assert resp.status_code == 400


def test_webhook_surfaces_billing_not_configured_as_503(fake_db):
    with patch("app.routers.billing.verify_webhook", side_effect=BillingNotConfiguredError("no secret")):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())
    assert resp.status_code == 503


def test_webhook_membership_activated_sets_the_plan(fake_db):
    event = {"type": "membership.activated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {"workspace_id": WORKSPACE_ID, "plan": "starter"}, "plan": {"id": "plan_starter"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), patch("app.routers.billing.get_membership", return_value=membership):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "starter"
    assert fake_db._tables["subscriptions"][WORKSPACE_ID]["status"] == "active"
    assert fake_db._tables["subscriptions"][WORKSPACE_ID]["whop_membership_id"] == "mem_123"


def test_webhook_membership_activated_falls_back_to_plan_id_lookup(fake_db):
    # No "plan" in metadata (e.g. an older checkout config) -- must still
    # resolve the plan from the Whop plan id itself.
    event = {"type": "membership.activated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {"workspace_id": WORKSPACE_ID}, "plan": {"id": "plan_pro_id"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), \
         patch("app.routers.billing.get_membership", return_value=membership), \
         patch("app.routers.billing.plan_for_whop_plan_id", return_value="pro"):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "pro"


def test_webhook_falls_back_to_the_checkout_configuration_when_membership_has_no_metadata(fake_db):
    # Whop's docs claim a checkout configuration's metadata is copied onto
    # the membership it produces -- this test is for when that turns out
    # not to hold (confirmed live once already for two other claims about
    # this same API): the membership itself carries none, so the handler
    # must fetch the checkout configuration and use its metadata instead.
    event = {"type": "membership.activated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {}, "plan": {"id": "plan_starter_id"}, "checkout_configuration_id": "ch_1"}
    checkout_config = {"id": "ch_1", "metadata": {"workspace_id": WORKSPACE_ID, "plan": "starter"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), \
         patch("app.routers.billing.get_membership", return_value=membership), \
         patch("app.routers.billing.get_checkout_configuration", return_value=checkout_config) as get_config:
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "starter"
    get_config.assert_called_once_with("ch_1")


def test_webhook_cancels_the_previous_membership_on_upgrade(fake_db):
    # Confirmed live: without this, buying a new plan while a different one
    # is still active just adds a second active membership billing in
    # parallel instead of replacing it.
    fake_db._tables["subscriptions"][WORKSPACE_ID] = {"workspace_id": WORKSPACE_ID, "whop_membership_id": "mem_old", "status": "active"}
    event = {"type": "membership.activated", "data": {"id": "mem_new"}}
    membership = {"id": "mem_new", "metadata": {"workspace_id": WORKSPACE_ID, "plan": "pro"}, "plan": {"id": "plan_pro"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), \
         patch("app.routers.billing.get_membership", return_value=membership), \
         patch("app.routers.billing.cancel_membership") as mock_cancel:
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    mock_cancel.assert_called_once_with("mem_old")
    assert fake_db._tables["subscriptions"][WORKSPACE_ID]["whop_membership_id"] == "mem_new"
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "pro"


def test_webhook_does_not_cancel_when_reactivating_the_same_membership(fake_db):
    fake_db._tables["subscriptions"][WORKSPACE_ID] = {"workspace_id": WORKSPACE_ID, "whop_membership_id": "mem_123", "status": "active"}
    event = {"type": "membership.activated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {"workspace_id": WORKSPACE_ID, "plan": "starter"}, "plan": {"id": "plan_starter"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), \
         patch("app.routers.billing.get_membership", return_value=membership), \
         patch("app.routers.billing.cancel_membership") as mock_cancel:
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    mock_cancel.assert_not_called()


def test_webhook_still_activates_the_new_plan_if_canceling_the_old_one_fails(fake_db):
    fake_db._tables["subscriptions"][WORKSPACE_ID] = {"workspace_id": WORKSPACE_ID, "whop_membership_id": "mem_old", "status": "active"}
    event = {"type": "membership.activated", "data": {"id": "mem_new"}}
    membership = {"id": "mem_new", "metadata": {"workspace_id": WORKSPACE_ID, "plan": "pro"}, "plan": {"id": "plan_pro"}}
    cancel_error = httpx.HTTPStatusError("already canceled", request=httpx.Request("POST", "https://x"), response=httpx.Response(404))
    with patch("app.routers.billing.verify_webhook", return_value=event), \
         patch("app.routers.billing.get_membership", return_value=membership), \
         patch("app.routers.billing.cancel_membership", side_effect=cancel_error):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "pro"


def test_webhook_membership_deactivated_downgrades_to_free(fake_db):
    fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] = "pro"
    event = {"type": "membership.deactivated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {"workspace_id": WORKSPACE_ID}}
    with patch("app.routers.billing.verify_webhook", return_value=event), patch("app.routers.billing.get_membership", return_value=membership):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())

    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "free"
    assert fake_db._tables["subscriptions"][WORKSPACE_ID]["status"] == "canceled"


def test_webhook_ignores_unrelated_event_types(fake_db):
    event = {"type": "payment.succeeded", "data": {"id": "pay_1"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), patch("app.routers.billing.get_membership") as get_membership:
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())
    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "free"
    get_membership.assert_not_called()


def test_webhook_ignores_a_membership_with_no_workspace_metadata(fake_db):
    event = {"type": "membership.activated", "data": {"id": "mem_123"}}
    membership = {"id": "mem_123", "metadata": {}, "plan": {"id": "plan_unknown"}}
    with patch("app.routers.billing.verify_webhook", return_value=event), patch("app.routers.billing.get_membership", return_value=membership):
        with TestClient(app) as c:
            resp = c.post("/v1/billing/whop/webhook", content=b"{}", headers=_whop_headers())
    assert resp.status_code == 200
    assert fake_db._tables["workspaces"][WORKSPACE_ID]["plan"] == "free"
    assert WORKSPACE_ID not in fake_db._tables["subscriptions"]
