"""F6 — AuditAgent MCP server.

Exposes a workspace's logs, approvals, and compliance posture as MCP tools
so a developer can ask about their agent conversationally from an MCP
client (Claude, ChatGPT, Grok, ...), instead of opening the dashboard.
This is a thin client over the same backend the SDK and dashboard use
(app/routers/mcp_data.py) — no logic is duplicated here.

Two ways to run this, both exposing the same four tools:

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

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from auditagent_mcp import client

mcp = FastMCP(
    "auditagent",
    # Not the default "/mcp": the host app (backend/app/main.py) mounts
    # http_app() at "/mcp" itself -- without this, the route would resolve
    # to "/mcp/mcp" instead of "/mcp".
    streamable_http_path="/",
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
# variable below via _resolve_api_key().
_current_api_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_api_key", default=None)


def _resolve_api_key() -> str:
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


@mcp.tool()
def get_recent_actions(limit: int = 20, action_type: str | None = None, status: str | None = None) -> list[dict]:
    """Get the most recent logged AI agent actions for this workspace.

    Args:
        limit: max number of events to return (default 20, max 100).
        action_type: optional filter, e.g. "external" or "data_access".
        status: optional filter, one of completed/approved/rejected/denied_timeout/error.
    """
    return client.get_recent_actions(_resolve_api_key(), limit=limit, action_type=action_type, status=status)


@mcp.tool()
def get_pending_approvals() -> list[dict]:
    """Get all approval requests currently awaiting a human decision."""
    return client.get_pending_approvals(_resolve_api_key())


@mcp.tool()
def draft_questionnaire_answers(questions: list[str]) -> list[dict]:
    """Draft answers to one or more security-questionnaire-style questions,
    grounded in this workspace's actual logged events, with cited event ids.

    This is a draft only — nothing is submitted or exported. For a full
    questionnaire file (PDF/CSV/XLSX), upload it in the AuditAgent dashboard
    instead; this tool is for one-off conversational questions.

    Args:
        questions: one or more questions, e.g. ["Do you log all AI agent actions?"]
    """
    return client.draft_questionnaire_answers(_resolve_api_key(), questions)


@mcp.tool()
def get_compliance_summary() -> dict:
    """Get a snapshot of this workspace's compliance posture: plan, whether
    Slack/email approval routing is configured, event counts by status over
    the last 30 days, how many approvals are pending, and the most recent
    audit-chain checkpoint (proof the event log hasn't been altered since)."""
    return client.get_compliance_summary(_resolve_api_key())


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
