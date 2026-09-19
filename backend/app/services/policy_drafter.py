"""F2 -- turns a plain-English instruction into a proposed policy YAML edit.

The result is always shown to the user as a diff to confirm (see
routers/policies.py's /policy/draft endpoint and the dashboard's Policy
page) -- this module never writes to the database itself. That matters
because the policy engine (services/policy_engine.py) can only match on
an event's `action_type`/`action_name` strings via fnmatch globs; it has
no visibility into an event's `inputs` payload (amounts, customer ids,
etc.). An instruction like "require approval for refunds over $500" is
not expressible here, and silently inventing a `match` field the engine
never checks would produce a rule that looks right and does nothing --
worse than refusing. The prompt below tells the model to say so instead.
"""

import json

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.config import get_settings
from app.services.policy_engine import PolicyParseError, parse_policy

_SYSTEM_PROMPT = """You edit Tracyn policy YAML from a plain-English instruction. \
Tracyn lets an AI agent's actions run automatically or blocks on a human approval, \
decided by this policy.

The exact schema (nothing else is valid):

    rules:
      - match:
          action_type: external   # and/or action_name
        require_approval: true    # or false

Rules:
- `match` may contain `action_type`, `action_name`, or both. There is NO other matchable \
field -- the engine never looks at an event's inputs/output/cost/amount/customer/etc., only \
these two strings. If the instruction needs anything else (an amount, a customer name, \
content of the request), it CANNOT be expressed here.
- Pattern values support `*` glob wildcards (fnmatch), e.g. "delete_*".
- Rules are evaluated top to bottom; the FIRST matching rule wins and the rest are never \
checked. An event that matches no rule runs automatically (no approval). When adding a rule \
that should override a broader existing one, place the more specific rule BEFORE the \
broader one in the list.
- `action_type` is whatever the SDK caller labels it (commonly "internal", "external", or \
"data_access", but any string is allowed). `action_name` is a free-text action label \
(e.g. "send_email", "delete_user", "send_refund").

You will be given the workspace's current policy YAML and an instruction. Reply with ONLY \
a JSON object, no other text:

    {"proposed_yaml": "<full new rules_yaml>" or null, "explanation": "<one or two sentences>"}

Set `proposed_yaml` to null (with `explanation` saying why, in plain English) when the \
instruction can't be expressed with only action_type/action_name matching. Otherwise \
`proposed_yaml` must be the COMPLETE new policy (not a diff/fragment) -- carry over every \
existing rule the instruction doesn't ask to change."""


class PolicyDraft(BaseModel):
    proposed_yaml: str | None
    explanation: str


async def draft_policy(instruction: str, current_yaml: str) -> PolicyDraft:
    settings = get_settings()

    if not settings.anthropic_api_key:
        return PolicyDraft(
            proposed_yaml=None,
            explanation="Plain-English policy editing is unavailable (no Anthropic API key configured) -- edit the YAML directly below.",
        )

    user_content = json.dumps({"current_policy_yaml": current_yaml, "instruction": instruction})

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
        proposed_yaml = parsed.get("proposed_yaml")
        explanation = parsed["explanation"]
    except (json.JSONDecodeError, KeyError):
        return PolicyDraft(proposed_yaml=None, explanation="Draft generation failed to parse -- please edit the YAML directly.")
    except Exception:
        # Same "fail closed" contract as claude_client.draft_answer -- a
        # transient Anthropic outage must surface as "try again", not a 500.
        return PolicyDraft(proposed_yaml=None, explanation="Draft generation failed (a temporary error) -- please try again.")

    if proposed_yaml is None:
        return PolicyDraft(proposed_yaml=None, explanation=explanation)

    try:
        parse_policy(proposed_yaml)
    except PolicyParseError:
        # The model's own claim that this YAML is valid isn't trustworthy
        # enough to skip re-checking it against the real parser -- an
        # unconfirmed proposal must never reach the diff UI as if it were
        # ready to apply.
        return PolicyDraft(proposed_yaml=None, explanation="Draft generation produced an invalid policy -- please try rephrasing, or edit the YAML directly.")

    return PolicyDraft(proposed_yaml=proposed_yaml, explanation=explanation)
