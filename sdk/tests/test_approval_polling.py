"""Covers the polling-resilience fix: an approval wait can run for up to the
server's approval window (30 min by default), so a momentary network blip
mid-poll must not kill the whole wait the way it would a one-shot request —
only several *consecutive* failures should. Discovered as a real gap while
live-testing against a real backend restart mid-poll."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from audagent.client import MAX_CONSECUTIVE_POLL_ERRORS, AuditAgent


def _make_agent():
    return AuditAgent(api_key="test", agent_name="test-agent", policy_yaml="rules: []")


def _response(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    resp.raise_for_status = MagicMock() if status_code < 400 else MagicMock(side_effect=httpx.HTTPStatusError("err", request=MagicMock(), response=resp))
    return resp


def test_sync_polling_survives_transient_network_errors():
    agent = _make_agent()
    fake_client = MagicMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    # Two transient failures, then a resolved status.
    fake_client.get.side_effect = [
        httpx.ConnectError("boom"),
        httpx.ReadError("boom again"),
        _response({"status": "approved", "id": "appr-1"}),
    ]

    with patch("audagent.client.httpx.Client", return_value=fake_client), patch("time.sleep"):
        result = agent._request_approval_sync("external", "send_email", {})

    assert result["status"] == "approved"
    assert fake_client.get.call_count == 3


def test_sync_polling_gives_up_after_too_many_consecutive_errors():
    agent = _make_agent()
    fake_client = MagicMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    fake_client.get.side_effect = httpx.ConnectError("persistent outage")

    with patch("audagent.client.httpx.Client", return_value=fake_client), patch("time.sleep"):
        with pytest.raises(httpx.ConnectError):
            agent._request_approval_sync("external", "send_email", {})

    assert fake_client.get.call_count == MAX_CONSECUTIVE_POLL_ERRORS


def test_sync_polling_survives_a_transient_5xx_from_the_backend():
    # A 5xx means the *poll* request failed, not that the decision itself
    # didn't happen -- treat it the same as a dropped connection rather than
    # aborting the whole wait (and skipping the outcome-logging call that
    # would otherwise follow) on one backend hiccup.
    agent = _make_agent()
    fake_client = MagicMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    fake_client.get.side_effect = [
        _response({}, status_code=503),
        _response({"status": "approved", "id": "appr-1"}),
    ]

    with patch("audagent.client.httpx.Client", return_value=fake_client), patch("time.sleep"):
        result = agent._request_approval_sync("external", "send_email", {})

    assert result["status"] == "approved"
    assert fake_client.get.call_count == 2


def test_sync_polling_does_not_retry_a_4xx_from_the_backend():
    # Unlike a 5xx, a 4xx (bad key, approval genuinely not found) is a real
    # problem retrying can't fix -- it should raise immediately, not burn
    # through MAX_CONSECUTIVE_POLL_ERRORS attempts first.
    agent = _make_agent()
    fake_client = MagicMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    fake_client.get.return_value = _response({}, status_code=404)

    with patch("audagent.client.httpx.Client", return_value=fake_client), patch("time.sleep"):
        with pytest.raises(httpx.HTTPStatusError):
            agent._request_approval_sync("external", "send_email", {})

    assert fake_client.get.call_count == 1


def test_async_polling_survives_a_transient_5xx_from_the_backend():
    agent = _make_agent()
    fake_client = AsyncMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    fake_client.get.side_effect = [
        _response({}, status_code=500),
        _response({"status": "rejected", "id": "appr-1"}),
    ]
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch("audagent.client.httpx.AsyncClient", return_value=fake_client), patch("asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(agent._request_approval_async("external", "send_email", {}))

    assert result["status"] == "rejected"
    assert fake_client.get.call_count == 2


def test_async_polling_survives_transient_network_errors():
    agent = _make_agent()
    fake_client = AsyncMock()
    fake_client.post.return_value = _response({"approval_id": "appr-1"})
    fake_client.get.side_effect = [
        httpx.ConnectError("boom"),
        _response({"status": "rejected", "id": "appr-1"}),
    ]
    fake_client.__aenter__.return_value = fake_client
    fake_client.__aexit__.return_value = False

    with patch("audagent.client.httpx.AsyncClient", return_value=fake_client), patch("asyncio.sleep", new=AsyncMock()):
        result = asyncio.run(agent._request_approval_async("external", "send_email", {}))

    assert result["status"] == "rejected"
    assert fake_client.get.call_count == 2
