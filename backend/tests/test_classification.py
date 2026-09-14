"""Covers redact_with_llm's fail-closed behavior: any hiccup (no API key, a
network error, a malformed/reshaped response) must return the original
Presidio-redacted data unchanged, never raise into the ingest worker."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.classification import redact_with_llm

DATA = {"note": "contact [REDACTED] about invoice", "amount": 500}


def _settings() -> SimpleNamespace:
    return SimpleNamespace(anthropic_api_key="sk-ant-fake", anthropic_haiku_model="claude-haiku-4-5")


@pytest.mark.anyio
async def test_redact_with_llm_returns_empty_input_unchanged():
    assert await redact_with_llm({}) == {}


@pytest.mark.anyio
async def test_redact_with_llm_applies_additional_redactions(monkeypatch):
    monkeypatch.setattr("app.services.classification.get_settings", _settings)
    fake_block = SimpleNamespace(type="text", text='{"note": "contact [REDACTED] about invoice", "amount": "[REDACTED]"}')
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.classification.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=fake_response)
        result = await redact_with_llm(DATA)

    assert result["amount"] == "[REDACTED]"


@pytest.mark.anyio
async def test_redact_with_llm_strips_markdown_code_fences(monkeypatch):
    monkeypatch.setattr("app.services.classification.get_settings", _settings)
    fake_block = SimpleNamespace(type="text", text='```json\n{"note": "ok", "amount": 500}\n```')
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.classification.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=fake_response)
        result = await redact_with_llm({"note": "x", "amount": 1})

    assert result == {"note": "ok", "amount": 500}


@pytest.mark.anyio
async def test_redact_with_llm_falls_back_when_keys_dont_match(monkeypatch):
    # A reshaped response (missing/extra keys) is a sign the model didn't
    # follow instructions — trust Presidio's output over a shape we can't verify.
    monkeypatch.setattr("app.services.classification.get_settings", _settings)
    fake_block = SimpleNamespace(type="text", text='{"unexpected_key": "value"}')
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.classification.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=fake_response)
        result = await redact_with_llm(DATA)

    assert result == DATA


@pytest.mark.anyio
async def test_redact_with_llm_falls_back_on_unparseable_response(monkeypatch):
    monkeypatch.setattr("app.services.classification.get_settings", _settings)
    fake_block = SimpleNamespace(type="text", text="not json")
    fake_response = SimpleNamespace(content=[fake_block])

    with patch("app.services.classification.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(return_value=fake_response)
        result = await redact_with_llm(DATA)

    assert result == DATA


@pytest.mark.anyio
async def test_redact_with_llm_falls_back_on_api_error(monkeypatch):
    monkeypatch.setattr("app.services.classification.get_settings", _settings)

    with patch("app.services.classification.AsyncAnthropic") as mock_cls:
        mock_cls.return_value.messages.create = AsyncMock(side_effect=RuntimeError("simulated outage"))
        result = await redact_with_llm(DATA)

    assert result == DATA
