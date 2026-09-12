"""Single source of truth for the numbers in the pricing table (F9). Keeping
these in one place means the ingest cap, agent cap, and questionnaire cap
can't silently drift out of sync with what's advertised on the pricing page."""

PLAN_AGENT_LIMITS: dict[str, int | None] = {"free": 1, "starter": 5, "growth": None, "enterprise": None}
PLAN_EVENT_LIMITS: dict[str, int | None] = {"free": 1_000, "starter": 50_000, "growth": None, "enterprise": None}
PLAN_QUESTIONNAIRE_LIMITS: dict[str, int | None] = {"free": 1, "starter": 5, "growth": None, "enterprise": None}


def agent_limit(plan: str) -> int | None:
    return PLAN_AGENT_LIMITS.get(plan, PLAN_AGENT_LIMITS["free"])


def event_limit(plan: str) -> int | None:
    return PLAN_EVENT_LIMITS.get(plan, PLAN_EVENT_LIMITS["free"])


def questionnaire_limit(plan: str) -> int | None:
    return PLAN_QUESTIONNAIRE_LIMITS.get(plan, PLAN_QUESTIONNAIRE_LIMITS["free"])
