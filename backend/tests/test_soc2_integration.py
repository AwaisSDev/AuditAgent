"""Integration tests for the SOC2 mapping router. Also guards a real bug
found while reading this file: get_soc2_controls had no auth dependency at
all despite its own docstring claiming "still requires login" — it was the
only unauthenticated route in the app. Fixed in app/routers/soc2.py; the
first test below is what would have caught it."""

import pytest
from fastapi.testclient import TestClient

from app.data.soc2_controls import SOC2_CONTROLS
from app.main import app
from app.security import CurrentUser, get_current_user, require_workspace_member

WORKSPACE_ID = "ws-1"


def test_get_soc2_controls_requires_authentication():
    with TestClient(app) as c:
        resp = c.get("/v1/soc2/controls")
    assert resp.status_code == 401


def test_get_soc2_controls_returns_the_static_list():
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    try:
        with TestClient(app) as c:
            resp = c.get("/v1/soc2/controls")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert len(resp.json()) == len(SOC2_CONTROLS)
    assert resp.json()[0]["control_id"] == SOC2_CONTROLS[0].control_id


def test_export_soc2_csv():
    app.dependency_overrides[require_workspace_member] = lambda: CurrentUser(id="user-1", email="reviewer@example.com")
    try:
        with TestClient(app) as c:
            resp = c.get(f"/v1/workspaces/{WORKSPACE_ID}/soc2/export.csv")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert SOC2_CONTROLS[0].control_id in resp.text


def test_export_soc2_csv_requires_workspace_membership():
    with TestClient(app) as c:
        resp = c.get(f"/v1/workspaces/{WORKSPACE_ID}/soc2/export.csv")
    assert resp.status_code == 401
