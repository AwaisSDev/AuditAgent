"""F6 — Claude MCP server for AuditAgent.

Exposes a workspace's logs, approvals, and compliance posture as MCP tools
so a developer can ask about their agent conversationally inside Claude
(Claude Desktop, Claude Code, or any other MCP client), instead of opening
the dashboard. This is a thin client over the same backend the SDK and
dashboard use (app/routers/mcp_data.py) — no logic is duplicated here.
"""

from mcp.server.fastmcp import FastMCP

from auditagent_mcp import client

mcp = FastMCP("auditagent")


@mcp.tool()
def get_recent_actions(limit: int = 20, action_type: str | None = None, status: str | None = None) -> list[dict]:
    """Get the most recent logged AI agent actions for this workspace.

    Args:
        limit: max number of events to return (default 20, max 100).
        action_type: optional filter, e.g. "external" or "data_access".
        status: optional filter, one of completed/approved/rejected/denied_timeout/error.
    """
    return client.get_recent_actions(limit=limit, action_type=action_type, status=status)


@mcp.tool()
def get_pending_approvals() -> list[dict]:
    """Get all approval requests currently awaiting a human decision."""
    return client.get_pending_approvals()


@mcp.tool()
def draft_questionnaire_answers(questions: list[str]) -> list[dict]:
    """Draft answers to one or more security-questionnaire-style questions,
    grounded in this workspace's actual logged events, with cited event ids.

    This is a draft only — nothing is submitted or exported. For a full
    questionnaire file (PDF/CSV/XLSX), upload it in the AuditAgent dashboard
    instead; this tool is for one-off conversational questions.

    Args:
        questions: one or more questions, e.g. ["Do you log all AI agent actions?"]
    """
    return client.draft_questionnaire_answers(questions)


@mcp.tool()
def get_compliance_summary() -> dict:
    """Get a snapshot of this workspace's compliance posture: plan, whether
    Slack/email approval routing is configured, event counts by status over
    the last 30 days, how many approvals are pending, and the most recent
    audit-chain checkpoint (proof the event log hasn't been altered since)."""
    return client.get_compliance_summary()


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
