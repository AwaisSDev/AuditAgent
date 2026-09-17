"""Backs the F6 MCP server (mcp-server/). These endpoints exist because the
dashboard's equivalent routes (events.py, approvals.py) are Supabase-JWT
authenticated for a logged-in human; the MCP server instead authenticates
as a workspace via the same API key the SDK uses (get_api_key_auth) since
it's a headless integration, not a signed-in user."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import get_db, run_db
from app.models.schemas import ApprovalDecision
from app.security import WorkspaceKeyAuth, get_api_key_auth
from app.services.approvals_service import ApprovalAlreadyDecidedError, apply_decision
from app.services.claude_client import draft_answer

router = APIRouter(prefix="/v1/mcp", tags=["mcp"])


def _summarize_approval(row: dict) -> dict:
    """Flattens the nested `requested_action` blob into the fields a
    conversation actually wants to say out loud, plus a ready-made sentence
    -- so a client just relays `summary` instead of reconstructing one from
    raw JSON (see the MCP server's get_pending_approvals docstring)."""
    action = row["requested_action"]
    agent_name = action.get("agent_name", "an agent")
    action_name = action.get("action_name", "an action")
    action_type = action.get("action_type", "unknown")
    inputs_preview = action.get("inputs_preview", {})
    return {
        "approval_id": row["id"],
        "agent_name": agent_name,
        "action_name": action_name,
        "action_type": action_type,
        "inputs_preview": inputs_preview,
        "status": row["status"],
        "requested_at": row["requested_at"],
        "decided_at": row.get("decided_at"),
        "decision_by": row.get("decision_by"),
        "decision_note": row.get("decision_note"),
        "summary": (
            f"{agent_name} wants to run {action_name} ({action_type}) with {inputs_preview} "
            f"— requested {row['requested_at']}, currently {row['status']}"
        ),
    }


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
    q = q.order("created_at", desc=True).limit(limit)
    return (await run_db(q.execute)).data


@router.get("/pending-approvals")
async def pending_approvals(auth: WorkspaceKeyAuth = Depends(get_api_key_auth)) -> list[dict]:
    """Human-readable, flattened shape (see `_summarize_approval`) rather
    than the raw `approvals` row -- a conversational client (Claude via the
    MCP server) can relay `summary` directly instead of narrating nested
    JSON, and use `approval_id` with `decide_approval` below."""
    db = get_db()
    rows = (
        await run_db(
            lambda: db.table("approvals")
            .select("*")
            .eq("workspace_id", auth.workspace_id)
            .eq("status", "pending")
            .order("requested_at", desc=True)
            .execute()
        )
    ).data
    return [_summarize_approval(r) for r in rows]


@router.post("/approvals/{approval_id}/decide")
async def decide_approval_via_mcp(
    approval_id: str,
    decision: ApprovalDecision,
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> dict:
    """Lets a human approve/reject a pending request from inside a
    conversation instead of opening the dashboard. Gated on `can_review`,
    a separate flag from ordinary key privileges (see api_keys.can_review
    in schema.sql): an agent's own tracking key must never be able to
    decide its own pending approval, which is exactly what a flat
    "any API key can decide" rule would allow -- create a reviewer key in
    Settings -> API keys, then use *that* key with your MCP connector."""
    if not auth.can_review:
        raise HTTPException(
            status_code=403,
            detail=(
                "This API key isn't allowed to approve or reject actions. "
                "Create a key with 'Can approve/reject' enabled in Settings -> API keys, "
                "and use that key for your MCP connector instead."
            ),
        )
    db = get_db()
    key_row = (
        await run_db(lambda: db.table("api_keys").select("name").eq("id", auth.api_key_id).single().execute())
    ).data
    decision_by = f"{key_row['name']} (via Claude)"
    try:
        updated = await apply_decision(
            approval_id=approval_id,
            decision=decision.decision,
            decision_by=decision_by,
            decision_note=decision.decision_note,
            workspace_id=auth.workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _summarize_approval(updated)


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
        await run_db(
            lambda: db.table("events")
            .select("id, action_type, action_name, status, created_at")
            .eq("workspace_id", auth.workspace_id)
            .order("created_at", desc=True)
            .limit(25)
            .execute()
        )
    ).data
    results = []
    for question in questions:
        drafted = await draft_answer(question, candidates)
        results.append({"question": question, "answer": drafted.answer, "cited_event_ids": drafted.cited_event_ids})
    return results


@router.get("/compliance-summary")
async def compliance_summary(auth: WorkspaceKeyAuth = Depends(get_api_key_auth)) -> dict:
    db = get_db()
    ws = (
        await run_db(
            lambda: db.table("workspaces")
            .select("plan, slack_channel_id, notify_email")
            .eq("id", auth.workspace_id)
            .single()
            .execute()
        )
    ).data

    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent = (
        await run_db(
            lambda: db.table("events")
            .select("status")
            .eq("workspace_id", auth.workspace_id)
            .gte("created_at", thirty_days_ago)
            .execute()
        )
    ).data
    status_counts: dict[str, int] = {}
    for row in recent:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    pending_count = (
        await run_db(
            lambda: db.table("approvals")
            .select("id", count="exact")
            .eq("workspace_id", auth.workspace_id)
            .eq("status", "pending")
            .execute()
        )
    ).count or 0

    latest_checkpoint = (
        await run_db(
            lambda: db.table("audit_chain")
            .select("period_end, event_count, checkpoint_hash")
            .eq("workspace_id", auth.workspace_id)
            .order("period_end", desc=True)
            .limit(1)
            .execute()
        )
    ).data

    return {
        "plan": ws["plan"],
        "approvals_configured": bool(ws.get("slack_channel_id") or ws.get("notify_email")),
        "events_last_30_days_by_status": status_counts,
        "pending_approvals": pending_count,
        "latest_audit_checkpoint": latest_checkpoint[0] if latest_checkpoint else None,
    }
