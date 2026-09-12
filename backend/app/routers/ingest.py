from datetime import datetime, timezone

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db
from app.models.schemas import EventIn, EventIngestResponse
from app.security import WorkspaceKeyAuth, get_api_key_auth
from app.services.plan_limits import event_limit

router = APIRouter(prefix="/v1", tags=["ingest"])


@router.post("/events", response_model=EventIngestResponse, status_code=202)
async def ingest_event(
    event: EventIn,
    request: Request,
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> EventIngestResponse:
    """Accepts an event from the SDK and returns immediately.

    Redaction, classification, agent upsert, policy re-check, and the
    immutable insert into `events` all happen asynchronously in the arq
    worker — see worker/tasks.py::process_event_intake. This keeps the
    SDK's network round trip short and means a slow Presidio/Haiku pass
    never blocks the caller's request.
    """
    db = get_db()

    ws = db.table("workspaces").select("plan").eq("id", auth.workspace_id).single().execute().data
    limit = event_limit(ws["plan"])
    if limit is not None:
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        used = (
            db.table("events")
            .select("id", count="exact")
            .eq("workspace_id", auth.workspace_id)
            .gte("created_at", month_start)
            .execute()
            .count
            or 0
        )
        if used >= limit:
            raise HTTPException(status_code=402, detail=f"Monthly event limit reached ({limit}). Upgrade your plan to keep logging.")

    intake = (
        db.table("event_intake")
        .insert(
            {
                "workspace_id": auth.workspace_id,
                "api_key_id": auth.api_key_id,
                "payload": event.model_dump(mode="json"),
            }
        )
        .execute()
    )
    intake_id = intake.data[0]["id"]

    arq_pool: ArqRedis | None = request.app.state.arq_pool
    if arq_pool is None:
        raise HTTPException(status_code=503, detail="Background processing (Redis) is not configured on this server yet.")
    await arq_pool.enqueue_job("process_event_intake", intake_id)

    return EventIngestResponse(intake_id=intake_id, accepted=True)
