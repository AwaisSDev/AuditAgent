from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db, run_db
from app.models.schemas import AgentIn, AgentOut, ApiKeyCreateIn, ApiKeyCreateOut, ApiKeyOut
from app.security import CurrentUser, generate_api_key, require_workspace_member
from app.services.plan_limits import agent_limit

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["agents"])


@router.get("/agents", response_model=list[AgentOut])
async def list_agents(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> list[AgentOut]:
    db = get_db()
    return (
        await run_db(lambda: db.table("agents").select("*").eq("workspace_id", workspace_id).order("created_at").execute())
    ).data


@router.post("/agents", response_model=AgentOut, status_code=201)
async def create_agent(
    workspace_id: str, body: AgentIn, user: CurrentUser = Depends(require_workspace_member)
) -> AgentOut:
    db = get_db()
    plan_limit = await _agent_limit_for_plan(db, workspace_id)
    count = (
        await run_db(lambda: db.table("agents").select("id", count="exact").eq("workspace_id", workspace_id).execute())
    ).count or 0
    if plan_limit is not None and count >= plan_limit:
        raise HTTPException(status_code=402, detail=f"Plan limit reached ({plan_limit} agents). Upgrade to add more.")
    created = await run_db(
        lambda: db.table("agents")
        .insert({"workspace_id": workspace_id, "name": body.name, "description": body.description, "created_by": user.id})
        .execute()
    )
    return created.data[0]


async def _agent_limit_for_plan(db, workspace_id: str) -> int | None:
    ws = (await run_db(lambda: db.table("workspaces").select("plan").eq("id", workspace_id).single().execute())).data
    return agent_limit(ws["plan"])


# --- API keys -----------------------------------------------------------

@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> list[ApiKeyOut]:
    db = get_db()
    return (
        await run_db(
            lambda: db.table("api_keys")
            .select("id, name, key_prefix, created_at, last_used_at, revoked_at")
            .eq("workspace_id", workspace_id)
            .order("created_at")
            .execute()
        )
    ).data


@router.post("/api-keys", response_model=ApiKeyCreateOut, status_code=201)
async def create_api_key(
    workspace_id: str, body: ApiKeyCreateIn, user: CurrentUser = Depends(require_workspace_member)
) -> ApiKeyCreateOut:
    full_key, prefix, key_hash = generate_api_key()
    db = get_db()
    created = await run_db(
        lambda: db.table("api_keys")
        .insert({"workspace_id": workspace_id, "name": body.name, "key_prefix": prefix, "key_hash": key_hash, "created_by": user.id})
        .execute()
    )
    row = created.data[0]
    return ApiKeyCreateOut(id=row["id"], name=row["name"], key_prefix=prefix, full_key=full_key)


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(workspace_id: str, key_id: str, user: CurrentUser = Depends(require_workspace_member)) -> None:
    db = get_db()
    from datetime import datetime, timezone

    await run_db(
        lambda: db.table("api_keys")
        .update({"revoked_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", key_id)
        .eq("workspace_id", workspace_id)
        .execute()
    )
