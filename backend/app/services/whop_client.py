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


def _checkout_origin(settings) -> str:
    # purchase_url comes back as a path relative to whop.com/sandbox.whop.com
    # (confirmed live: "/checkout/ch_xxx/"), not the api./sandbox-api. host
    # requests are actually made against -- so it has to be derived
    # separately rather than assumed to already be absolute.
    return "https://sandbox.whop.com" if "sandbox" in settings.whop_api_base_url else "https://whop.com"


def create_checkout_session(workspace_id: str, plan: str, customer_email: str) -> str:
    """Creates a one-off checkout configuration referencing one of the two
    plans created in the Whop dashboard, carrying workspace_id/plan as
    metadata -- Whop copies a checkout configuration's metadata onto the
    payment and membership it produces, which is how the webhook below
    maps a completed payment back to a workspace (there's no equivalent of
    Stripe's client_reference_id here, metadata is the only pass-through).

    Uses the "existing plan_id" variant of this endpoint's request schema
    (it's a oneOf: inline plan details, an existing plan_id, or "setup"
    mode) -- plan_id and mode are both required for that variant;
    account_id is only required for the unrelated "setup" mode."""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.whop_api_base_url}/checkout_configurations",
        headers=_headers(),
        json={
            "plan_id": whop_plan_id_for(plan),
            "mode": "payment",
            "metadata": {"workspace_id": workspace_id, "plan": plan},
            # `plan` here is ours, not Whop's -- lets the success page show
            # the right plan name immediately instead of waiting on the
            # webhook (which can lag the redirect by a few seconds) just to
            # know what was purchased. Whop appends its own params
            # (payment_id, receipt_id, ...) on top of this, doesn't replace it.
            "redirect_url": f"{settings.dashboard_base_url}/settings?billing=success&plan={plan}",
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    purchase_url = resp.json()["purchase_url"]
    return purchase_url if purchase_url.startswith("http") else f"{_checkout_origin(settings)}{purchase_url}"


def get_membership(membership_id: str) -> dict:
    """Webhook payloads only carry `data.id` (confirmed against Whop's own
    payment.succeeded example -- no embedded object), so every event
    handler needs this follow-up call to actually see metadata/plan/status."""
    settings = get_settings()
    resp = httpx.get(f"{settings.whop_api_base_url}/memberships/{membership_id}", headers=_headers(), timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def get_checkout_configuration(checkout_configuration_id: str) -> dict:
    """Fallback source of truth for metadata (see billing.py's webhook
    handler): docs claim a checkout configuration's metadata is copied onto
    the membership/payment it produces, but that's exactly the kind of
    claim this integration has already gotten burned trusting without
    confirmation once -- the configuration itself definitely has it,
    since create_checkout_session is what set it."""
    settings = get_settings()
    resp = httpx.get(
        f"{settings.whop_api_base_url}/checkout_configurations/{checkout_configuration_id}", headers=_headers(), timeout=15.0
    )
    resp.raise_for_status()
    return resp.json()


def _candidate_secret_keys(secret: str) -> list[bytes]:
    """What HMAC key Whop actually means by "the secret" turned out not to
    match this integration's first two guesses (see verify_webhook's
    docstring history) -- confirmed live, the dashboard shows a "ws_"
    prefix, not the "whsec_" the Standard Webhooks spec's own examples use,
    and base64-decoding the whole "ws_..." string (prefix included) fails
    with "Incorrect padding" on every delivery, which was exactly the 400
    every attempt got. Rather than lock in a third specific guess, generate
    every plausible key derivation -- verify_webhook tries each one and
    accepts the first that produces a matching signature. This doesn't
    weaken anything: an attacker without the real secret still can't
    produce a signature that matches under any candidate."""
    stripped = secret
    for prefix in ("whsec_", "ws_"):
        if secret.startswith(prefix):
            stripped = secret[len(prefix) :]
            break

    candidates = [secret.encode(), stripped.encode()]
    for value in (secret, stripped):
        padded = value + "=" * (-len(value) % 4)
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                candidates.append(decoder(padded, validate=True) if decoder is base64.b64decode else decoder(padded))
            except ValueError:
                pass
    return candidates


def verify_webhook(payload: bytes, webhook_id: str, webhook_timestamp: str, webhook_signature: str) -> dict:
    """Whop signs webhooks per the Standard Webhooks specification (the
    same open scheme Svix popularized -- see
    https://github.com/standard-webhooks/standard-webhooks): HMAC-SHA256
    over "{id}.{timestamp}.{raw body}", base64 the result, match it against
    one of the (possibly several, space-separated) "v1,<sig>" entries in
    the webhook-signature header. See _candidate_secret_keys for why the
    HMAC key itself is tried multiple ways rather than one fixed encoding.
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

    signed_content = f"{webhook_id}.{webhook_timestamp}.".encode() + payload
    sig_candidates = [part.split(",", 1)[1] for part in webhook_signature.split() if part.startswith("v1,") and "," in part]

    matched = any(
        hmac.compare_digest(base64.b64encode(hmac.new(key, signed_content, hashlib.sha256).digest()).decode(), sig)
        for key in _candidate_secret_keys(settings.whop_webhook_secret)
        for sig in sig_candidates
    )
    if not matched:
        raise ValueError("Webhook signature mismatch")

    return json.loads(payload)
