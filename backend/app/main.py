from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import agents, approvals, auth, billing, events, ingest, mcp_data, policies, questionnaires, slack, soc2, workspaces


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    try:
        app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception as exc:  # noqa: BLE001 — deliberately broad: Redis being down must never crash the API
        # Redis is required for the ingest/questionnaire pipelines (see
        # worker/), but its absence shouldn't take down the whole API —
        # every other route (workspaces, agents, policies, approvals,
        # billing, SOC2) has no dependency on it.
        print(f"WARNING: could not connect to Redis at startup ({exc}); ingest and questionnaire uploads will be unavailable.")
        app.state.arq_pool = None
    yield
    if app.state.arq_pool is not None:
        await app.state.arq_pool.close()


app = FastAPI(title="AuditAgent API", version="0.1.0", lifespan=lifespan)

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


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
