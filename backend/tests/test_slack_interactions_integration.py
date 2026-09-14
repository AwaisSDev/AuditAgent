"""Integration tests for POST /v1/slack/interactions: signature
verification gates everything else, Approve/Reject button clicks call
into the shared approvals service (and silently no-op on a stale/already-
decided approval rather than erroring back to Slack), the Edit button
opens a modal pre-filled with the current inputs, and the modal's
submission both applies the edit and validates the JSON a user typed."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.approvals_service import ApprovalAlreadyDecidedError

WORKSPACE_ID = "ws-1"


def _slack_form(payload: dict) -> dict:
    return {"payload": json.dumps(payload)}


@pytest.fixture(autouse=True)
def _bypass_signature_check(monkeypatch):
    monkeypatch.setattr("app.routers.slack.verify_slack_request", lambda *a, **kw: True)


def test_interactions_rejects_an_invalid_signature(monkeypatch):
    monkeypatch.setattr("app.routers.slack.verify_slack_request", lambda *a, **kw: False)
    with TestClient(app) as c:
        resp = c.post("/v1/slack/interactions", data=_slack_form({"type": "block_actions"}))
    assert resp.status_code == 401


def test_approve_button_applies_the_decision():
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "approve", "value": "appr-1"}],
        "user": {"id": "U123", "username": "reviewer"},
    }
    with patch("app.routers.slack.apply_decision", new=AsyncMock()) as mock_apply:
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200
    mock_apply.assert_awaited_once_with(approval_id="appr-1", decision="approved", decision_by="@reviewer")


def test_reject_button_applies_the_decision():
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "reject", "value": "appr-1"}],
        "user": {"id": "U123"},  # no username -> falls back to the user id
    }
    with patch("app.routers.slack.apply_decision", new=AsyncMock()) as mock_apply:
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200
    mock_apply.assert_awaited_once_with(approval_id="appr-1", decision="rejected", decision_by="U123")


def test_approve_on_an_already_decided_approval_is_a_silent_no_op():
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "approve", "value": "appr-1"}],
        "user": {"id": "U123"},
    }
    with patch("app.routers.slack.apply_decision", new=AsyncMock(side_effect=ApprovalAlreadyDecidedError("already approved"))):
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200


def test_edit_button_opens_a_prefilled_modal(monkeypatch):
    approval_row = {"requested_action": {"inputs_preview": {"amount": 49.99}}}
    fake_db = SimpleNamespace(
        table=lambda name: SimpleNamespace(
            select=lambda *_a, **_kw: SimpleNamespace(
                eq=lambda *_a, **_kw: SimpleNamespace(single=lambda: SimpleNamespace(execute=lambda: SimpleNamespace(data=approval_row)))
            )
        )
    )
    monkeypatch.setattr("app.routers.slack.get_db", lambda: fake_db)
    monkeypatch.setattr("app.routers.slack.get_settings", lambda: SimpleNamespace(slack_bot_token="xoxb-fake"))

    payload = {
        "type": "block_actions",
        "actions": [{"action_id": "edit", "value": "appr-1"}],
        "user": {"id": "U123"},
        "trigger_id": "trigger-1",
    }
    with patch("app.routers.slack.AsyncWebClient") as mock_cls:
        mock_cls.return_value.views_open = AsyncMock()
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200
    view = mock_cls.return_value.views_open.call_args.kwargs["view"]
    assert view["private_metadata"] == "appr-1"
    assert "49.99" in view["blocks"][0]["element"]["initial_value"]


def test_edit_modal_submission_applies_the_edit_with_note():
    payload = {
        "type": "view_submission",
        "view": {
            "private_metadata": "appr-1",
            "state": {
                "values": {
                    "edited_inputs": {"value": {"value": '{"amount": 10}'}},
                    "note": {"value": {"value": "reduced per customer request"}},
                }
            },
        },
        "user": {"id": "U123", "username": "reviewer"},
    }
    with patch("app.routers.slack.apply_decision", new=AsyncMock()) as mock_apply:
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200
    mock_apply.assert_awaited_once_with(
        approval_id="appr-1",
        decision="approved",
        decision_by="@reviewer",
        decision_note="reduced per customer request",
        edited_action={"inputs_preview": {"amount": 10}},
    )


def test_edit_modal_submission_rejects_malformed_json_inputs():
    payload = {
        "type": "view_submission",
        "view": {
            "private_metadata": "appr-1",
            "state": {"values": {"edited_inputs": {"value": {"value": "not json"}}}},
        },
        "user": {"id": "U123"},
    }
    with patch("app.routers.slack.apply_decision", new=AsyncMock()) as mock_apply:
        with TestClient(app) as c:
            resp = c.post("/v1/slack/interactions", data=_slack_form(payload))

    assert resp.status_code == 200
    assert resp.json()["response_action"] == "errors"
    mock_apply.assert_not_called()
