import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.data.soc2_controls import SOC2_CONTROLS, Soc2Control, Soc2ControlOut
from app.db import get_db
from app.security import CurrentUser, get_current_user, require_workspace_member
from app.services.soc2_evidence import compute_live_evidence

router = APIRouter(prefix="/v1", tags=["soc2"])


@router.get("/soc2/controls", response_model=list[Soc2Control])
async def get_soc2_controls(user: CurrentUser = Depends(get_current_user)) -> list[Soc2Control]:
    """Static data, kept for any caller that isn't asking about one specific
    workspace. The dashboard's SOC2 page uses the workspace-scoped endpoint
    below instead."""
    return SOC2_CONTROLS


@router.get("/workspaces/{workspace_id}/soc2/controls", response_model=list[Soc2ControlOut])
async def get_workspace_soc2_controls(
    workspace_id: str, user: CurrentUser = Depends(require_workspace_member)
) -> list[Soc2ControlOut]:
    db = get_db()
    live = await compute_live_evidence(db, workspace_id)
    return [
        Soc2ControlOut(**c.model_dump(), live_evidence=live.get(c.control_id, c.evidence_note)) for c in SOC2_CONTROLS
    ]


@router.get("/workspaces/{workspace_id}/soc2/export.csv")
async def export_soc2_csv(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> StreamingResponse:
    db = get_db()
    live = await compute_live_evidence(db, workspace_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Control ID", "Title", "Description", "Evidence Type", "Evidence (this workspace)"])
    for c in SOC2_CONTROLS:
        writer.writerow([c.control_id, c.title, c.description, c.evidence_type, live.get(c.control_id, c.evidence_note)])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=tracyn-soc2-mapping.csv"},
    )
