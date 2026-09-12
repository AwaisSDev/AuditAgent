from contextlib import asynccontextmanager

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
