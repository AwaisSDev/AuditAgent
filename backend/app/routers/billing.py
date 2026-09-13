import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, run_db
from app.models.schemas import CheckoutSessionIn, CheckoutSessionOut
from app.security import CurrentUser, require_workspace_member
import stripe as stripe_sdk

from app.services.stripe_client import BillingNotConfiguredError, construct_webhook_event, create_checkout_session, plan_for_price_id

router = APIRouter(prefix="/v1", tags=["billing"])


@router.post("/workspaces/{workspace_id}/billing/checkout", response_model=CheckoutSessionOut)
async def create_checkout(
    workspace_id: str, body: CheckoutSessionIn, user: CurrentUser = Depends(require_workspace_member)
) -> CheckoutSessionOut:
    if not user.email:
        raise HTTPException(status_code=400, detail="Account has no email on file")
    try:
        # stripe-python is a synchronous client under the hood.
        url = await asyncio.to_thread(create_checkout_session, workspace_id, body.plan, user.email)
    except BillingNotConfiguredError as exc:
        # Without this, an unhandled exception here produces a 500 that
        # Starlette sends without CORS headers, which the browser blocks
        # outright — the "Upgrade" button would silently do nothing with no
        # error ever reaching the user. See BillingNotConfiguredError's docstring.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except stripe_sdk.error.StripeError as exc:
        raise HTTPException(status_code=502, detail=f"Stripe rejected the request: {exc.user_message or str(exc)}") from exc
    return CheckoutSessionOut(checkout_url=url)


@router.post("/billing/webhook")
async def stripe_webhook(request: Request) -> dict:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = construct_webhook_event(payload, sig_header)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}") from exc

    db = get_db()
    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        workspace_id = obj["metadata"]["workspace_id"]
        plan = obj["metadata"]["plan"]
        await _upsert_subscription(
            db,
            workspace_id=workspace_id,
            stripe_customer_id=obj["customer"],
            stripe_subscription_id=obj["subscription"],
            plan=plan,
            status="active",
        )

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        workspace_id = obj.get("metadata", {}).get("workspace_id")
        if workspace_id:
            price_id = obj["items"]["data"][0]["price"]["id"] if obj.get("items", {}).get("data") else None
            plan = plan_for_price_id(price_id) if price_id else None
            status = "active" if event["type"] == "customer.subscription.updated" and obj["status"] == "active" else "canceled"
            await _upsert_subscription(
                db,
                workspace_id=workspace_id,
                stripe_customer_id=obj["customer"],
                stripe_subscription_id=obj["id"],
                plan=plan if event["type"] != "customer.subscription.deleted" else "free",
                status=status,
            )

    return {"received": True}


async def _upsert_subscription(db, workspace_id: str, stripe_customer_id: str, stripe_subscription_id: str, plan: str | None, status: str) -> None:
    payload = {
        "workspace_id": workspace_id,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if plan:
        payload["plan"] = plan
    await run_db(lambda: db.table("subscriptions").upsert(payload, on_conflict="workspace_id").execute())
    if plan:
        await run_db(lambda: db.table("workspaces").update({"plan": plan}).eq("id", workspace_id).execute())
