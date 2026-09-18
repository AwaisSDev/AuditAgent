"""Covers draft_policy's graceful-degradation and validation contract: a
proposal is never handed back unless it actually parses as a valid policy
(services/policy_engine.py), and no API key / a transient failure /
unparseable output all fail closed with proposed_yaml=None rather than
crashing or returning something the dashboard would show as a ready-to-
apply diff."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import policy_drafter
from app.services.policy_drafter import draft_policy

CURRENT_YAML = "rules:\n  - match:\n      action_type: external\n    require_approval: true\n"


def _settings(api_key: str) -> SimpleNamespace:
    return SimpleNamespace(anthropic_api_key=api_key, anthropic_sonnet_model="claude-sonnet-4-6")


@pytest.mark.anyio
async def test_draft_policy_degrades_gracefully_with_no_api_key(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings(""))

    result = await draft_policy("require approval for refunds", CURRENT_YAML)

    assert result.proposed_yaml is None
    assert "yaml" in result.explanation.lower()


@pytest.mark.anyio
async def test_draft_policy_degrades_gracefully_on_api_error(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings("sk-ant-fake"))

    with patch("app.services.policy_drafter.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("simulated Anthropic outage"))

        result = await draft_policy("require approval for deletes", CURRENT_YAML)

    assert result.proposed_yaml is None
    assert "try again" in result.explanation.lower()


@pytest.mark.anyio
async def test_draft_policy_applies_a_successful_valid_response(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings("sk-ant-fake"))

    new_yaml = "rules:\n  - match:\n      action_name: delete_*\n    require_approval: true\n  - match:\n      action_type: external\n    require_approval: true\n"
    payload = json.dumps({"proposed_yaml": new_yaml, "explanation": "Added a rule requiring approval for delete actions."})
    fake_block = SimpleNamespace(type="text", text=payload)
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.policy_drafter.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_policy("also require approval for deletes", CURRENT_YAML)

    assert result.proposed_yaml == new_yaml
    assert "delete" in result.explanation.lower()


@pytest.mark.anyio
async def test_draft_policy_rejects_a_response_claiming_yaml_that_doesnt_actually_parse(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings("sk-ant-fake"))

    fake_block = SimpleNamespace(type="text", text='{"proposed_yaml": "not: valid: policy: [[", "explanation": "Done."}')
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.policy_drafter.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_policy("do something", CURRENT_YAML)

    assert result.proposed_yaml is None
    assert "invalid" in result.explanation.lower()


@pytest.mark.anyio
async def test_draft_policy_explains_when_the_instruction_cant_be_expressed(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings("sk-ant-fake"))

    fake_block = SimpleNamespace(
        type="text",
        text='{"proposed_yaml": null, "explanation": "Refund amounts aren\'t something this policy engine can match on."}',
    )
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.policy_drafter.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_policy("require approval for refunds over $500", CURRENT_YAML)

    assert result.proposed_yaml is None
    assert "refund" in result.explanation.lower()


@pytest.mark.anyio
async def test_draft_policy_degrades_gracefully_on_unparseable_response(monkeypatch):
    monkeypatch.setattr(policy_drafter, "get_settings", lambda: _settings("sk-ant-fake"))

    fake_block = SimpleNamespace(type="text", text="not json at all")
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.policy_drafter.AsyncAnthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create = AsyncMock(return_value=fake_response)

        result = await draft_policy("do something", CURRENT_YAML)

    assert result.proposed_yaml is None
    assert "parse" in result.explanation.lower()
