"""Whop billing -- replaces Stripe as the active checkout provider.

Setup (see docs/MANUAL_SETUP.md once this ships): create two plans on
whop.com (or sandbox.whop.com for testing) named Starter and Pro, copy
their ids into WHOP_PLAN_STARTER / WHOP_PLAN_PRO, copy an API key from
Settings -> Developer into WHOP_API_KEY, then add a webhook (Settings ->
Developer -> Webhooks) pointed at {APP_BASE_URL}/v1/billing/whop/webhook,
subscribed to membership.activated and membership.deactivated, and copy
its signing secret into WHOP_WEBHOOK_SECRET.
"""

import base64
import hashlib
import hmac
import json
import time

import httpx

from app.config import get_settings

_PLAN_TO_WHOP_ID = {
    "starter": lambda s: s.whop_plan_starter,
    "pro": lambda s: s.whop_plan_pro,
}

# A webhook older than this is either badly delayed or a replay -- the
# Standard Webhooks spec Whop implements recommends rejecting it either way
# rather than trusting an arbitrarily old signed payload.
_WEBHOOK_TOLERANCE_SECONDS = 300


class BillingNotConfiguredError(Exception):
    """Mirrors stripe_client.py's own -- see its docstring for why this is
    raised instead of letting a bare httpx/KeyError blow up: an unhandled
    exception here would surface to the browser as an opaque blocked
    network error (Starlette's default 500 response skips CORSMiddleware),
    not a message the "Upgrade" button could show anyone."""


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.whop_api_key:
        raise BillingNotConfiguredError("Billing isn't configured on this server yet (no Whop API key).")
    return {"Authorization": f"Bearer {settings.whop_api_key}"}


def whop_plan_id_for(plan: str) -> str:
    settings = get_settings()
    getter = _PLAN_TO_WHOP_ID.get(plan)
    if not getter:
        raise ValueError(f"No Whop plan configured for plan '{plan}'")
    plan_id = getter(settings)
    if not plan_id:
        raise BillingNotConfiguredError(f"No Whop plan id is configured for the '{plan}' plan yet.")
    return plan_id


def plan_for_whop_plan_id(plan_id: str) -> str | None:
    settings = get_settings()
    mapping = {settings.whop_plan_starter: "starter", settings.whop_plan_pro: "pro"}
    return mapping.get(plan_id)


def create_checkout_session(workspace_id: str, plan: str, customer_email: str) -> str:
    """Creates a one-off checkout configuration referencing one of the two
    plans created in the Whop dashboard, carrying workspace_id/plan as
    metadata -- Whop copies a checkout configuration's metadata onto the
    payment and membership it produces, which is how the webhook below
    maps a completed payment back to a workspace (there's no equivalent of
    Stripe's client_reference_id here, metadata is the only pass-through)."""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.whop_api_base_url}/checkout-configurations",
        headers=_headers(),
        json={
            "plan": {"id": whop_plan_id_for(plan)},
            "metadata": {"workspace_id": workspace_id, "plan": plan},
            "redirect_url": f"{settings.dashboard_base_url}/settings?billing=success",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["purchase_url"]


def get_membership(membership_id: str) -> dict:
    """Webhook payloads only carry `data.id` (confirmed against Whop's own
    payment.succeeded example -- no embedded object), so every event
    handler needs this follow-up call to actually see metadata/plan/status."""
    settings = get_settings()
    resp = httpx.get(f"{settings.whop_api_base_url}/memberships/{membership_id}", headers=_headers(), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def verify_webhook(payload: bytes, webhook_id: str, webhook_timestamp: str, webhook_signature: str) -> dict:
    """Whop signs webhooks per the Standard Webhooks specification (the
    same open scheme Svix popularized -- see
    https://github.com/standard-webhooks/standard-webhooks), not a
    Whop-specific format: HMAC-SHA256 over "{id}.{timestamp}.{raw body}"
    using the base64 portion of the "whsec_..." secret as the key, base64
    the result, and match it against one of the (possibly several,
    space-separated) "v1,<sig>" entries in the webhook-signature header.
    Raises ValueError on any failure -- caller turns that into a 400."""
    settings = get_settings()
    if not settings.whop_webhook_secret:
        raise BillingNotConfiguredError("Whop billing isn't configured on this server yet (no webhook secret).")
    if not (webhook_id and webhook_timestamp and webhook_signature):
        raise ValueError("Missing webhook-id/webhook-timestamp/webhook-signature header")

    try:
        age = abs(time.time() - int(webhook_timestamp))
    except ValueError as exc:
        raise ValueError("Invalid webhook-timestamp header") from exc
    if age > _WEBHOOK_TOLERANCE_SECONDS:
        raise ValueError("Webhook timestamp outside the tolerance window")

    secret = settings.whop_webhook_secret
    secret_bytes = base64.b64decode(secret[len("whsec_") :] if secret.startswith("whsec_") else secret)
    signed_content = f"{webhook_id}.{webhook_timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(secret_bytes, signed_content, hashlib.sha256).digest()).decode()

    candidates = [part.split(",", 1)[1] for part in webhook_signature.split() if part.startswith("v1,") and "," in part]
    if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
        raise ValueError("Webhook signature mismatch")

    return json.loads(payload)
