"""Unit tests for TracynOAuthProvider: the OAuth Authorization Server
implementation that gives MCP clients (Claude.ai, ChatGPT, Grok, and
Claude Code's connector button, which has no other way to authenticate a
non-OAuth server) a one-click "Connect" flow, without this being a
general-purpose auth system -- the token it issues IS a real Tracyn
API key, verified the same way as any other. Covers the whole cycle:
dynamic client registration, /authorize handing off to the dashboard,
the dashboard's consent decision completing or denying it, code exchange,
single-use/expiry, and bearer-token verification."""

import time
from unittest.mock import AsyncMock

import pytest
from mcp.server.auth.provider import AuthorizationParams
from mcp.shared.auth import OAuthClientInformationFull

from app.services.mcp_oauth_provider import TracynOAuthProvider


def _client(client_id="client-1", redirect_uri="https://claude.ai/api/mcp/callback") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(client_id=client_id, redirect_uris=[redirect_uri])


def _params(code_challenge="challenge123", state="state123", redirect_uri="https://claude.ai/api/mcp/callback") -> AuthorizationParams:
    return AuthorizationParams(
        state=state,
        scopes=["mcp"],
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        redirect_uri_provided_explicitly=True,
    )


@pytest.fixture
def provider() -> TracynOAuthProvider:
    return TracynOAuthProvider(dashboard_base_url="https://app.example.com/")


# -- client registration -------------------------------------------------------


@pytest.mark.anyio
async def test_register_and_get_client_round_trip(provider):
    client = _client()
    await provider.register_client(client)

    assert await provider.get_client("client-1") is client


@pytest.mark.anyio
async def test_get_client_returns_none_for_an_unknown_client(provider):
    assert await provider.get_client("nonexistent") is None


# -- authorize: hands off to the dashboard, doesn't decide anything itself ----


@pytest.mark.anyio
async def test_authorize_returns_a_url_pointing_at_the_dashboard_consent_page(provider):
    url = await provider.authorize(_client(), _params())

    assert url.startswith("https://app.example.com/oauth/authorize?request_id=")


@pytest.mark.anyio
async def test_authorize_stores_the_request_for_the_consent_page_to_retrieve(provider):
    client = _client()
    params = _params()
    url = await provider.authorize(client, params)
    request_id = url.rsplit("=", 1)[1]

    pending = provider.get_pending(request_id)

    assert pending is not None
    assert pending.client is client
    assert pending.params is params


def test_get_pending_returns_none_for_an_unknown_request_id(provider):
    assert provider.get_pending("does-not-exist") is None


# -- consent decision: complete or deny ---------------------------------------


@pytest.mark.anyio
async def test_complete_authorization_redirects_to_the_clients_own_redirect_uri_with_a_code(provider):
    url = await provider.authorize(_client(), _params(state="xyz"))
    request_id = url.rsplit("=", 1)[1]

    redirect = provider.complete_authorization(request_id, api_key="al_live_realkey", subject="ws-1")

    assert redirect is not None
    assert redirect.startswith("https://claude.ai/api/mcp/callback?")
    assert "code=" in redirect
    assert "state=xyz" in redirect


@pytest.mark.anyio
async def test_complete_authorization_consumes_the_pending_request(provider):
    url = await provider.authorize(_client(), _params())
    request_id = url.rsplit("=", 1)[1]

    provider.complete_authorization(request_id, api_key="al_live_realkey", subject="ws-1")

    assert provider.get_pending(request_id) is None
    # Completing it twice must not succeed a second time.
    assert provider.complete_authorization(request_id, api_key="al_live_other", subject="ws-1") is None


def test_complete_authorization_returns_none_for_an_unknown_request(provider):
    assert provider.complete_authorization("bogus", api_key="al_live_x", subject="ws-1") is None


@pytest.mark.anyio
async def test_deny_authorization_redirects_with_access_denied(provider):
    url = await provider.authorize(_client(), _params(state="abc"))
    request_id = url.rsplit("=", 1)[1]

    redirect = provider.deny_authorization(request_id)

    assert redirect is not None
    assert "error=access_denied" in redirect
    assert "state=abc" in redirect
    assert provider.get_pending(request_id) is None


# -- authorization code exchange ----------------------------------------------


@pytest.mark.anyio
async def test_load_and_exchange_authorization_code_hands_back_the_minted_api_key(provider):
    client = _client()
    url = await provider.authorize(client, _params(code_challenge="chal-abc"))
    request_id = url.rsplit("=", 1)[1]
    redirect = provider.complete_authorization(request_id, api_key="al_live_theminted_key", subject="ws-42")
    code = dict(part.split("=") for part in redirect.split("?", 1)[1].split("&"))["code"]

    loaded = await provider.load_authorization_code(client, code)
    assert loaded is not None
    assert loaded.code_challenge == "chal-abc"
    assert loaded.subject == "ws-42"

    token = await provider.exchange_authorization_code(client, loaded)
    assert token.access_token == "al_live_theminted_key"
    assert token.token_type == "Bearer"


@pytest.mark.anyio
async def test_load_authorization_code_rejects_a_code_issued_to_a_different_client(provider):
    client_a = _client(client_id="client-a")
    client_b = _client(client_id="client-b")
    url = await provider.authorize(client_a, _params())
    request_id = url.rsplit("=", 1)[1]
    redirect = provider.complete_authorization(request_id, api_key="al_live_x", subject="ws-1")
    code = dict(part.split("=") for part in redirect.split("?", 1)[1].split("&"))["code"]

    assert await provider.load_authorization_code(client_b, code) is None


@pytest.mark.anyio
async def test_authorization_code_is_single_use(provider):
    client = _client()
    url = await provider.authorize(client, _params())
    request_id = url.rsplit("=", 1)[1]
    redirect = provider.complete_authorization(request_id, api_key="al_live_x", subject="ws-1")
    code = dict(part.split("=") for part in redirect.split("?", 1)[1].split("&"))["code"]
    loaded = await provider.load_authorization_code(client, code)

    await provider.exchange_authorization_code(client, loaded)

    assert await provider.load_authorization_code(client, code) is None


@pytest.mark.anyio
async def test_load_authorization_code_rejects_an_expired_code(provider, monkeypatch):
    client = _client()
    url = await provider.authorize(client, _params())
    request_id = url.rsplit("=", 1)[1]
    redirect = provider.complete_authorization(request_id, api_key="al_live_x", subject="ws-1")
    code = dict(part.split("=") for part in redirect.split("?", 1)[1].split("&"))["code"]

    real_time = time.time()
    monkeypatch.setattr(time, "time", lambda: real_time + 3600)

    assert await provider.load_authorization_code(client, code) is None


# -- refresh tokens: explicitly unsupported ------------------------------------


@pytest.mark.anyio
async def test_load_refresh_token_always_returns_none(provider):
    assert await provider.load_refresh_token(_client(), "whatever") is None


@pytest.mark.anyio
async def test_exchange_refresh_token_raises_token_error(provider):
    from mcp.server.auth.provider import TokenError

    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(_client(), None, [])


# -- resource-server side: verifying a bearer token ---------------------------


@pytest.mark.anyio
async def test_load_access_token_delegates_to_verify_api_key(provider, monkeypatch):
    from app.security import WorkspaceKeyAuth

    mock_verify = AsyncMock(return_value=WorkspaceKeyAuth(workspace_id="ws-99", api_key_id="key-99"))
    monkeypatch.setattr("app.services.mcp_oauth_provider.verify_api_key", mock_verify)

    token = await provider.load_access_token("al_live_something")

    mock_verify.assert_awaited_once_with("al_live_something")
    assert token is not None
    assert token.token == "al_live_something"
    assert token.subject == "ws-99"


@pytest.mark.anyio
async def test_load_access_token_returns_none_for_an_invalid_key(provider, monkeypatch):
    monkeypatch.setattr("app.services.mcp_oauth_provider.verify_api_key", AsyncMock(return_value=None))

    assert await provider.load_access_token("al_live_bad") is None


@pytest.mark.anyio
async def test_revoke_token_is_a_no_op_and_does_not_raise(provider):
    await provider.revoke_token(None)
