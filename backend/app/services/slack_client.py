"""Posts approval requests to Slack with Approve / Reject / Edit buttons.

Manual setup required — see docs/MANUAL_SETUP.md:
  1. Create a Slack app at https://api.slack.com/apps (from the manifest in
     slack-app/manifest.yaml).
  2. Install it to the workspace, copy the Bot Token into SLACK_BOT_TOKEN.
  3. Copy the Signing Secret into SLACK_SIGNING_SECRET (used to verify
     interactivity callbacks in routers/slack.py).
  4. Point the app's Interactivity Request URL at
     {APP_BASE_URL}/v1/slack/interactions.
  5. Invite the bot to the channel each workspace wants approvals posted in,
     and store that channel id on the workspace (dashboard setting).
"""

from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.config import get_settings


def _blocks(approval_id: str, agent_name: str, action_type: str, action_name: str, inputs_preview: dict[str, Any]) -> list[dict]:
    preview_lines = "\n".join(f"*{k}*: {v}" for k, v in list(inputs_preview.items())[:10]) or "_(no inputs)_"
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f":robot_face: *{agent_name}* wants to run *{action_name}* "
                    f"(`{action_type}`) and needs approval.\n\n{preview_lines}"
                ),
            },
        },
        {
            "type": "actions",
            "block_id": f"approval_{approval_id}",
            "elements": [
                {
                    "type": "button",
                    "style": "primary",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "action_id": "approve",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "style": "danger",
                    "text": {"type": "plain_text", "text": "Reject"},
                    "action_id": "reject",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit..."},
                    "action_id": "edit",
                    "value": approval_id,
                },
            ],
        },
    ]


async def post_approval_request(
    channel: str,
    approval_id: str,
    agent_name: str,
    action_type: str,
    action_name: str,
    inputs_preview: dict[str, Any],
) -> tuple[str, str] | None:
    """Returns (channel, message_ts) so decisions can update the message in place."""
    settings = get_settings()
    if not settings.slack_bot_token:
        return None
    client = AsyncWebClient(token=settings.slack_bot_token)
    response = await client.chat_postMessage(
        channel=channel,
        text=f"{agent_name} wants to run {action_name} — approval needed",
        blocks=_blocks(approval_id, agent_name, action_type, action_name, inputs_preview),
    )
    return response["channel"], response["ts"]


async def update_message_with_decision(channel: str, ts: str, summary_text: str) -> None:
    settings = get_settings()
    if not settings.slack_bot_token:
        return
    client = AsyncWebClient(token=settings.slack_bot_token)
    await client.chat_update(
        channel=channel,
        ts=ts,
        text=summary_text,
        blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": summary_text}}],
    )
