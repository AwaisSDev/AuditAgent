from contextlib import asynccontextmanager

from auditagent_mcp.server import http_app as mcp_http_app
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.arq_pool import close_arq_pool, get_arq_pool
from app.config import get_settings
from app.routers import agents, approvals, auth, billing, events, ingest, mcp_data, policies, questionnaires, slack, soc2, workspaces


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
    title="AuditAgent API",
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

Most integrations only ever need the Python SDK (`pip install AudAgent`)
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

# F6, remote/multi-tenant: exposes the same four tools as mcp_data.router
# over MCP's Streamable HTTP transport instead of plain REST, so claude.ai,
# ChatGPT, and Grok's custom-connector flows can reach it (none of them can
# reach a stdio-only server — see docs/PRODUCTION_READINESS.md). Each
# caller authenticates with their own AuditAgent API key as the bearer
# token; nothing server-wide is shared between callers (see
# auditagent_mcp.server._BearerTokenMiddleware).
app.mount("/mcp", mcp_http_app())


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
