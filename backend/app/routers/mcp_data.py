"""Backs the F6 MCP server (mcp-server/). These endpoints exist because the
dashboard's equivalent routes (events.py, approvals.py) are Supabase-JWT
authenticated for a logged-in human; the MCP server instead authenticates
as a workspace via the same API key the SDK uses (get_api_key_auth) since
it's a headless integration, not a signed-in user."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from app.db import get_db
from app.security import WorkspaceKeyAuth, get_api_key_auth
from app.services.claude_client import draft_answer

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


@router.get("/recent-actions")
async def recent_actions(
    limit: int = Query(default=20, le=100),
    action_type: str | None = None,
    status: str | None = None,
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> list[dict]:
    db = get_db()
    q = db.table("events").select("*").eq("workspace_id", auth.workspace_id)
    if action_type:
        q = q.eq("action_type", action_type)
    if status:
        q = q.eq("status", status)
    return q.order("created_at", desc=True).limit(limit).execute().data


@router.get("/pending-approvals")
async def pending_approvals(auth: WorkspaceKeyAuth = Depends(get_api_key_auth)) -> list[dict]:
    db = get_db()
    return (
        db.table("approvals")
        .select("*")
        .eq("workspace_id", auth.workspace_id)
        .eq("status", "pending")
        .order("requested_at", desc=True)
        .execute()
        .data
    )


@router.post("/draft-questionnaire-answers")
async def draft_questionnaire_answers(
    questions: list[str],
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> list[dict]:
    """Ad-hoc version of F4 for conversational use inside Claude — answers
    one or more questions directly against recent logs, without requiring a
    file upload first. Still just a draft: nothing here is exported or
    submitted anywhere on its own."""
    db = get_db()
    candidates = (
        db.table("events")
        .select("id, action_type, action_name, status, created_at")
        .eq("workspace_id", auth.workspace_id)
        .order("created_at", desc=True)
        .limit(25)
        .execute()
        .data
    )
    results = []
    for question in questions:
        drafted = await draft_answer(question, candidates)
        results.append({"question": question, "answer": drafted.answer, "cited_event_ids": drafted.cited_event_ids})
    return results


@router.get("/compliance-summary")
async def compliance_summary(auth: WorkspaceKeyAuth = Depends(get_api_key_auth)) -> dict:
    db = get_db()
    ws = db.table("workspaces").select("plan, slack_channel_id, notify_email").eq("id", auth.workspace_id).single().execute().data

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent = (
        db.table("events")
        .select("status")
        .eq("workspace_id", auth.workspace_id)
        .gte("created_at", thirty_days_ago)
        .execute()
        .data
    )
    status_counts: dict[str, int] = {}
    for row in recent:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    pending_count = (
        db.table("approvals")
        .select("id", count="exact")
        .eq("workspace_id", auth.workspace_id)
        .eq("status", "pending")
        .execute()
        .count
        or 0
    )

    latest_checkpoint = (
        db.table("audit_chain")
        .select("period_end, event_count, checkpoint_hash")
        .eq("workspace_id", auth.workspace_id)
        .order("period_end", desc=True)
        .limit(1)
        .execute()
        .data
    )

    return {
        "plan": ws["plan"],
        "approvals_configured": bool(ws.get("slack_channel_id") or ws.get("notify_email")),
        "events_last_30_days_by_status": status_counts,
        "pending_approvals": pending_count,
        "latest_audit_checkpoint": latest_checkpoint[0] if latest_checkpoint else None,
    }
