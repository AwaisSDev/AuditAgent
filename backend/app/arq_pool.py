"""Lazily-created arq Redis pool, independent of FastAPI's lifespan events.

Why this exists: on the Hugging Face Space deployment, Gradio owns the ASGI
server and the FastAPI app is *mounted* under it (see space_app.py). Starlette
does not forward lifespan startup/shutdown events into mounted sub-applications
— only the outermost app served by the ASGI server gets them. That meant
app.state.arq_pool, set in main.py's lifespan, was simply never created there,
and every ingest call hit an AttributeError. A pool created on first real use
works the same way under plain uvicorn (local dev), Railway, or Gradio-mounted
Spaces, since it never depends on which app the server thinks is "the" app.
"""

import asyncio

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.config import get_settings

_pool: ArqRedis | None = None
_lock = asyncio.Lock()


async def get_arq_pool() -> ArqRedis | None:
    global _pool
    if _pool is not None:
        return _pool
    async with _lock:
        if _pool is not None:  # another request won the race while we waited
            return _pool
        try:
            _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        except Exception as exc:  # noqa: BLE001 — Redis being down must never crash a request
            print(f"WARNING: could not connect to Redis ({exc}); ingest/questionnaire uploads unavailable until it recovers.")
            return None
        return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
