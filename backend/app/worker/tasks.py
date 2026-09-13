import hashlib
import re
from datetime import datetime, timezone

from app.db import get_db, run_db as _db
from app.services.claude_client import draft_answer
from app.services.classification import redact_with_llm
from app.services.email_client import send_timeout_notice
from app.services.questionnaire_parser import parse_questionnaire
from app.services.redaction import redact_pii
from app.services.slack_client import update_message_with_decision

GENESIS_HASH = "0" * 64


def _get_or_create_agent(db, workspace_id: str, name: str) -> str:
    existing = db.table("agents").select("id").eq("workspace_id", workspace_id).eq("name", name).limit(1).execute()
    if existing.data:
        return existing.data[0]["id"]
    created = db.table("agents").insert({"workspace_id": workspace_id, "name": name}).execute()
    return created.data[0]["id"]


async def process_event_intake(ctx, intake_id: str) -> None:
    """The core F3 pipeline: redact -> classify -> insert immutable event.

    Runs once per ingested event. See app/routers/ingest.py for why this is
    async instead of happening inline in the request handler, and
    supabase/schema.sql's `event_intake` table comment for why redaction
    can't happen via a later UPDATE.
    """
    db = get_db()

    intake_res = await _db(lambda: db.table("event_intake").select("*").eq("id", intake_id).single().execute())
    intake = intake_res.data
    if not intake or intake["status"] != "queued":
        return

    await _db(lambda: db.table("event_intake").update({"status": "processing"}).eq("id", intake_id).execute())

    try:
        payload = intake["payload"]
        workspace_id = intake["workspace_id"]

        redacted_inputs = redact_pii(payload.get("inputs") or {})
        redacted_inputs = await redact_with_llm(redacted_inputs)

        redacted_output = redact_pii(payload.get("output"))
        if isinstance(redacted_output, dict):
            redacted_output = await redact_with_llm(redacted_output)

        agent_id = await _db(_get_or_create_agent, db, workspace_id, payload["agent_name"])

        event_row = await _db(
            lambda: db.table("events")
            .insert(
                {
                    "workspace_id": workspace_id,
                    "agent_id": agent_id,
                    "action_type": payload["action_type"],
                    "action_name": payload["action_name"],
                    "inputs_redacted": redacted_inputs,
                    "output_redacted": redacted_output,
                    "model": payload.get("model"),
                    "prompt_hash": payload.get("prompt_hash"),
                    "cost_usd": payload.get("cost_usd"),
                    "latency_ms": payload.get("latency_ms"),
                    "status": payload.get("status", "completed"),
                }
            )
            .execute(),
            # Never retried: unlike the selects/updates around it, an INSERT
            # here is not safely repeatable — if "Server disconnected" fires
            # after Postgres already committed the row but before the response
            # arrived, a retry would insert a second, duplicate immutable event.
            # A single lost attempt just fails the event; that's the safe side
            # to fail on for an append-only audit log.
            attempts=1,
        )
        event_id = event_row.data[0]["id"]

        approval_id = payload.get("approval_id")
        if approval_id:
            await _db(lambda: db.table("approvals").update({"event_id": event_id}).eq("id", approval_id).execute())

        await _db(
            lambda: db.table("event_intake")
            .update({"status": "done", "processed_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", intake_id)
            .execute()
        )
    except Exception as exc:
        await _db(
            lambda: db.table("event_intake")
            .update({"status": "error", "error_message": str(exc)[:2000]})
            .eq("id", intake_id)
            .execute()
        )
        raise


async def sweep_expired_approvals(ctx) -> None:
    """Cron (every minute): auto-deny anything past its 30-minute window and
    notify. This is the belt-and-suspenders path — normally the SDK's own
    poll loop notices expiry first, but this covers the case where the SDK
    process died or was never polling (e.g. dashboard-only workspace)."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    expired = await _db(
        lambda: db.table("approvals")
        .select("id, workspace_id, slack_channel, slack_message_ts, requested_action")
        .eq("status", "pending")
        .lt("expires_at", now)
        .execute()
    )

    for row in expired.data:
        await _db(
            lambda r=row: db.table("approvals")
            .update({"status": "denied_timeout", "decided_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", r["id"])
            .execute()
        )

        if row.get("slack_channel") and row.get("slack_message_ts"):
            await update_message_with_decision(
                row["slack_channel"], row["slack_message_ts"], ":alarm_clock: *Auto-denied* — no response within 30 minutes"
            )

        ws = await _db(
            lambda r=row: db.table("workspaces").select("notify_email").eq("id", r["workspace_id"]).single().execute()
        )
        email = (ws.data or {}).get("notify_email")
        if email:
            action = row["requested_action"]
            send_timeout_notice(email, action.get("agent_name", ""), action.get("action_name", ""))


_QUESTION_STOPWORDS = {
    "what", "does", "have", "your", "company", "with", "this", "that", "from",
    "which", "would", "could", "their", "there", "about", "please", "describe",
}


def _question_keywords(question: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{5,}", question.lower())
    return [w for w in dict.fromkeys(words) if w not in _QUESTION_STOPWORDS][:5]


async def process_questionnaire(ctx, questionnaire_id: str) -> None:
    """F4 pipeline: parse the uploaded file into questions, find candidate
    evidence per question via keyword match (falling back to "most recent
    events" if nothing matches), then have Claude Sonnet draft a cited
    answer for each. Results land as `draft` answers — a human always
    reviews/edits before anything is exported (routers/questionnaires.py)."""
    db = get_db()
    q_res = await _db(lambda: db.table("questionnaires").select("*").eq("id", questionnaire_id).single().execute())
    questionnaire = q_res.data
    if not questionnaire:
        return

    try:
        file_bytes = await _db(lambda: db.storage.from_("questionnaires").download(questionnaire["storage_path"]))
        questions = parse_questionnaire(file_bytes, questionnaire["file_type"])
        workspace_id = questionnaire["workspace_id"]

        for question_text in questions:
            keywords = _question_keywords(question_text)
            candidates: list[dict] = []

            if keywords:
                or_filter = ",".join(f"action_name.ilike.%{kw}%,action_type.ilike.%{kw}%" for kw in keywords)
                res = await _db(
                    lambda f=or_filter: db.table("events")
                    .select("id, action_type, action_name, status, created_at")
                    .eq("workspace_id", workspace_id)
                    .or_(f)
                    .order("created_at", desc=True)
                    .limit(15)
                    .execute()
                )
                candidates = res.data

            if not candidates:
                res = await _db(
                    lambda: db.table("events")
                    .select("id, action_type, action_name, status, created_at")
                    .eq("workspace_id", workspace_id)
                    .order("created_at", desc=True)
                    .limit(15)
                    .execute()
                )
                candidates = res.data

            drafted = await draft_answer(question_text, candidates)

            answer_row = await _db(
                lambda qt=question_text, ans=drafted.answer: db.table("answers")
                .insert({"questionnaire_id": questionnaire_id, "workspace_id": workspace_id, "question_text": qt, "draft_answer": ans})
                .execute()
            )
            answer_id = answer_row.data[0]["id"]

            for event_id in drafted.cited_event_ids:
                await _db(
                    lambda aid=answer_id, eid=event_id: db.table("evidence_links")
                    .insert({"answer_id": aid, "event_id": eid})
                    .execute()
                )

        await _db(lambda: db.table("questionnaires").update({"status": "ready"}).eq("id", questionnaire_id).execute())
    except Exception as exc:
        await _db(
            lambda: db.table("questionnaires")
            .update({"status": "error", "error_message": str(exc)[:2000]})
            .eq("id", questionnaire_id)
            .execute()
        )
        raise


async def compute_audit_checkpoints(ctx) -> None:
    """Cron (daily): seals each workspace's events since the last checkpoint
    into one chained checkpoint hash (see schema.sql's `audit_chain` comment).
    Evidence packs cite the checkpoint covering a given event as proof the
    log hasn't been altered since."""
    db = get_db()
    workspaces = await _db(lambda: db.table("workspaces").select("id").execute())

    for ws in workspaces.data:
        workspace_id = ws["id"]

        last = await _db(
            lambda wid=workspace_id: db.table("audit_chain")
            .select("period_end, checkpoint_hash")
            .eq("workspace_id", wid)
            .order("period_end", desc=True)
            .limit(1)
            .execute()
        )
        period_start = last.data[0]["period_end"] if last.data else "1970-01-01T00:00:00+00:00"
        prev_hash = last.data[0]["checkpoint_hash"] if last.data else GENESIS_HASH
        period_end = datetime.now(timezone.utc).isoformat()

        events_res = await _db(
            lambda wid=workspace_id: db.table("events")
            .select("row_hash")
            .eq("workspace_id", wid)
            .gt("created_at", period_start)
            .lte("created_at", period_end)
            .order("created_at")
            .execute()
        )
        rows = events_res.data
        if not rows:
            continue

        checkpoint_hash = hashlib.sha256(("".join(r["row_hash"] for r in rows) + prev_hash).encode()).hexdigest()

        await _db(
            lambda wid=workspace_id, ph=prev_hash, ch=checkpoint_hash, ps=period_start, pe=period_end, n=len(rows): db.table(
                "audit_chain"
            )
            .insert(
                {
                    "workspace_id": wid,
                    "period_start": ps,
                    "period_end": pe,
                    "event_count": n,
                    "checkpoint_hash": ch,
                    "prev_checkpoint_hash": ph,
                }
            )
            .execute()
        )
