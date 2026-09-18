import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_db, run_db
from app.models.schemas import CheckoutSessionIn, CheckoutSessionOut
from app.security import CurrentUser, require_workspace_member
from app.services.whop_client import (
    BillingNotConfiguredError,
    cancel_membership,
    create_checkout_session,
    get_checkout_configuration,
    get_membership,
    plan_for_whop_plan_id,
    verify_webhook,
)

router = APIRouter(prefix="/v1", tags=["billing"])


@router.post("/workspaces/{workspace_id}/billing/checkout", response_model=CheckoutSessionOut)
async def create_checkout(
    workspace_id: str, body: CheckoutSessionIn, user: CurrentUser = Depends(require_workspace_member)
) -> CheckoutSessionOut:
    if not user.email:
        raise HTTPException(status_code=400, detail="Account has no email on file")
    try:
        # httpx's sync Client is used here (see whop_client.py) -- off the
        # event loop the same way stripe-python's own sync client was.
        url = await asyncio.to_thread(create_checkout_session, workspace_id, body.plan, user.email)
    except BillingNotConfiguredError as exc:
        # Without this, an unhandled exception here produces a 500 that
        # Starlette sends without CORS headers, which the browser blocks
        # outright — the "Upgrade" button would silently do nothing with no
        # error ever reaching the user. See BillingNotConfiguredError's docstring.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Whop rejected the request: {exc.response.text}") from exc
    return CheckoutSessionOut(checkout_url=url)


@router.post("/billing/whop/webhook")
async def whop_webhook(request: Request) -> dict:
    payload = await request.body()
    try:
        event = verify_webhook(
            payload,
            webhook_id=request.headers.get("webhook-id", ""),
            webhook_timestamp=request.headers.get("webhook-timestamp", ""),
            webhook_signature=request.headers.get("webhook-signature", ""),
        )
    except BillingNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid webhook: {exc}") from exc

    event_type = event.get("type", "")
    membership_id = event.get("data", {}).get("id")
    if not membership_id or event_type not in ("membership.activated", "membership.deactivated"):
        # Every other subscribed-or-not event is a no-op here on purpose --
        # ack it anyway so Whop doesn't retry-storm an endpoint that was
        # never going to handle it.
        return {"received": True}

    # The webhook payload only ever carries an id (confirmed against Whop's
    # own payment.succeeded example) -- metadata/plan/status live on the
    # full object, not the event envelope, so this fetch isn't optional.
    membership = await asyncio.to_thread(get_membership, membership_id)
    metadata = membership.get("metadata") or {}
    if not metadata.get("workspace_id") and membership.get("checkout_configuration_id"):
        # Docs claim a checkout configuration's metadata is copied onto the
        # membership it produces -- unconfirmed, and this integration has
        # already hit two other doc claims that didn't match the real API,
        # so don't just trust an empty membership.metadata as "no workspace
        # to update": go straight to the one place the metadata is
        # definitely correct, since create_checkout_session is what set it.
        checkout_config = await asyncio.to_thread(get_checkout_configuration, membership["checkout_configuration_id"])
        metadata = checkout_config.get("metadata") or {}

    workspace_id = metadata.get("workspace_id")
    if not workspace_id:
        return {"received": True}

    db = get_db()
    existing = await run_db(
        lambda: db.table("subscriptions").select("whop_membership_id").eq("workspace_id", workspace_id).execute()
    )
    on_file_membership_id = existing.data[0]["whop_membership_id"] if existing.data else None

    if event_type == "membership.activated":
        plan = metadata.get("plan") or plan_for_whop_plan_id(membership.get("plan", {}).get("id", ""))

        # A workspace buying a new plan while a *different* membership is
        # still on file means an upgrade/downgrade, not a first purchase --
        # without canceling the old one, both stay active and billing in
        # parallel (confirmed live: the same account ended up with a
        # Starter and a Pro payment both succeeded back to back).
        if on_file_membership_id and on_file_membership_id != membership_id:
            try:
                await asyncio.to_thread(cancel_membership, on_file_membership_id)
            except httpx.HTTPStatusError:
                # Already canceled/expired on Whop's side, or some other
                # non-fatal rejection -- don't let cleanup of the OLD
                # membership block activating the NEW one, which is what
                # actually matters to the workspace right now.
                pass

        await _upsert_whop_subscription(db, workspace_id=workspace_id, whop_membership_id=membership_id, plan=plan, status="active")
    else:
        # That cancel call above makes Whop deliver a deactivated event for
        # the OLD membership -- confirmed live, it can arrive *after* the
        # NEW membership's activated event already set the correct plan,
        # and this branch would otherwise downgrade to free unconditionally,
        # stomping the just-applied upgrade back to free. Only act on a
        # deactivation if it's for whichever membership is actually on file
        # right now -- a deactivation for a membership that's already been
        # superseded by a newer one is stale and must be a no-op.
        if on_file_membership_id and on_file_membership_id != membership_id:
            return {"received": True}
        await _upsert_whop_subscription(db, workspace_id=workspace_id, whop_membership_id=membership_id, plan="free", status="canceled")

    return {"received": True}


async def _upsert_whop_subscription(db, workspace_id: str, whop_membership_id: str, plan: str | None, status: str) -> None:
    payload = {
        "workspace_id": workspace_id,
        "whop_membership_id": whop_membership_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if plan:
        payload["plan"] = plan
    await run_db(lambda: db.table("subscriptions").upsert(payload, on_conflict="workspace_id").execute())
    if plan:
        await run_db(lambda: db.table("workspaces").update({"plan": plan}).eq("id", workspace_id).execute())
