import os

import httpx

# Mutable, not a frozen constant: when this package is mounted into the
# backend itself (see server.configure_backend_url, called from
# backend/app/main.py), the host app sets this to its own real origin —
# it can't rely on AUDITAGENT_BASE_URL being set before this module is
# first imported, since that depends on import order. Falls back to the
# env var (for a standalone deployment of this package) and then the
# real deployed origin as a default (for local/stdio use against the
# public API) -- auditagent.dev was never bought, so this HF Space URL
# is the actual backend, not a placeholder for a future custom domain.
_base_url = os.environ.get("AUDITAGENT_BASE_URL", "https://awais1290-auditagent.hf.space")


def set_base_url(base_url: str) -> None:
    global _base_url
    _base_url = base_url


def _client(api_key: str) -> httpx.Client:
    if not api_key:
        raise RuntimeError("No AuditAgent API key available — see README.md for setup.")
    return httpx.Client(base_url=_base_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0)


def get_recent_actions(
    api_key: str, limit: int = 20, action_type: str | None = None, status: str | None = None
) -> list[dict]:
    params = {"limit": limit}
    if action_type:
        params["action_type"] = action_type
    if status:
        params["status"] = status
    with _client(api_key) as client:
        resp = client.get("/v1/mcp/recent-actions", params=params)
        resp.raise_for_status()
        return resp.json()


def get_pending_approvals(api_key: str) -> list[dict]:
    with _client(api_key) as client:
        resp = client.get("/v1/mcp/pending-approvals")
        resp.raise_for_status()
        return resp.json()


def draft_questionnaire_answers(api_key: str, questions: list[str]) -> list[dict]:
    with _client(api_key) as client:
        resp = client.post("/v1/mcp/draft-questionnaire-answers", json=questions)
        resp.raise_for_status()
        return resp.json()


def get_compliance_summary(api_key: str) -> dict:
    with _client(api_key) as client:
        resp = client.get("/v1/mcp/compliance-summary")
        resp.raise_for_status()
        return resp.json()
