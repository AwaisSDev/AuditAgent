"""Unit tests for the thin HTTP client backing every MCP tool: request
shape (params/body sent to the real backend endpoints in
app/routers/mcp_data.py), auth header, error propagation on a non-2xx
response, and the "no API key configured" failure mode. Network calls are
faked via httpx.MockTransport -- no real server involved."""

import httpx
import pytest

from auditagent_mcp import client


def _install_transport(monkeypatch, handler):
    def _client():
        if not client.API_KEY:
            raise RuntimeError("AUDITAGENT_API_KEY is not set — see README.md for setup.")
        return httpx.Client(
            base_url=client.BASE_URL,
            headers={"Authorization": f"Bearer {client.API_KEY}"},
            timeout=30.0,
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(client, "_client", _client)


def test_client_raises_when_no_api_key_is_configured(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", None)
    with pytest.raises(RuntimeError, match="AUDITAGENT_API_KEY"):
        client.get_pending_approvals()


def test_get_recent_actions_sends_expected_params_and_auth_header(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=[{"id": "evt-1", "status": "completed"}])

    _install_transport(monkeypatch, handler)

    result = client.get_recent_actions(limit=5, action_type="external", status="completed")

    assert result == [{"id": "evt-1", "status": "completed"}]
    assert captured["auth"] == "Bearer al_live_test_key"
    assert "/v1/mcp/recent-actions" in captured["url"]
    assert "limit=5" in captured["url"]
    assert "action_type=external" in captured["url"]
    assert "status=completed" in captured["url"]


def test_get_recent_actions_omits_unset_optional_filters(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    _install_transport(monkeypatch, handler)

    client.get_recent_actions()

    assert "action_type" not in captured["url"]
    assert "status" not in captured["url"]
    assert "limit=20" in captured["url"]


def test_get_pending_approvals_parses_the_response(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    _install_transport(monkeypatch, lambda req: httpx.Response(200, json=[{"id": "appr-1", "status": "pending"}]))

    assert client.get_pending_approvals() == [{"id": "appr-1", "status": "pending"}]


def test_draft_questionnaire_answers_posts_the_question_list(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["method"] = request.method
        return httpx.Response(200, json=[{"question": "Do you log actions?", "answer": "Yes.", "cited_event_ids": []}])

    _install_transport(monkeypatch, handler)

    result = client.draft_questionnaire_answers(["Do you log actions?"])

    assert captured["method"] == "POST"
    assert b"Do you log actions?" in captured["body"]
    assert result[0]["answer"] == "Yes."


def test_get_compliance_summary_parses_the_response(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    summary = {"plan": "growth", "approvals_configured": True, "events_last_30_days_by_status": {}, "pending_approvals": 0, "latest_audit_checkpoint": None}
    _install_transport(monkeypatch, lambda req: httpx.Response(200, json=summary))

    assert client.get_compliance_summary() == summary


def test_a_non_2xx_response_raises(monkeypatch):
    monkeypatch.setattr(client, "API_KEY", "al_live_test_key")
    _install_transport(monkeypatch, lambda req: httpx.Response(401, json={"detail": "Invalid API key"}))

    with pytest.raises(httpx.HTTPStatusError):
        client.get_pending_approvals()
