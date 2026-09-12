import os

import httpx

BASE_URL = os.environ.get("AUDITAGENT_BASE_URL", "https://api.auditagent.dev")
API_KEY = os.environ.get("AUDITAGENT_API_KEY")


def _client() -> httpx.Client:
    if not API_KEY:
        raise RuntimeError("AUDITAGENT_API_KEY is not set — see README.md for setup.")
    return httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30.0)


def get_recent_actions(limit: int = 20, action_type: str | None = None, status: str | None = None) -> list[dict]:
    params = {"limit": limit}
    if action_type:
        params["action_type"] = action_type
    if status:
        params["status"] = status
    with _client() as client:
        resp = client.get("/v1/mcp/recent-actions", params=params)
        resp.raise_for_status()
        return resp.json()


def get_pending_approvals() -> list[dict]:
    with _client() as client:
        resp = client.get("/v1/mcp/pending-approvals")
        resp.raise_for_status()
        return resp.json()


def draft_questionnaire_answers(questions: list[str]) -> list[dict]:
    with _client() as client:
        resp = client.post("/v1/mcp/draft-questionnaire-answers", json=questions)
        resp.raise_for_status()
        return resp.json()


def get_compliance_summary() -> dict:
    with _client() as client:
        resp = client.get("/v1/mcp/compliance-summary")
        resp.raise_for_status()
        return resp.json()
