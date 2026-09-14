"""Verifies the MCP server registers exactly the four tools F6 promises,
under the expected names, and that each tool function is a thin,
argument-preserving pass-through to the corresponding client.* call --
catching any drift between the two without needing a real MCP client or
network connection."""

import asyncio
from unittest.mock import MagicMock

import pytest

from auditagent_mcp import server


def test_all_four_tools_are_registered():
    tools = asyncio.run(server.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_recent_actions",
        "get_pending_approvals",
        "draft_questionnaire_answers",
        "get_compliance_summary",
    }


def test_get_recent_actions_forwards_its_arguments(monkeypatch):
    mock = MagicMock(return_value=[{"id": "evt-1"}])
    monkeypatch.setattr(server.client, "get_recent_actions", mock)

    result = server.get_recent_actions(limit=5, action_type="external", status="completed")

    mock.assert_called_once_with(limit=5, action_type="external", status="completed")
    assert result == [{"id": "evt-1"}]


def test_get_pending_approvals_forwards_to_the_client(monkeypatch):
    mock = MagicMock(return_value=[{"id": "appr-1"}])
    monkeypatch.setattr(server.client, "get_pending_approvals", mock)

    assert server.get_pending_approvals() == [{"id": "appr-1"}]
    mock.assert_called_once_with()


def test_draft_questionnaire_answers_forwards_the_question_list(monkeypatch):
    mock = MagicMock(return_value=[{"question": "q", "answer": "a", "cited_event_ids": []}])
    monkeypatch.setattr(server.client, "draft_questionnaire_answers", mock)

    result = server.draft_questionnaire_answers(["Do you log actions?"])

    mock.assert_called_once_with(["Do you log actions?"])
    assert result[0]["answer"] == "a"


def test_get_compliance_summary_forwards_to_the_client(monkeypatch):
    mock = MagicMock(return_value={"plan": "free"})
    monkeypatch.setattr(server.client, "get_compliance_summary", mock)

    assert server.get_compliance_summary() == {"plan": "free"}
    mock.assert_called_once_with()


@pytest.mark.parametrize(
    "tool_name",
    ["get_recent_actions", "get_pending_approvals", "draft_questionnaire_answers", "get_compliance_summary"],
)
def test_every_tool_has_a_non_empty_docstring(tool_name):
    # MCP clients show this text to the model/user as the tool's description --
    # an empty one would make the tool effectively undiscoverable.
    fn = getattr(server, tool_name)
    assert fn.__doc__ and len(fn.__doc__.strip()) > 20
