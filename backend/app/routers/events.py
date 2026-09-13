from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.db import get_db, run_db
from app.models.schemas import EventOut
from app.security import CurrentUser, require_workspace_member
from app.services.events_export import build_events_csv

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["events"])

# Same cap the dashboard timeline uses per page, but exports are a one-shot
# pull rather than a paginated view — this is a generous ceiling (matches
# the free plan's whole monthly event allowance) rather than a real limit.
_EXPORT_ROW_LIMIT = 10_000


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
    return (await run_db(q.execute)).data


@router.get("/events/export.csv")
async def export_events_csv(
    workspace_id: str,
    agent_id: str | None = None,
    action_type: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    user: CurrentUser = Depends(require_workspace_member),
) -> StreamingResponse:
    """The raw hash-chained log, not the SOC2 mapping or an evidence pack —
    for backup, an auditor handoff, or feeding this workspace's own data into
    another tool. Same filters as the dashboard timeline; no pagination,
    since this is a one-shot pull rather than a paginated view (see
    _EXPORT_ROW_LIMIT). This route is registered ahead of GET /events/{event_id}
    below — Starlette matches path routes in registration order, and
    "export.csv" would otherwise be captured as a literal event_id.
    """
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
    q = q.order("created_at", desc=True).limit(_EXPORT_ROW_LIMIT)
    events = (await run_db(q.execute)).data
    content = build_events_csv(events)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditagent-events.csv"},
    )


@router.get("/events/{event_id}", response_model=EventOut)
async def get_event(workspace_id: str, event_id: str, user: CurrentUser = Depends(require_workspace_member)) -> EventOut:
    db = get_db()
    res = await run_db(lambda: db.table("events").select("*").eq("id", event_id).eq("workspace_id", workspace_id).single().execute())
    return res.data
