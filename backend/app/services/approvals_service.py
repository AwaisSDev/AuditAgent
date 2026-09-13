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
) -> dict[str, Any]:
    db = get_db()
    res = db.table("approvals").select("*").eq("id", approval_id).single().execute()
    if not res.data:
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
    result = db.table("approvals").update(update).eq("id", approval_id).eq("status", "pending").execute().data
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
