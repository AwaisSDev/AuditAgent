"""Verifies the MCP server registers exactly the four tools F6 promises,
under the expected names, that each tool function is a thin,
argument-preserving pass-through to the corresponding client.* call (now
with the resolved api_key threaded through) -- and covers the two API-key
resolution paths (stdio env var vs. the HTTP bearer-token contextvar) plus
the middleware that sets the latter per-request, since that's what makes
the hosted server multi-tenant rather than sharing one key across callers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from auditagent_mcp import server


def test_all_four_tools_are_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_recent_actions",
        "get_pending_approvals",
        "draft_questionnaire_answers",
        "get_compliance_summary",
    }


def test_get_recent_actions_forwards_its_arguments_and_the_resolved_key(monkeypatch):
    monkeypatch.setattr(server, "_resolve_api_key", lambda: "al_live_resolved")
    mock = MagicMock(return_value=[{"id": "evt-1"}])
    monkeypatch.setattr(server.client, "get_recent_actions", mock)

    result = server.get_recent_actions(limit=5, action_type="external", status="completed")

    mock.assert_called_once_with("al_live_resolved", limit=5, action_type="external", status="completed")
    assert result == [{"id": "evt-1"}]


def test_get_pending_approvals_forwards_to_the_client(monkeypatch):
    monkeypatch.setattr(server, "_resolve_api_key", lambda: "al_live_resolved")
    mock = MagicMock(return_value=[{"id": "appr-1"}])
    monkeypatch.setattr(server.client, "get_pending_approvals", mock)

    assert server.get_pending_approvals() == [{"id": "appr-1"}]
    mock.assert_called_once_with("al_live_resolved")


def test_draft_questionnaire_answers_forwards_the_question_list(monkeypatch):
    monkeypatch.setattr(server, "_resolve_api_key", lambda: "al_live_resolved")
    mock = MagicMock(return_value=[{"question": "q", "answer": "a", "cited_event_ids": []}])
    monkeypatch.setattr(server.client, "draft_questionnaire_answers", mock)

    result = server.draft_questionnaire_answers(["Do you log actions?"])

    mock.assert_called_once_with("al_live_resolved", ["Do you log actions?"])
    assert result[0]["answer"] == "a"


def test_get_compliance_summary_forwards_to_the_client(monkeypatch):
    monkeypatch.setattr(server, "_resolve_api_key", lambda: "al_live_resolved")
    mock = MagicMock(return_value={"plan": "free"})
    monkeypatch.setattr(server.client, "get_compliance_summary", mock)

    assert server.get_compliance_summary() == {"plan": "free"}
    mock.assert_called_once_with("al_live_resolved")


@pytest.mark.parametrize(
    "tool_name",
    ["get_recent_actions", "get_pending_approvals", "draft_questionnaire_answers", "get_compliance_summary"],
)
def test_every_tool_has_a_non_empty_docstring(tool_name):
    # MCP clients show this text to the model/user as the tool's description --
    # an empty one would make the tool effectively undiscoverable.
    fn = getattr(server, tool_name)
    assert fn.__doc__ and len(fn.__doc__.strip()) > 20


# -- API-key resolution: stdio env var vs. HTTP contextvar -------------------


def test_resolve_api_key_uses_the_contextvar_when_set(monkeypatch):
    monkeypatch.delenv("AUDITAGENT_API_KEY", raising=False)
    token = server._current_api_key.set("al_live_from_request")
    try:
        assert server._resolve_api_key() == "al_live_from_request"
    finally:
        server._current_api_key.reset(token)


def test_resolve_api_key_falls_back_to_the_environment_variable(monkeypatch):
    monkeypatch.setenv("AUDITAGENT_API_KEY", "al_live_from_env")
    assert server._current_api_key.get() is None  # not set by any request in this test
    assert server._resolve_api_key() == "al_live_from_env"


def test_resolve_api_key_raises_when_neither_is_available(monkeypatch):
    monkeypatch.delenv("AUDITAGENT_API_KEY", raising=False)
    assert server._current_api_key.get() is None
    with pytest.raises(RuntimeError, match="No AuditAgent API key"):
        server._resolve_api_key()


def test_contextvar_takes_priority_over_the_environment_variable(monkeypatch):
    # The hosted/remote path must never silently fall back to a shared
    # server-wide key just because one happens to be set in the process
    # environment -- the per-request caller's key always wins.
    monkeypatch.setenv("AUDITAGENT_API_KEY", "al_live_server_wide")
    token = server._current_api_key.set("al_live_per_request")
    try:
        assert server._resolve_api_key() == "al_live_per_request"
    finally:
        server._current_api_key.reset(token)


# -- _BearerTokenMiddleware ---------------------------------------------------
#
# _BearerTokenMiddleware.__call__ also calls _ensure_session_manager_started(),
# which -- for real -- spawns a background task that enters
# mcp.session_manager.run() and then blocks forever by design (see its own
# docstring: the process exiting is this deployment's actual shutdown).
# That's correct for the real hosted server, but exercising it unmocked in
# a unit test leaves a permanent, never-cancelled task running against
# whichever event loop this test happened to run on -- which then hangs
# pytest's own teardown once a *later* test tears down a different loop.
# These tests are about header extraction and contextvar scoping, not
# session-manager startup, so mock that part out.


@pytest.fixture(autouse=True)
def _skip_real_session_manager_startup(monkeypatch):
    monkeypatch.setattr(server, "_ensure_session_manager_started", AsyncMock())


@pytest.mark.anyio
async def test_bearer_token_middleware_extracts_the_token_into_the_contextvar():
    captured = {}

    async def inner_app(scope, receive, send):
        captured["key_seen_by_tool"] = server._current_api_key.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = server._BearerTokenMiddleware(inner_app)
    scope = {"type": "http", "headers": [(b"authorization", b"Bearer al_live_remote_caller")]}

    await middleware(scope, AsyncMock(), AsyncMock())

    assert captured["key_seen_by_tool"] == "al_live_remote_caller"
    # And it must not leak into the next request once this one is done.
    assert server._current_api_key.get() is None


@pytest.mark.anyio
async def test_bearer_token_middleware_passes_through_with_no_token_when_header_is_absent():
    captured = {}

    async def inner_app(scope, receive, send):
        captured["key_seen_by_tool"] = server._current_api_key.get()

    middleware = server._BearerTokenMiddleware(inner_app)
    await middleware({"type": "http", "headers": []}, AsyncMock(), AsyncMock())

    assert captured["key_seen_by_tool"] is None


@pytest.mark.anyio
async def test_bearer_token_middleware_ignores_non_bearer_auth_headers():
    captured = {}

    async def inner_app(scope, receive, send):
        captured["key_seen_by_tool"] = server._current_api_key.get()

    middleware = server._BearerTokenMiddleware(inner_app)
    await middleware({"type": "http", "headers": [(b"authorization", b"Basic dXNlcjpwYXNz")]}, AsyncMock(), AsyncMock())

    assert captured["key_seen_by_tool"] is None


@pytest.mark.anyio
async def test_bearer_token_middleware_ignores_non_http_scopes():
    inner_app = AsyncMock()
    middleware = server._BearerTokenMiddleware(inner_app)

    await middleware({"type": "lifespan"}, AsyncMock(), AsyncMock())

    inner_app.assert_awaited_once()


def test_http_app_is_wrapped_with_the_bearer_token_middleware():
    app = server.http_app()
    assert isinstance(app, server._BearerTokenMiddleware)
