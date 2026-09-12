import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.data.soc2_controls import SOC2_CONTROLS, Soc2Control
from app.security import CurrentUser, require_workspace_member

router = APIRouter(prefix="/v1", tags=["soc2"])


@router.get("/soc2/controls", response_model=list[Soc2Control])
async def get_soc2_controls() -> list[Soc2Control]:
    """Public-ish static data (still requires login, no workspace scoping needed
    since it's the same 15 controls for everyone) backing F7's mapping page."""
    return SOC2_CONTROLS


@router.get("/workspaces/{workspace_id}/soc2/export.csv")
async def export_soc2_csv(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Control ID", "Title", "Description", "Evidence Type", "Evidence Note"])
    for c in SOC2_CONTROLS:
        writer.writerow([c.control_id, c.title, c.description, c.evidence_type, c.evidence_note])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=auditagent-soc2-mapping.csv"},
    )
