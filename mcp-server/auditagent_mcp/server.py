"""F6 — AuditAgent MCP server.

Exposes a workspace's logs, approvals, and compliance posture as MCP tools
so a developer can ask about their agent conversationally from an MCP
client (Claude, ChatGPT, Grok, ...), instead of opening the dashboard.
This is a thin client over the same backend the SDK and dashboard use
(app/routers/mcp_data.py) — no logic is duplicated here.

Two ways to run this, both exposing the same five tools:

- `run()` — stdio transport, for Claude Desktop/Claude Code running the
  server as a local subprocess. Single workspace per process: reads
  AUDITAGENT_API_KEY from the environment once at call time.
- `http_app()` — an ASGI app (Streamable HTTP transport), for hosting
  remotely so claude.ai, ChatGPT, and Grok's custom-connector flows can
  reach it over the network (a hosted chat product has no local machine
  to spawn a stdio subprocess on, so stdio is not reachable from any of
  them — see PRODUCTION_READINESS.md). Multi-tenant: every request must
  carry the caller's own AuditAgent API key as its bearer token, which the
  `_BearerTokenMiddleware` below picks up per-request; nothing server-wide
  is shared between callers. Meant to be mounted onto an existing host
  app (see backend/app/main.py), not run standalone.
"""

import asyncio
import contextvars
import os
from typing import Protocol

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import OAuthAuthorizationServerProvider, ProviderTokenVerifier
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from auditagent_mcp import client

mcp = FastMCP(
    "auditagent",
    # The default "/mcp" -- the host app (backend/app/main.py) mounts
    # http_app() at "/" (not "/mcp"), so this path is what actually puts
    # the MCP protocol endpoint at "/mcp" externally. When OAuth is
    # configured (configure_oauth), this ASGI app also carries the
    # discovery/registration/authorize/token routes, which by contrast
    # need to sit at the true root, not nested under this path -- see the
    # comment on app.mount(...) in main.py for why mounting under "/mcp"
    # itself doesn't work once OAuth is involved.
    streamable_http_path="/mcp",
    # DNS-rebinding protection (Host/Origin header allowlisting) exists for
    # setups that trust same-origin browser requests; ours doesn't -- every
    # request must carry a real AuditAgent API key as its bearer token,
    # checked by the backend itself, so Host-header matching would only
    # add a brittle, easy-to-misconfigure second gate (and it auto-enables
    # with a localhost-only allowlist whenever FastMCP's default `host`
    # looks like localhost, which would reject every real request once
    # this is mounted and served from a real public hostname).
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# Set per-request by _BearerTokenMiddleware (HTTP transport only); stdio
# transport has no such request, so tools fall back to the environment
# variable below via _resolve_api_key(). Only used when configure_oauth()
# below has NOT been called -- once a real auth_server_provider is
# configured, FastMCP's own bearer-auth middleware (see http_app()) takes
# over token extraction/verification instead, for both real OAuth-issued
# tokens and a manually-pasted static API key alike (same load_access_token
# check either way -- see configure_oauth's docstring).
_current_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_api_key", default=None)


def _resolve_api_key() -> str:
    # When configure_oauth() is active, FastMCP's own AuthenticationMiddleware
    # already validated the caller's token (via the provider's
    # load_access_token) and stashed it here before this tool ever runs.
    access_token = get_access_token()
    if access_token:
        return access_token.token
    key = _current_api_key.get()
    if key:
        return key
    key = os.environ.get("AUDITAGENT_API_KEY")
    if not key:
        raise RuntimeError(
            "No AuditAgent API key available. For local/stdio use, set the "
            "AUDITAGENT_API_KEY environment variable. For the hosted remote "
            "server, connect with your AuditAgent API key as the bearer token."
        )
    return key


def configure_backend_url(base_url: str) -> None:
    """Points the MCP tools' outbound calls (client.py) at the host app's
    own real origin, instead of client.py's placeholder default. Needed
    because this package is mounted *inside* the same backend it's a thin
    client for (see backend/app/main.py) — without this, every tool call
    goes out over the network to a domain nobody configured, and fails.
    Call this once at startup, same place as configure_oauth.

    Superseded by configure_data_provider when that's also called (see
    below) -- kept as a fallback for a standalone deployment of this
    package that still wants a real default instead of the placeholder."""
    client.set_base_url(base_url)


class DataProvider(Protocol):
    """What configure_data_provider needs implemented, matching client.py's
    four functions but as async methods on one object instead of module-
    level functions -- lets a host app hand in something backed by direct
    in-process calls (see backend/app/services/mcp_provider.py) instead of
    client.py's real HTTP round trip."""

    async def get_recent_actions(
        self, api_key: str, *, limit: int = 20, action_type: str | None = None, status: str | None = None
    ) -> list[dict]: ...

    async def get_pending_approvals(self, api_key: str) -> list[dict]: ...

    async def decide_approval(self, api_key: str, approval_id: str, decision: str, note: str | None = None) -> dict: ...

    async def draft_questionnaire_answers(self, api_key: str, questions: list[str]) -> list[dict]: ...

    async def get_compliance_summary(self, api_key: str) -> dict: ...


_data_provider: DataProvider | None = None


def configure_data_provider(provider: DataProvider) -> None:
    """Makes every tool call this object directly instead of going through
    client.py's httpx call to configure_backend_url's address.

    Exists because that address, even once correctly configured, is this
    same server's own public hostname -- calling it from inside the same
    process is a self-referential round trip out through the host's
    network ingress and back in, which on Hugging Face Spaces in practice
    stalls for the client's full timeout rather than completing quickly
    (observed directly: a plain REST call to the same endpoint from
    outside the container returned in ~2s, while the identical call made
    by a tool from inside it took 30s and still timed out). Call this once
    at startup, same place as configure_oauth/configure_backend_url --
    when both this and configure_backend_url have been called, this one
    wins."""
    global _data_provider
    _data_provider = provider


def configure_oauth(
    provider: OAuthAuthorizationServerProvider,
    *,
    issuer_url: str,
    resource_server_url: str,
) -> None:
    """Wires a real OAuth Authorization Server implementation onto the
    shared MCP server instance, replacing the plain bearer-token-passthrough
    model with the full discovery/registration/authorize/token flow that
    MCP clients' one-click "Connect" buttons expect (rather than requiring
    every user to manually paste a static token, which some clients --
    Claude Code's own connector UI, notably -- have no way to do at all;
    see PRODUCTION_READINESS.md).

    The token this issues (see the provider's exchange_authorization_code)
    is a real AuditAgent API key, not a separate credential type -- so
    load_access_token's job is just verifying an API key exactly like the
    backend already does elsewhere, and the *same* verification correctly
    accepts a pre-existing key a user pastes in directly too, without going
    through the OAuth dance at all. Both paths end up authenticated via
    this one mechanism (FastMCP's own bearer-auth middleware populates
    get_access_token() for both), which is why _resolve_api_key() only
    needs to check one place once this has been called.

    Mutates the already-constructed `mcp` singleton's auth-related
    attributes rather than constructing a second FastMCP instance --
    streamable_http_app() (see http_app()) reads them fresh on every call,
    confirmed by reading its source, so this is safe as long as it's
    called before http_app(). Meant to be called at most once, by the
    host application (see backend/app/main.py), which supplies a provider
    backed by its own database and Supabase-authenticated consent page --
    this package has no opinion on how consent/login itself works.
    """
    mcp._auth_server_provider = provider
    mcp._token_verifier = ProviderTokenVerifier(provider)
    mcp.settings.auth = AuthSettings(
        issuer_url=issuer_url,
        resource_server_url=resource_server_url,
        # Every token our own load_access_token accepts is, by construction,
        # only ever valid for this one server (it's a lookup in our own
        # api_keys table) -- there's no other "resource" a token could be
        # confused with, so there's nothing for audience-checking to add.
        validate_token_resource=False,
        client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=["mcp"], default_scopes=["mcp"]),
        revocation_options=RevocationOptions(enabled=True),
    )


@mcp.tool()
async def get_recent_actions(limit: int = 20, action_type: str | None = None, status: str | None = None) -> list[dict]:
    """Get the most recent logged AI agent actions for this workspace.

    Args:
        limit: max number of events to return (default 20, max 100).
        action_type: optional filter, e.g. "external" or "data_access".
        status: optional filter, one of completed/approved/rejected/denied_timeout/error.
    """
    api_key = _resolve_api_key()
    if _data_provider is not None:
        return await _data_provider.get_recent_actions(api_key, limit=limit, action_type=action_type, status=status)
    return await anyio.to_thread.run_sync(lambda: client.get_recent_actions(api_key, limit=limit, action_type=action_type, status=status))


@mcp.tool()
async def get_pending_approvals() -> list[dict]:
    """Get all approval requests currently awaiting a human decision.

    Each item includes a ready-made `summary` sentence (e.g. "ops-agent
    wants to run bulk_delete_records (external) with {...} — requested
    ..., currently pending") plus the flattened fields it's built from
    (agent_name, action_name, action_type, inputs_preview, status,
    requested_at) and an `approval_id` to pass to `decide_approval`.
    """
    api_key = _resolve_api_key()
    if _data_provider is not None:
        return await _data_provider.get_pending_approvals(api_key)
    return await anyio.to_thread.run_sync(lambda: client.get_pending_approvals(api_key))


@mcp.tool()
async def decide_approval(approval_id: str, decision: str, note: str | None = None) -> dict:
    """Approve or reject a pending approval request, as the human reviewing
    it in this conversation -- an alternative to clicking Approve/Reject in
    the dashboard.

    Requires a *reviewer* API key (created in Settings -> API keys with
    "Can approve/reject" enabled). An ordinary agent-tracking key is
    refused on purpose: an agent must never be able to decide its own
    pending request, which is exactly what letting any key approve would
    allow.

    Args:
        approval_id: the id from get_pending_approvals.
        decision: "approved" or "rejected".
        note: optional free-text reason, shown in the dashboard's audit trail.
    """
    api_key = _resolve_api_key()
    if _data_provider is not None:
        return await _data_provider.decide_approval(api_key, approval_id, decision, note)
    return await anyio.to_thread.run_sync(lambda: client.decide_approval(api_key, approval_id, decision, note))


@mcp.tool()
async def draft_questionnaire_answers(questions: list[str]) -> list[dict]:
    """Draft answers to one or more security-questionnaire-style questions,
    grounded in this workspace's actual logged events, with cited event ids.

    This is a draft only — nothing is submitted or exported. For a full
    questionnaire file (PDF/CSV/XLSX), upload it in the AuditAgent dashboard
    instead; this tool is for one-off conversational questions.

    Args:
        questions: one or more questions, e.g. ["Do you log all AI agent actions?"]
    """
    api_key = _resolve_api_key()
    if _data_provider is not None:
        return await _data_provider.draft_questionnaire_answers(api_key, questions)
    return await anyio.to_thread.run_sync(lambda: client.draft_questionnaire_answers(api_key, questions))


@mcp.tool()
async def get_compliance_summary() -> dict:
    """Get a snapshot of this workspace's compliance posture: plan, whether
    Slack/email approval routing is configured, event counts by status over
    the last 30 days, how many approvals are pending, and the most recent
    audit-chain checkpoint (proof the event log hasn't been altered since)."""
    api_key = _resolve_api_key()
    if _data_provider is not None:
        return await _data_provider.get_compliance_summary(api_key)
    return await anyio.to_thread.run_sync(lambda: client.get_compliance_summary(api_key))


# FastMCP's streamable_http_app() declares its own `lifespan=` (it enters
# `mcp.session_manager.run()` to set up an internal anyio task group), but
# that only fires if the ASGI server treats this app as *the* app it
# serves directly. Mounted under another app -- FastAPI in
# backend/app/main.py, itself possibly mounted again under Gradio on the
# Hugging Face Space deployment -- Starlette never forwards lifespan
# startup into a mounted sub-application, at any level of nesting. This is
# the same problem backend/app/arq_pool.py already documents and solves
# for the Redis pool, but the fix can't be the same: a plain connection
# pool has no task affinity, while `session_manager.run()`'s task group
# does -- entering it inline from whichever per-request task happens to
# be first, then having a *different* request's task reach back into it,
# violates anyio's structured concurrency (cancel scopes are bound to the
# task that entered them) and raises "Attempted to exit cancel scope in a
# different task than it was entered in". So instead this runs the context
# manager inside one dedicated background task that's never touched by
# any request's own task -- requests only ever call into the already-
# running task group's `handle_request`, never enter or exit it themselves.
_session_manager_ready = asyncio.Event()
_session_manager_task: asyncio.Task | None = None
_session_manager_start_lock = asyncio.Lock()


async def _run_session_manager_forever() -> None:
    async with mcp.session_manager.run():
        _session_manager_ready.set()
        await asyncio.Event().wait()  # blocks forever; process exit is this deployment's real shutdown


async def _ensure_session_manager_started() -> None:
    global _session_manager_task
    if _session_manager_task is not None:
        await _session_manager_ready.wait()
        return
    async with _session_manager_start_lock:
        if _session_manager_task is not None:  # another request won the race while we waited
            await _session_manager_ready.wait()
            return
        _session_manager_task = asyncio.create_task(_run_session_manager_forever())
        await _session_manager_ready.wait()


class _BearerTokenMiddleware:
    """Reads the caller's `Authorization: Bearer <token>` header and makes
    it available to tool handlers via `_current_api_key`. Not OAuth: the
    token IS the caller's real AuditAgent API key, validated downstream by
    the real backend (app/routers/mcp_data.py's get_api_key_auth) exactly
    like the SDK's own requests — this middleware only extracts and scopes
    it per-request, it does not itself decide whether the key is valid.

    Also ensures the session manager has actually been started (see
    _ensure_session_manager_started) before the first request is let
    through, since this middleware wraps every request to the mounted app
    regardless of how it's deployed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        await _ensure_session_manager_started()

        token = None
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                raw = value.decode("latin-1")
                if raw.lower().startswith("bearer "):
                    token = raw[7:].strip()
                break

        reset_token = _current_api_key.set(token)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_api_key.reset(reset_token)


def http_app() -> ASGIApp:
    """ASGI app for the hosted, multi-tenant remote deployment (Streamable
    HTTP transport). Mount this onto a host application rather than
    running it standalone — see backend/app/main.py."""
    return _BearerTokenMiddleware(mcp.streamable_http_app())


def run() -> None:
    """Local stdio entry point (Claude Desktop, Claude Code) — unchanged
    single-workspace-per-process behavior."""
    mcp.run()


if __name__ == "__main__":
    run()
