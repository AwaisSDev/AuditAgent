"""Unit tests for run_db's retry logic: transient httpx.TransportError
(the "Server disconnected" case documented in db.py's own docstring) gets
retried with backoff, a non-transport error propagates immediately without
retrying, and exhausting all attempts re-raises the last error rather than
hanging or swallowing it."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.db import run_db


@pytest.mark.anyio
async def test_run_db_returns_the_result_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    result = await run_db(fn)

    assert result == "ok"
    assert len(calls) == 1


@pytest.mark.anyio
async def test_run_db_retries_on_transport_error_then_succeeds(monkeypatch):
    monkeypatch.setattr("app.db.asyncio.sleep", AsyncMock())
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.TransportError("Server disconnected")
        return "recovered"

    result = await run_db(fn, attempts=3)

    assert result == "recovered"
    assert attempts["count"] == 3


@pytest.mark.anyio
async def test_run_db_raises_after_exhausting_all_attempts(monkeypatch):
    monkeypatch.setattr("app.db.asyncio.sleep", AsyncMock())
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        raise httpx.TransportError("Server disconnected")

    with pytest.raises(httpx.TransportError):
        await run_db(fn, attempts=3)

    assert attempts["count"] == 3


@pytest.mark.anyio
async def test_run_db_does_not_retry_a_non_transport_error():
    attempts = {"count": 0}

    def fn():
        attempts["count"] += 1
        raise ValueError("not a transport error")

    with pytest.raises(ValueError):
        await run_db(fn, attempts=3)

    assert attempts["count"] == 1


@pytest.mark.anyio
async def test_run_db_passes_through_args_and_kwargs():
    def fn(a, b, c=None):
        return (a, b, c)

    result = await run_db(fn, 1, 2, c=3)

    assert result == (1, 2, 3)
