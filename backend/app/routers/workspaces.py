import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_db, run_db
from app.models.schemas import WorkspaceCreateIn, WorkspaceOut
from app.security import CurrentUser, get_current_user, require_workspace_member
from app.services.policy_engine import DEFAULT_POLICY_YAML

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "workspace"
    return base


@router.get("", response_model=list[WorkspaceOut])
async def list_my_workspaces(user: CurrentUser = Depends(get_current_user)) -> list[WorkspaceOut]:
    db = get_db()
    memberships = (
        await run_db(lambda: db.table("workspace_members").select("workspace_id").eq("user_id", user.id).execute())
    ).data
    ids = [m["workspace_id"] for m in memberships]
    if not ids:
        return []
    return (await run_db(lambda: db.table("workspaces").select("*").in_("id", ids).execute())).data


@router.post("", response_model=WorkspaceOut, status_code=201)
async def create_workspace(body: WorkspaceCreateIn, user: CurrentUser = Depends(get_current_user)) -> WorkspaceOut:
    """Creates a workspace + owner membership + a default policy in one shot.
    Goes through the backend (rather than the dashboard writing to Supabase
    directly) so these three inserts stay atomic under the service-role key."""
    db = get_db()
    slug = _slugify(body.name)
    suffix = 0
    while (await run_db(lambda: db.table("workspaces").select("id").eq("slug", slug).execute())).data:
        suffix += 1
        slug = f"{_slugify(body.name)}-{suffix}"

    ws = (
        await run_db(lambda: db.table("workspaces").insert({"name": body.name, "slug": slug, "owner_id": user.id}).execute())
    ).data[0]
    await run_db(
        lambda: db.table("workspace_members").insert({"workspace_id": ws["id"], "user_id": user.id, "role": "owner"}).execute()
    )
    await run_db(lambda: db.table("policies").insert({"workspace_id": ws["id"], "rules_yaml": DEFAULT_POLICY_YAML}).execute())
    return ws


class WorkspaceSettingsIn(BaseModel):
    slack_channel_id: str | None = None
    notify_email: str | None = None


@router.get("/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> WorkspaceOut:
    db = get_db()
    res = await run_db(lambda: db.table("workspaces").select("*").eq("id", workspace_id).single().execute())
    if not res.data:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return res.data


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
async def update_workspace_settings(
    workspace_id: str, body: WorkspaceSettingsIn, user: CurrentUser = Depends(require_workspace_member)
) -> WorkspaceOut:
    db = get_db()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await run_db(lambda: db.table("workspaces").update(updates).eq("id", workspace_id).execute())
    return updated.data[0]
