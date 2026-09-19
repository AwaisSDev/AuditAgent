from contextlib import asynccontextmanager

import sentry_sdk
from tracyn_mcp.server import configure_backend_url, configure_data_provider, configure_oauth, http_app as mcp_http_app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.arq_pool import close_arq_pool, get_arq_pool
from app.config import get_settings
from app.routers import agents, approvals, auth, billing, events, ingest, mcp_data, oauth, policies, questionnaires, slack, soc2, workspaces
from app.services.mcp_oauth_provider import get_oauth_provider
from app.services.mcp_provider import BackendDataProvider

_settings = get_settings()
# No-op until SENTRY_DSN is set to a real DSN from a Sentry project -- see
# app/config.py::Settings.sentry_dsn.
if _settings.sentry_dsn:
    sentry_sdk.init(
        dsn=_settings.sentry_dsn,
        environment=_settings.sentry_environment,
        traces_sample_rate=0.1,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the pool at startup when lifespan actually runs (plain uvicorn,
    # Railway). When this app is mounted under another ASGI app (the
    # Hugging Face Gradio Space — see space_app.py), Starlette never fires
    # lifespan for a mounted sub-app, so routes fall back to creating the
    # pool lazily on first use via app.arq_pool.get_arq_pool().
    await get_arq_pool()
    yield
    await close_arq_pool()


app = FastAPI(
    title="Tracyn API",
    version="0.1.0",
    lifespan=lifespan,
    description="""
Compliance infrastructure for AI agent teams — logging, human approvals,
an immutable audit trail, and evidence-pack generation.

## Authentication

Two separate schemes, depending on the caller:

- **SDK / API-key routes** (`/v1/events`, `/v1/approvals/request`,
  `/v1/approvals/{approval_id}/status`, `/v1/sdk/policy`, `/v1/mcp/*`) —
  send `Authorization: Bearer <your al_live_... key>`. Create a key from
  the dashboard's Settings page.
- **Dashboard / human routes** (everything under `/v1/workspaces/{id}/...`
  except the SDK-facing ones above) — send
  `Authorization: Bearer <Supabase session JWT>`, the same token the
  dashboard's own browser session uses.

## Where to start

Most integrations only ever need the Python SDK (`pip install tracyn`)
rather than calling this API directly — see its README for the
`@audit.track(...)` decorator. This reference is for the SDK's own
internals, the MCP server, or a direct integration in another language.
""",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(ingest.router)
app.include_router(approvals.router)
app.include_router(policies.router)
app.include_router(agents.router)
app.include_router(events.router)
app.include_router(workspaces.router)
app.include_router(questionnaires.router)
app.include_router(billing.router)
app.include_router(slack.router)
app.include_router(soc2.router)
app.include_router(mcp_data.router)
app.include_router(oauth.router)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


# F6, remote/multi-tenant: exposes the same four tools as mcp_data.router
# over MCP's Streamable HTTP transport instead of plain REST, so claude.ai,
# ChatGPT, and Grok's custom-connector flows can reach it (none of them can
# reach a stdio-only server — see docs/PRODUCTION_READINESS.md). A caller
# can authenticate either way: paste an existing Tracyn API key
# directly as the bearer token (still works, unchanged), or go through the
# real OAuth flow below, which a plain static token can't offer -- some
# clients' own "Connect" buttons (Claude Code's, notably) only know how to
# do OAuth and have no field to paste a token into at all. Either way ends
# up authenticated as a real, revokable API key, checked the same way.
configure_backend_url(settings.app_base_url)
configure_data_provider(BackendDataProvider())
configure_oauth(
    get_oauth_provider(),
    issuer_url=settings.app_base_url,
    resource_server_url=f"{settings.app_base_url}/mcp",
)
# Mounted at "/" (not "/mcp"), and registered LAST so every route above
# always wins first: the OAuth discovery/registration/authorize/token
# routes this generates (see configure_oauth) are only correct at
# predictable, often-root-relative paths -- RFC 9728's well-known
# protected-resource path in particular is defined relative to the
# origin's root, not to whatever sub-path the resource itself lives
# under. Mounting the whole thing under "/mcp" instead would nest every
# one of those paths an extra level (discovered as
# /mcp/.well-known/oauth-protected-resource/mcp, /mcp/authorize, etc.)
# while the auto-generated metadata still advertises the un-nested
# versions -- confirmed by actually running the full discovery ->
# registration -> authorize -> token exchange handshake and watching it
# 404 before this fix. The actual MCP protocol endpoint itself still ends
# up at exactly "/mcp" (see streamable_http_path in tracyn_mcp/server.py),
# same external URL as before -- only the OAuth routes' position changes.
app.mount("/", mcp_http_app())
