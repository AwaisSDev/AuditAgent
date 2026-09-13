"""F9 — Stripe billing. Manual setup required — see docs/MANUAL_SETUP.md:

  1. Create a Stripe account, switch to test mode for development.
  2. Create 3 recurring Products/Prices (Starter $49/mo, Growth $199/mo,
     Enterprise $999/mo) in the Stripe Dashboard -> Product catalog.
     (Free has no Stripe price — it's just the default `plan` value.)
  3. Copy each Price id into STRIPE_PRICE_STARTER / _GROWTH / _ENTERPRISE.
  4. Copy the Secret key into STRIPE_SECRET_KEY.
  5. Add a webhook endpoint at {APP_BASE_URL}/v1/billing/webhook listening
     for: checkout.session.completed, customer.subscription.updated,
     customer.subscription.deleted. Copy its signing secret into
     STRIPE_WEBHOOK_SECRET.
"""

import stripe

from app.config import get_settings

_PLAN_TO_PRICE_ENV = {
    "starter": lambda s: s.stripe_price_starter,
    "growth": lambda s: s.stripe_price_growth,
    "enterprise": lambda s: s.stripe_price_enterprise,
}

_PRICE_TO_PLAN_CACHE: dict[str, str] | None = None


class BillingNotConfiguredError(Exception):
    """Raised instead of letting a bare Stripe SDK call blow up with an
    unhelpful "you did not provide an API key" error. An unhandled exception
    here previously surfaced to the browser as a silent failure — Starlette's
    default 500 response for an unhandled exception isn't passed back through
    CORSMiddleware, so the browser's fetch just sees a blocked, unreadable
    network error with no message at all (see routers/billing.py)."""


def _configure() -> None:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingNotConfiguredError("Billing isn't configured on this server yet (no Stripe secret key).")
    stripe.api_key = settings.stripe_secret_key


def price_id_for_plan(plan: str) -> str:
    settings = get_settings()
    getter = _PLAN_TO_PRICE_ENV.get(plan)
    if not getter:
        raise ValueError(f"No Stripe price configured for plan '{plan}'")
    price_id = getter(settings)
    if not price_id:
        raise BillingNotConfiguredError(f"No Stripe price is configured for the '{plan}' plan yet.")
    return price_id


def plan_for_price_id(price_id: str) -> str | None:
    settings = get_settings()
    mapping = {
        settings.stripe_price_starter: "starter",
        settings.stripe_price_growth: "growth",
        settings.stripe_price_enterprise: "enterprise",
    }
    return mapping.get(price_id)


def create_checkout_session(workspace_id: str, plan: str, customer_email: str) -> str:
    _configure()
    settings = get_settings()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=customer_email,
        line_items=[{"price": price_id_for_plan(plan), "quantity": 1}],
        success_url=f"{settings.dashboard_base_url}/billing?success=1",
        cancel_url=f"{settings.dashboard_base_url}/billing?canceled=1",
        client_reference_id=workspace_id,
        metadata={"workspace_id": workspace_id, "plan": plan},
        subscription_data={"metadata": {"workspace_id": workspace_id, "plan": plan}},
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    _configure()
    settings = get_settings()
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
