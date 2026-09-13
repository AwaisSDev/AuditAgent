import asyncio
from functools import lru_cache
from typing import Callable, TypeVar

import httpx
from supabase import Client, create_client

from app.config import get_settings

T = TypeVar("T")


@lru_cache
def get_db() -> Client:
    """Service-role Supabase client. Bypasses RLS — only ever used server-side."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def run_db(fn: Callable[..., T], *args, attempts: int = 3, **kwargs) -> T:
    """Runs a blocking supabase-py call (e.g. `lambda: db.table(...).execute()`)
    off the event loop, so one slow Supabase round trip doesn't stall every
    other concurrent request/job — supabase-py's client is synchronous, and
    calling it directly inside an `async def` would otherwise block the whole
    event loop for the duration of the network call.

    Retries on transport-level failures (e.g. "Server disconnected"): on a
    free-tier container, a burst of concurrent requests occasionally drops
    the connection to Supabase's REST endpoint mid-request. That's transient,
    not a real failure of the request itself, so it's worth a couple of
    quick retries before giving up.
    """
    for attempt in range(attempts):
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except httpx.TransportError:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))
    raise AssertionError("unreachable")  # for the type checker; the loop always returns or raises
