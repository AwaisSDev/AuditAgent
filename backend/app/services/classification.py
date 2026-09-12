"""Secondary redaction pass via Claude Haiku.

Presidio (redaction.py) catches structured PII (emails, SSNs, credit cards...)
using regex + NER. It misses things that only make sense in context — API
keys, internal customer names mentioned in prose, business-sensitive
figures. Haiku is cheap and fast enough to run per-event and catch those.

This is deliberately *not* a separate "what kind of action is this" classifier:
action_type is explicit input from the SDK/developer (used by the policy
engine), so there's nothing to infer there. Folding "classification" into a
second redaction pass keeps this to one job instead of two.
"""

import json
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings

_SYSTEM_PROMPT = (
    "You are a data-loss-prevention filter. You will receive a JSON object that has "
    "already had common PII (names, emails, phone numbers, SSNs, credit cards) redacted "
    "as [REDACTED]. Find anything else sensitive that was missed — API keys, tokens, "
    "passwords, internal secrets, or clearly-identifying business data — and replace "
    "those substrings with [REDACTED] too. Do not change anything else: keep the same "
    "JSON structure, same keys, same non-sensitive values, verbatim. "
    "Reply with ONLY the corrected JSON object, no commentary."
)


async def redact_with_llm(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return data
    settings = get_settings()
    try:
        # An explicit timeout matters here: this runs inside the ingest
        # worker, and a hung call (no API key, a slow/unreachable network
        # path) must fail fast into the except below rather than leaving
        # the event stuck in "processing" forever with no error surfaced.
        client = AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=15.0)
        response = await client.messages.create(
            model=settings.anthropic_haiku_model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(data, default=str)}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.keys() == data.keys():
            return parsed
        return data
    except Exception:
        # Fail closed on the side of "keep Presidio's output" — never let an LLM
        # hiccup block ingest or silently drop the event.
        return data
