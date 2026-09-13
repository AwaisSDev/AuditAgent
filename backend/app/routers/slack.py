import json

from fastapi import APIRouter, HTTPException, Request
from slack_sdk.web.async_client import AsyncWebClient

from app.config import get_settings
from app.db import get_db, run_db
from app.services.approvals_service import ApprovalAlreadyDecidedError, apply_decision
from app.services.slack_verify import verify_slack_request

router = APIRouter(prefix="/v1/slack", tags=["slack"])

EDIT_MODAL_CALLBACK_ID = "edit_approval_modal"


@router.post("/interactions")
async def slack_interactions(request: Request) -> dict:
    """Handles Slack's interactivity callbacks — Approve / Reject / Edit
    button clicks and the Edit modal submission. Slack requires a response
    within 3 seconds, so this stays synchronous and lightweight.

    Manual setup: point the Slack app's Interactivity Request URL at
    {APP_BASE_URL}/v1/slack/interactions (see slack-app/manifest.yaml).
    """
    raw_body = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    if not verify_slack_request(raw_body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    payload = json.loads(form["payload"])
    payload_type = payload.get("type")

    if payload_type == "block_actions":
        return await _handle_block_action(payload)
    if payload_type == "view_submission":
        return await _handle_edit_submission(payload)
    return {}


async def _handle_block_action(payload: dict) -> dict:
    action = payload["actions"][0]
    action_id = action["action_id"]
    approval_id = action["value"]
    user = payload["user"]
    decision_by = f"@{user['username']}" if user.get("username") else user["id"]

    if action_id in ("approve", "reject"):
        try:
            await apply_decision(
                approval_id=approval_id,
                decision="approved" if action_id == "approve" else "rejected",
                decision_by=decision_by,
            )
        except (ValueError, ApprovalAlreadyDecidedError):
            pass  # message already reflects a terminal state; nothing to do
        return {}

    if action_id == "edit":
        db = get_db()
        approval = (
            await run_db(lambda: db.table("approvals").select("requested_action").eq("id", approval_id).single().execute())
        ).data
        settings = get_settings()
        client = AsyncWebClient(token=settings.slack_bot_token)
        await client.views_open(
            trigger_id=payload["trigger_id"],
            view={
                "type": "modal",
                "callback_id": EDIT_MODAL_CALLBACK_ID,
                "private_metadata": approval_id,
                "title": {"type": "plain_text", "text": "Edit & approve"},
                "submit": {"type": "plain_text", "text": "Approve with edits"},
                "close": {"type": "plain_text", "text": "Cancel"},
                "blocks": [
                    {
                        "type": "input",
                        "block_id": "edited_inputs",
                        "label": {"type": "plain_text", "text": "Edited inputs (JSON)"},
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "value",
                            "multiline": True,
                            "initial_value": json.dumps(
                                approval["requested_action"].get("inputs_preview", {}), indent=2
                            ),
                        },
                    },
                    {
                        "type": "input",
                        "block_id": "note",
                        "optional": True,
                        "label": {"type": "plain_text", "text": "Note (optional)"},
                        "element": {"type": "plain_text_input", "action_id": "value"},
                    },
                ],
            },
        )
        return {}

    return {}


async def _handle_edit_submission(payload: dict) -> dict:
    view = payload["view"]
    approval_id = view["private_metadata"]
    values = view["state"]["values"]
    raw_inputs = values["edited_inputs"]["value"]["value"]
    note = values.get("note", {}).get("value", {}).get("value")
    user = payload["user"]
    decision_by = f"@{user['username']}" if user.get("username") else user["id"]

    try:
        edited_inputs = json.loads(raw_inputs)
    except json.JSONDecodeError:
        return {
            "response_action": "errors",
            "errors": {"edited_inputs": "Must be valid JSON"},
        }

    try:
        await apply_decision(
            approval_id=approval_id,
            decision="approved",
            decision_by=decision_by,
            decision_note=note,
            edited_action={"inputs_preview": edited_inputs},
        )
    except (ValueError, ApprovalAlreadyDecidedError):
        pass
    return {}
