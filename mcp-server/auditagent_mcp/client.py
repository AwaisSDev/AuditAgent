import os

import httpx

BASE_URL = os.environ.get("AUDITAGENT_BASE_URL", "https://api.auditagent.dev")


def _client(api_key: str) -> httpx.Client:
    if not api_key:
        raise RuntimeError("No AuditAgent API key available — see README.md for setup.")
    return httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30.0)


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
