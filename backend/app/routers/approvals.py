from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import get_settings
from app.db import get_db, run_db
from app.models.schemas import (
    ApprovalDecision,
    ApprovalOut,
    ApprovalRequestIn,
    ApprovalRequestOut,
    ApprovalStatusOut,
)
from app.security import CurrentUser, WorkspaceKeyAuth, get_api_key_auth, require_workspace_member
from app.services.approvals_service import ApprovalAlreadyDecidedError, apply_decision
from app.services.email_client import send_approval_email
from app.services.redaction import redact_pii
from app.services.slack_client import post_approval_request

router = APIRouter(prefix="/v1", tags=["approvals"])


# ---------------------------------------------------------------------------
# SDK-facing: request an approval, then poll for the decision.
# ---------------------------------------------------------------------------

@router.post("/approvals/request", response_model=ApprovalRequestOut, summary="Request human approval for an action")
async def request_approval(
    body: ApprovalRequestIn,
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> ApprovalRequestOut:
    """Called by the SDK before running a policy-flagged action. Notifies
    Slack (or falls back to email) if configured, and returns immediately
    with a `pending` approval — the caller polls
    `GET /v1/approvals/{approval_id}/status` until it resolves, which the
    SDK's `@audit.track(...)` decorator already does for you."""
    db = get_db()
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.approval_timeout_minutes)

    redacted_preview = redact_pii(body.inputs_preview)
    row = (
        await run_db(
            lambda: db.table("approvals")
            .insert(
                {
                    "workspace_id": auth.workspace_id,
                    "requested_action": {
                        "agent_name": body.agent_name,
                        "action_type": body.action_type,
                        "action_name": body.action_name,
                        "inputs_preview": redacted_preview,
                    },
                    "expires_at": expires_at.isoformat(),
                }
            )
            .execute()
        )
    ).data[0]

    ws = (
        await run_db(
            lambda: db.table("workspaces")
            .select("slack_channel_id, notify_email")
            .eq("id", auth.workspace_id)
            .single()
            .execute()
        )
    ).data

    if ws.get("slack_channel_id"):
        posted = await post_approval_request(
            channel=ws["slack_channel_id"],
            approval_id=row["id"],
            agent_name=body.agent_name,
            action_type=body.action_type,
            action_name=body.action_name,
            inputs_preview=redacted_preview,
        )
        if posted:
            channel, ts = posted
            await run_db(
                lambda: db.table("approvals")
                .update({"slack_channel": channel, "slack_message_ts": ts})
                .eq("id", row["id"])
                .execute()
            )
    elif ws.get("notify_email"):
        send_approval_email(
            ws["notify_email"], row["id"], body.agent_name, body.action_name, settings.dashboard_base_url
        )

    return ApprovalRequestOut(approval_id=row["id"], status="pending", expires_at=expires_at)


@router.get("/approvals/{approval_id}/status", response_model=ApprovalStatusOut)
async def get_approval_status(
    approval_id: str,
    auth: WorkspaceKeyAuth = Depends(get_api_key_auth),
) -> ApprovalStatusOut:
    db = get_db()
    res = (
        db.table("approvals")
        .select("id, status, decision_by, decision_note, expires_at")
        .eq("id", approval_id)
        .eq("workspace_id", auth.workspace_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Approval not found")
    return ApprovalStatusOut(**res.data)


# ---------------------------------------------------------------------------
# Dashboard-facing: queue view + manual decision (F5's "pending approvals queue")
# ---------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    workspace_id: str,
    status: str | None = None,
    user: CurrentUser = Depends(require_workspace_member),
) -> list[ApprovalOut]:
    db = get_db()
    q = db.table("approvals").select("*").eq("workspace_id", workspace_id).order("requested_at", desc=True)
    if status:
        q = q.eq("status", status)
    return q.execute().data


@router.post("/workspaces/{workspace_id}/approvals/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    workspace_id: str,
    approval_id: str,
    decision: ApprovalDecision,
    user: CurrentUser = Depends(require_workspace_member),
) -> ApprovalOut:
    try:
        updated = await apply_decision(
            approval_id=approval_id,
            decision=decision.decision,
            decision_by=user.email or user.id,
            decision_note=decision.decision_note,
            edited_action=decision.edited_action,
            workspace_id=workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalAlreadyDecidedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return updated
