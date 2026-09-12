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
behalf of a company that uses AuditAgent to log and govern its AI agents' actions. \
You will be given a question and a list of candidate log events (already PII-redacted) \
from that company's own AuditAgent workspace.

Rules:
- Answer only using the provided events and general, defensible statements about how \
AuditAgent's logging/approval/audit-chain features work. Never invent specifics not in \
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
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=30.0)

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

    response = await client.messages.create(
        model=settings.anthropic_sonnet_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()

    try:
        parsed = json.loads(text)
        valid_ids = {e["id"] for e in candidate_events}
        cited = [eid for eid in parsed.get("cited_event_ids", []) if eid in valid_ids]
        return DraftedAnswer(answer=parsed["answer"], cited_event_ids=cited)
    except (json.JSONDecodeError, KeyError):
        return DraftedAnswer(
            answer="Draft generation failed to parse — please write this answer manually.",
            cited_event_ids=[],
        )
