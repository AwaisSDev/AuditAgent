"""F4 — drafts questionnaire answers with Claude Sonnet, grounded in the
workspace's actual logged events. The model is only ever shown *already
redacted* event data and is explicitly told to cite by event id — answers
are drafts a human reviews and edits before anything is exported (see
routers/questionnaires.py; nothing here ever auto-submits anywhere)."""

import json

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import get_settings

_SYSTEM_PROMPT = """You are drafting answers to a customer security questionnaire on \
behalf of a company that uses Tracyn to log and govern its AI agents' actions. \
You will be given a question and a list of candidate log events (already PII-redacted) \
from that company's own Tracyn workspace.

Rules:
- Answer only using the provided events and general, defensible statements about how \
Tracyn's logging/approval/audit-chain features work. Never invent specifics not in \
the evidence.
- If the evidence doesn't support a confident answer, say so plainly and suggest what \
the human reviewer should add.
- Cite evidence by event id, using the exact ids given — never invent an id.
- Keep answers to 2-4 sentences; questionnaires are read by busy security reviewers.

Reply with ONLY a JSON object: {"answer": "...", "cited_event_ids": ["...", ...]}"""


class DraftedAnswer(BaseModel):
    answer: str
    cited_event_ids: list[str]


async def draft_answer(question: str, candidate_events: list[dict]) -> DraftedAnswer:
    settings = get_settings()

    if not settings.anthropic_api_key:
        # Documented as an optional, gracefully-degrading feature (see
        # config.py / backend/README.md) — without a key, still parse the
        # file and match evidence, just skip the drafted wording rather than
        # failing the whole questionnaire (worker/tasks.py::process_questionnaire
        # wraps every question in one try/except, so one hard failure here
        # used to abort every other question in the file too).
        return DraftedAnswer(
            answer="Draft generation is unavailable (no Anthropic API key configured) — please write this answer manually.",
            cited_event_ids=[],
        )

    events_for_prompt = [
        {
            "event_id": e["id"],
            "action_type": e["action_type"],
            "action_name": e["action_name"],
            "status": e["status"],
            "created_at": e["created_at"],
        }
        for e in candidate_events
    ]

    user_content = json.dumps({"question": question, "candidate_events": events_for_prompt})

    try:
        client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30.0)
        response = await client.messages.create(
            model=settings.anthropic_sonnet_model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        parsed = json.loads(text)
        valid_ids = {e["id"] for e in candidate_events}
        cited = [eid for eid in parsed.get("cited_event_ids", []) if eid in valid_ids]
        return DraftedAnswer(answer=parsed["answer"], cited_event_ids=cited)
    except (json.JSONDecodeError, KeyError):
        return DraftedAnswer(
            answer="Draft generation failed to parse — please write this answer manually.",
            cited_event_ids=[],
        )
    except Exception:
        # Same "fail closed, keep going" contract as classification.py's
        # redact_with_llm: a transient Anthropic outage or timeout for one
        # question must not take the rest of the questionnaire down with it.
        return DraftedAnswer(
            answer="Draft generation failed (a temporary error) — please write this answer manually.",
            cited_event_ids=[],
        )
