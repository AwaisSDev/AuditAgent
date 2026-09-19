"""Shared decision logic used by both the dashboard's decide endpoint
(routers/approvals.py) and the Slack interactivity webhook
(routers/slack.py) — a decision can come from either place."""

from datetime import datetime, timezone
from typing import Any, Literal

from app.db import get_db
from app.services.slack_client import update_message_with_decision


class ApprovalAlreadyDecidedError(Exception):
    pass


async def apply_decision(
    approval_id: str,
    decision: Literal["approved", "rejected"],
    decision_by: str,
    decision_note: str | None = None,
    edited_action: dict[str, Any] | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """`workspace_id` scopes the lookup/update to a specific tenant. The
    dashboard's decide endpoint always passes it (the caller only proved
    membership in *a* workspace via `require_workspace_member`, not that
    `approval_id` belongs to that same workspace — without this check, any
    member of any workspace who obtained another tenant's approval_id could
    approve/reject it). The Slack webhook path omits it: Slack's own
    signature verification is what authenticates that call, and the
    approval_id there comes only from a button Tracyn itself posted."""
    db = get_db()
    q = db.table("approvals").select("*").eq("id", approval_id)
    if workspace_id is not None:
        q = q.eq("workspace_id", workspace_id)
    res = q.single().execute()
    if not res.data:
        # Same "not found" whether the id doesn't exist or belongs to a
        # different workspace — never confirm cross-tenant existence.
        raise ValueError("Approval not found")
    approval = res.data
    if approval["status"] != "pending":
        raise ApprovalAlreadyDecidedError(f"Approval already {approval['status']}")

    update: dict[str, Any] = {
        "status": decision,
        "decision_by": decision_by,
        "decision_note": decision_note,
        "decided_at": datetime.now(timezone.utc).isoformat(),
    }
    if edited_action:
        merged = {**approval["requested_action"], **edited_action}
        update["requested_action"] = merged

    # Condition the UPDATE on `status = pending` so this is a single atomic
    # compare-and-swap at the database level, not a separate check-then-act:
    # two concurrent decisions (e.g. a Slack click racing a dashboard click)
    # must not both succeed with the second one silently overwriting the
    # first while both callers see a 200.
    update_q = db.table("approvals").update(update).eq("id", approval_id).eq("status", "pending")
    if workspace_id is not None:
        update_q = update_q.eq("workspace_id", workspace_id)
    result = update_q.execute().data
    if not result:
        raise ApprovalAlreadyDecidedError("Approval was already decided by someone else")
    updated = result[0]

    if approval.get("slack_channel") and approval.get("slack_message_ts"):
        verb = "approved" if decision == "approved" else "rejected"
        who = decision_by
        summary = f":white_check_mark: *{verb.title()}* by {who}" if decision == "approved" else f":no_entry: *{verb.title()}* by {who}"
        if decision_note:
            summary += f"\n> {decision_note}"
        await update_message_with_decision(approval["slack_channel"], approval["slack_message_ts"], summary)

    return updated
