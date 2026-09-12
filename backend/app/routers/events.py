from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.models.schemas import EventOut
from app.security import CurrentUser, require_workspace_member

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["events"])


@router.get("/events", response_model=list[EventOut])
async def list_events(
    workspace_id: str,
    agent_id: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    user: CurrentUser = Depends(require_workspace_member),
) -> list[EventOut]:
    """Backs the F5 audit dashboard timeline — filter by agent, action type,
    date range, and status; newest first."""
    db = get_db()
    q = db.table("events").select("*").eq("workspace_id", workspace_id)
    if agent_id:
        q = q.eq("agent_id", agent_id)
    if action_type:
        q = q.eq("action_type", action_type)
    if status:
        q = q.eq("status", status)
    if since:
        q = q.gte("created_at", since.isoformat())
    if until:
        q = q.lte("created_at", until.isoformat())
    q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
    return q.execute().data


@router.get("/events/{event_id}", response_model=EventOut)
async def get_event(workspace_id: str, event_id: str, user: CurrentUser = Depends(require_workspace_member)) -> EventOut:
    db = get_db()
    res = db.table("events").select("*").eq("id", event_id).eq("workspace_id", workspace_id).single().execute()
    return res.data
