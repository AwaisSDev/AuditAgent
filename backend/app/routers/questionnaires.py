import uuid
from datetime import datetime, timezone

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.db import get_db
from app.models.schemas import AnswerOut, AnswerUpdateIn, QuestionnaireOut
from app.security import CurrentUser, require_workspace_member
from app.services.evidence_export import build_csv, build_docx
from app.services.plan_limits import questionnaire_limit

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["questionnaires"])

_EXT_TO_TYPE = {"pdf": "pdf", "csv": "csv", "xlsx": "xlsx", "xls": "xlsx"}


@router.get("/questionnaires", response_model=list[QuestionnaireOut])
async def list_questionnaires(workspace_id: str, user: CurrentUser = Depends(require_workspace_member)) -> list[QuestionnaireOut]:
    db = get_db()
    return db.table("questionnaires").select("*").eq("workspace_id", workspace_id).order("created_at", desc=True).execute().data


@router.post("/questionnaires", response_model=QuestionnaireOut, status_code=201)
async def upload_questionnaire(
    workspace_id: str,
    request: Request,
    file: UploadFile,
    user: CurrentUser = Depends(require_workspace_member),
) -> QuestionnaireOut:
    db = get_db()

    ws = db.table("workspaces").select("plan").eq("id", workspace_id).single().execute().data
    limit = questionnaire_limit(ws["plan"])
    if limit is not None:
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        used = (
            db.table("questionnaires")
            .select("id", count="exact")
            .eq("workspace_id", workspace_id)
            .gte("created_at", month_start)
            .execute()
            .count
            or 0
        )
        if used >= limit:
            raise HTTPException(status_code=402, detail=f"Monthly questionnaire limit reached ({limit}). Upgrade to process more.")

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    file_type = _EXT_TO_TYPE.get(ext)
    if not file_type:
        raise HTTPException(status_code=400, detail="Supported file types: PDF, CSV, XLSX")

    content = await file.read()
    storage_path = f"{workspace_id}/{uuid.uuid4()}.{ext}"
    db.storage.from_("questionnaires").upload(storage_path, content, {"content-type": file.content_type or "application/octet-stream"})

    created = (
        db.table("questionnaires")
        .insert(
            {
                "workspace_id": workspace_id,
                "filename": file.filename,
                "file_type": file_type,
                "storage_path": storage_path,
                "uploaded_by": user.id,
            }
        )
        .execute()
    ).data[0]

    arq_pool: ArqRedis | None = request.app.state.arq_pool
    if arq_pool is None:
        raise HTTPException(status_code=503, detail="Background processing (Redis) is not configured on this server yet.")
    await arq_pool.enqueue_job("process_questionnaire", created["id"])

    return created


@router.get("/questionnaires/{questionnaire_id}/answers", response_model=list[AnswerOut])
async def list_answers(
    workspace_id: str, questionnaire_id: str, user: CurrentUser = Depends(require_workspace_member)
) -> list[AnswerOut]:
    db = get_db()
    answers = (
        db.table("answers")
        .select("*")
        .eq("questionnaire_id", questionnaire_id)
        .eq("workspace_id", workspace_id)
        .order("created_at")
        .execute()
        .data
    )
    result = []
    for a in answers:
        links = db.table("evidence_links").select("event_id").eq("answer_id", a["id"]).execute().data
        result.append({**a, "evidence_event_ids": [l["event_id"] for l in links]})
    return result


@router.patch("/answers/{answer_id}", response_model=AnswerOut)
async def update_answer(
    workspace_id: str, answer_id: str, body: AnswerUpdateIn, user: CurrentUser = Depends(require_workspace_member)
) -> AnswerOut:
    """Human review step — F4 explicitly never auto-submits; this is where a
    person edits the draft into the final wording before export."""
    db = get_db()
    updated = (
        db.table("answers")
        .update(
            {
                "final_answer": body.final_answer,
                "status": body.status,
                "reviewed_by": user.id,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("id", answer_id)
        .eq("workspace_id", workspace_id)
        .execute()
        .data[0]
    )
    links = db.table("evidence_links").select("event_id").eq("answer_id", answer_id).execute().data
    return {**updated, "evidence_event_ids": [l["event_id"] for l in links]}


async def _export_rows(db, workspace_id: str, questionnaire_id: str) -> list[dict]:
    answers = db.table("answers").select("*").eq("questionnaire_id", questionnaire_id).eq("workspace_id", workspace_id).order("created_at").execute().data
    rows = []
    for a in answers:
        links = db.table("evidence_links").select("event_id").eq("answer_id", a["id"]).execute().data
        rows.append({**a, "evidence_event_ids": [l["event_id"] for l in links]})
    return rows


@router.get("/questionnaires/{questionnaire_id}/export.docx")
async def export_docx(workspace_id: str, questionnaire_id: str, user: CurrentUser = Depends(require_workspace_member)) -> StreamingResponse:
    db = get_db()
    ws = db.table("workspaces").select("name, plan").eq("id", workspace_id).single().execute().data
    q = db.table("questionnaires").select("filename").eq("id", questionnaire_id).single().execute().data
    rows = await _export_rows(db, workspace_id, questionnaire_id)
    content = build_docx(ws["name"], q["filename"], rows, watermark=(ws["plan"] == "free"))
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=evidence-pack-{questionnaire_id}.docx"},
    )


@router.get("/questionnaires/{questionnaire_id}/export.csv")
async def export_csv(workspace_id: str, questionnaire_id: str, user: CurrentUser = Depends(require_workspace_member)) -> StreamingResponse:
    db = get_db()
    rows = await _export_rows(db, workspace_id, questionnaire_id)
    content = build_csv(rows)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=evidence-pack-{questionnaire_id}.csv"},
    )
