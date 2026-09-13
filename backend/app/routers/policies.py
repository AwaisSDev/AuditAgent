from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db, run_db
from app.models.schemas import PolicyIn, PolicyOut
from app.security import CurrentUser, WorkspaceKeyAuth, get_api_key_auth, require_workspace_member
from app.services.policy_engine import DEFAULT_POLICY_YAML, PolicyParseError, parse_policy

router = APIRouter(prefix="/v1", tags=["policies"])


# SDK-facing: fetched once at SDK init ("F2: SDK reads policy on init").
@router.get("/sdk/policy")
async def get_policy_for_sdk(auth: WorkspaceKeyAuth = Depends(get_api_key_auth)) -> dict:
    db = get_db()
    res = await run_db(
        lambda: db.table("policies")
        .select("rules_yaml")
        .eq("workspace_id", auth.workspace_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    rules_yaml = res.data[0]["rules_yaml"] if res.data else DEFAULT_POLICY_YAML
    return {"rules_yaml": rules_yaml}


# Dashboard-facing: view/edit the active policy.
@router.get("/workspaces/{workspace_id}/policy", response_model=PolicyOut)
async def get_policy(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> PolicyOut:
    db = get_db()
    res = await run_db(
        lambda: db.table("policies")
        .select("*")
        .eq("workspace_id", workspace_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    created = await run_db(
        lambda: db.table("policies").insert({"workspace_id": workspace_id, "rules_yaml": DEFAULT_POLICY_YAML}).execute()
    )
    return created.data[0]


@router.put("/workspaces/{workspace_id}/policy", response_model=PolicyOut)
async def update_policy(
    workspace_id: str, body: PolicyIn, user: CurrentUser = Depends(require_workspace_member)
) -> PolicyOut:
    try:
        parse_policy(body.rules_yaml)
    except PolicyParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db = get_db()
    existing = await run_db(
        lambda: db.table("policies").select("id").eq("workspace_id", workspace_id).eq("is_active", True).limit(1).execute()
    )
    if existing.data:
        updated = await run_db(
            lambda: db.table("policies")
            .update({"rules_yaml": body.rules_yaml, "name": body.name, "updated_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", existing.data[0]["id"])
            .execute()
        )
        return updated.data[0]
    created = await run_db(
        lambda: db.table("policies").insert({"workspace_id": workspace_id, "name": body.name, "rules_yaml": body.rules_yaml}).execute()
    )
    return created.data[0]
