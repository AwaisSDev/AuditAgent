"""In-process implementation of auditagent_mcp.server.DataProvider.

Wired in via configure_data_provider (see main.py) so the MCP tools --
mounted inside this same backend -- call straight into this process's
own route logic instead of making an HTTP request back out to this
server's own public hostname. That self-referential round trip (out
through the Space's ingress/proxy and back in) is what was actually
timing out in production, not the placeholder-URL bug fixed just before
it -- see the commit that added this file for the concrete symptom.

Reuses mcp_data.py's own route functions directly rather than
duplicating their DB logic: FastAPI route registration doesn't change a
function's normal callability, so passing `auth=` explicitly here just
overrides the `Depends(get_api_key_auth)` default, no HTTP request or
FastAPI dependency-injection machinery involved.
"""

from app.routers.mcp_data import (
    compliance_summary,
    draft_questionnaire_answers as _draft_questionnaire_answers,
    pending_approvals,
    recent_actions,
)
from app.security import verify_api_key


class InvalidApiKeyError(Exception):
    pass


class BackendDataProvider:
    async def _auth(self, api_key: str):
        auth = await verify_api_key(api_key)
        if auth is None:
            raise InvalidApiKeyError("Invalid API key")
        return auth

    async def get_recent_actions(
        self, api_key: str, *, limit: int = 20, action_type: str | None = None, status: str | None = None
    ) -> list[dict]:
        auth = await self._auth(api_key)
        return await recent_actions(limit=limit, action_type=action_type, status=status, auth=auth)

    async def get_pending_approvals(self, api_key: str) -> list[dict]:
        auth = await self._auth(api_key)
        return await pending_approvals(auth=auth)

    async def draft_questionnaire_answers(self, api_key: str, questions: list[str]) -> list[dict]:
        auth = await self._auth(api_key)
        return await _draft_questionnaire_answers(questions, auth=auth)

    async def get_compliance_summary(self, api_key: str) -> dict:
        auth = await self._auth(api_key)
        return await compliance_summary(auth=auth)
