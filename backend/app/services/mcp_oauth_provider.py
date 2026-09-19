"""OAuth 2.0 Authorization Server implementation backing the MCP server's
one-click "Connect" flow (see tracyn_mcp.server.configure_oauth,
routers/oauth.py, and the dashboard's app/(app)/oauth/authorize page).

Deliberately minimal: this isn't a general-purpose OAuth provider, just a
thin login/consent wrapper around Tracyn's own accounts. The "access
token" handed out at the end of the flow IS a real Tracyn API key,
verified by the exact same check (security.verify_api_key) as every other
API-key-authed route -- so a user who instead pastes an existing key
directly (Claude Code's --header method, skipping this flow entirely)
authenticates exactly the same way, through the same table.

Storage here is in-memory (module-level state via the singleton below),
not the database: everything held is short-lived by design -- a client
registration lasts for the life of this process (re-registering on
restart is a normal, harmless part of the RFC 7591 flow, not an error
case), and a pending consent request or an issued-but-not-yet-exchanged
authorization code lives for minutes. The one thing that IS persisted is
the API key itself, in the same `api_keys` table every other key lives
in, so a token issued through this flow survives a restart of this
process fine; only a mid-flight, not-yet-completed login would need to be
retried, which is normal for OAuth in general (codes are meant to be
single-use and short-lived everywhere, not just here).
"""

import secrets
import time
from dataclasses import dataclass, field
from functools import lru_cache

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.config import get_settings
from app.db import get_db, run_db
from app.security import generate_api_key, verify_api_key

_REQUEST_TTL_SECONDS = 15 * 60  # time to actually complete login + consent in the browser
_CODE_TTL_SECONDS = 5 * 60  # time to exchange the code for a token -- standard short-lived practice


class _TracynAuthCode(AuthorizationCode):
    """Adds the actual, already-minted API key this code will hand out on
    exchange. Not part of the base protocol's model; subclassing to add a
    field the framework itself never renders is explicitly supported (see
    AuthorizationCode's own module docstring in the mcp package)."""

    api_key: str


@dataclass
class PendingAuthorization:
    """One in-flight /authorize request, waiting on the dashboard's
    consent page (routers/oauth.py) to complete it."""

    client: OAuthClientInformationFull
    params: AuthorizationParams
    created_at: float = field(default_factory=time.monotonic)


class TracynOAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self, *, dashboard_base_url: str) -> None:
        self._dashboard_base_url = dashboard_base_url.rstrip("/")
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._pending: dict[str, PendingAuthorization] = {}
        self._codes: dict[str, _TracynAuthCode] = {}

    # -- client registration (RFC 7591) --------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    # -- authorization: hand off to our own consent page ----------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self._sweep_expired()
        request_id = secrets.token_urlsafe(24)
        self._pending[request_id] = PendingAuthorization(client=client, params=params)
        return f"{self._dashboard_base_url}/oauth/authorize?request_id={request_id}"

    def get_pending(self, request_id: str) -> PendingAuthorization | None:
        """Used by routers/oauth.py's GET endpoint to render the consent
        page, and by its POST endpoint to complete or deny the flow."""
        self._sweep_expired()
        return self._pending.get(request_id)

    def complete_authorization(self, request_id: str, *, api_key: str, subject: str) -> str | None:
        """Called once the user approves, having already minted `api_key`
        for the workspace they picked. Returns the URL to send the user's
        browser back to (the MCP client's own redirect_uri), or None if
        the request_id is unknown or has expired."""
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return None

        code = secrets.token_urlsafe(32)  # ~256 bits, comfortably over RFC 6749's 128-bit floor
        self._codes[code] = _TracynAuthCode(
            code=code,
            scopes=pending.params.scopes or ["mcp"],
            expires_at=time.time() + _CODE_TTL_SECONDS,
            client_id=pending.client.client_id,
            code_challenge=pending.params.code_challenge,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            resource=pending.params.resource,
            subject=subject,
            api_key=api_key,
        )
        return construct_redirect_uri(str(pending.params.redirect_uri), code=code, state=pending.params.state)

    def deny_authorization(self, request_id: str) -> str | None:
        pending = self._pending.pop(request_id, None)
        if pending is None:
            return None
        return construct_redirect_uri(str(pending.params.redirect_uri), error="access_denied", state=pending.params.state)

    def _sweep_expired(self) -> None:
        cutoff = time.monotonic() - _REQUEST_TTL_SECONDS
        expired = [rid for rid, p in self._pending.items() if p.created_at < cutoff]
        for rid in expired:
            del self._pending[rid]

    # -- authorization code exchange ------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> _TracynAuthCode | None:
        code = self._codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            del self._codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: _TracynAuthCode
    ) -> OAuthToken:
        del self._codes[authorization_code.code]  # single use
        return OAuthToken(
            access_token=authorization_code.api_key,
            token_type="Bearer",
            scope=" ".join(authorization_code.scopes),
        )

    # -- refresh tokens: not supported. Tracyn API keys don't expire, so
    # there's nothing to refresh -- a client that never receives a
    # refresh_token simply keeps using the same access token indefinitely,
    # which is the correct behavior here, not a missing feature.

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        raise TokenError(
            error="unsupported_grant_type",
            error_description="Tracyn API keys do not expire; there is no refresh token to exchange.",
        )

    # -- resource-server side: verifying a bearer token -----------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        auth = await verify_api_key(token)
        if auth is None:
            return None
        return AccessToken(token=token, client_id="tracyn-api-key", scopes=["mcp"], subject=auth.workspace_id)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Deliberately a no-op: `token` here is a real, already-persisted
        # API key row -- revoking it is the same "Revoke" action already
        # exposed on the dashboard's Settings > API Keys page, not
        # something this OAuth-specific code path should also reach into
        # the database to do independently.
        return None


async def mint_api_key_for_workspace(workspace_id: str, *, name: str, created_by: str) -> str:
    """Creates a real, persisted API key for the given workspace -- used
    when a user approves an OAuth consent request, so the token an MCP
    client ends up with is a first-class key indistinguishable from one
    created by hand in Settings (visible there, independently revokable,
    same last_used_at tracking)."""
    full_key, prefix, key_hash = generate_api_key()
    db = get_db()
    await run_db(
        lambda: db.table("api_keys")
        .insert(
            {
                "workspace_id": workspace_id,
                "name": name,
                "key_prefix": prefix,
                "key_hash": key_hash,
                "created_by": created_by,
            }
        )
        .execute()
    )
    return full_key


@lru_cache
def get_oauth_provider() -> TracynOAuthProvider:
    return TracynOAuthProvider(dashboard_base_url=get_settings().dashboard_base_url)
