"""Email fallback for approvals when a workspace has no Slack channel configured.

Manual setup: create a Resend account (https://resend.com), verify a sending
domain, and set RESEND_API_KEY. Free tier is plenty for MVP volume.
"""

import resend

from app.config import get_settings


def send_approval_email(to_email: str, approval_id: str, agent_name: str, action_name: str, dashboard_url: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [to_email],
            "subject": f"Approval needed: {agent_name} wants to run {action_name}",
            "html": (
                f"<p><b>{agent_name}</b> wants to run <b>{action_name}</b> and needs your approval.</p>"
                f"<p><a href='{dashboard_url}/approvals/{approval_id}'>Review in Tracyn →</a></p>"
                f"<p>This request auto-denies in 30 minutes if nobody responds.</p>"
            ),
        }
    )


def send_timeout_notice(to_email: str, agent_name: str, action_name: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        return
    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [to_email],
            "subject": f"Auto-denied: {agent_name} / {action_name}",
            "html": f"<p>Nobody responded within 30 minutes, so the request for <b>{agent_name}</b> to run <b>{action_name}</b> was automatically denied.</p>",
        }
    )
