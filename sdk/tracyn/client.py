from __future__ import annotations

import asyncio
import atexit
import inspect
import queue
import sys
import threading
import time
from functools import wraps
from typing import Any, Callable, TypeVar

import httpx

from tracyn.exceptions import ApprovalDeniedError, ApprovalTimeoutError
from tracyn.hashing import hash_prompt
from tracyn.policy import Policy

F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_BASE_URL = "https://mcp.tracyn.online"
POLL_INTERVAL_SECONDS = 2.0
# An approval poll can run for up to the server's approval window (30 min by
# default) — a single transient network blip during that whole span
# shouldn't kill the wait the way it would a one-shot request. Only give up
# after several consecutive failures, which is what actually indicates the
# backend is down rather than a momentary hiccup.
MAX_CONSECUTIVE_POLL_ERRORS = 5


def _is_transient_poll_error(exc: Exception) -> bool:
    """A dropped connection is the obvious transient case, but a bare 5xx
    from the backend belongs in the same bucket -- it means the *poll*
    request failed, not that the decision itself didn't happen (that lives
    in a separate row, decided independently of this GET). Treating a 5xx
    as immediately fatal was aborting the whole approval wait -- raising
    out of track() and skipping the outcome-logging call entirely -- on a
    single backend hiccup, even when a human had already correctly decided
    the request. A 4xx (bad key, approval genuinely not found) is a real
    problem retrying won't fix, so only 5xx gets the same tolerance as a
    transport-level failure."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.TransportError)


class Tracyn:
    """
        from tracyn import Tracyn

        audit = Tracyn(api_key="al_live_...", agent_name="support-bot")

        @audit.track(action_type="external", action_name="send_email")
        async def send_email(to, subject, body):
            ...

    Logging is fire-and-forget onto a background thread (see `_enqueue_event`)
    so `track()` adds sub-5ms overhead to the wrapped call itself — the only
    time it genuinely blocks is when the policy requires human approval,
    which is the point of that feature, not overhead.
    """

    def __init__(
        self,
        api_key: str,
        agent_name: str,
        base_url: str = DEFAULT_BASE_URL,
        policy_yaml: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key
        self.agent_name = agent_name
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        # F2: "SDK reads policy on init" — pass policy_yaml explicitly to use
        # the repo-local YAML file instead of fetching the dashboard's copy.
        self.policy = Policy(policy_yaml) if policy_yaml else self._fetch_policy()

        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()

        # The flush thread is a daemon so it never blocks process exit, but
        # that means a normal (non-crash) exit kills it mid-queue unless
        # something flushes first. Registering this here — instead of
        # documenting "remember to call atexit.register(audit.close)" as a
        # quickstart step — means a dropped audit event on ordinary exit
        # isn't something every integration has to remember to prevent.
        atexit.register(self.close)

    # -- setup -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _fetch_policy(self) -> Policy:
        try:
            resp = httpx.get(f"{self.base_url}/v1/sdk/policy", headers=self._headers(), timeout=self.timeout_seconds)
            resp.raise_for_status()
            return Policy(resp.json()["rules_yaml"])
        except Exception:
            # Never let a network hiccup at import/init time crash the host app.
            return Policy.default()

    # -- background event flushing ---------------------------------------

    def _flush_loop(self) -> None:
        client = httpx.Client(timeout=self.timeout_seconds)
        while not self._stop.is_set() or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._send_with_retry(client, event)
        client.close()

    def _send_with_retry(self, client: httpx.Client, event: dict, attempts: int = 3) -> None:
        # A silently-dropped event defeats the entire point of an audit log,
        # so this retries transient failures and — unlike a bare `except:
        # pass` — actually surfaces a final failure instead of hiding it.
        last_error: Exception | str | None = None
        for attempt in range(attempts):
            try:
                resp = client.post(f"{self.base_url}/v1/events", json=event, headers=self._headers())
                if resp.status_code < 300:
                    return
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as exc:
                last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))
        print(
            f"[tracyn] WARNING: failed to log event {event.get('action_name')!r} "
            f"after {attempts} attempts: {last_error}",
            file=sys.stderr,
        )

    def flush(self, timeout: float = 5.0) -> None:
        """Blocks until queued events are sent. Call before process exit
        (e.g. in a `finally` block or `atexit` handler) so the last few
        actions before a crash/shutdown aren't lost."""
        deadline = time.monotonic() + timeout
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.05)

    def close(self) -> None:
        # Idempotent: atexit will call this even if the caller also calls it
        # explicitly (e.g. in a `finally` block), and joining an
        # already-finished thread twice would otherwise be harmless but the
        # double flush() wait is not free.
        if self._closed:
            return
        self._closed = True
        self.flush()
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _enqueue_event(self, **fields: Any) -> None:
        self._queue.put_nowait(fields)  # in-memory put — this is the entire "overhead"

    # -- approval flow -----------------------------------------------------

    def _request_approval_sync(self, action_type: str, action_name: str, inputs: dict) -> dict:
        client = httpx.Client(timeout=self.timeout_seconds)
        try:
            resp = client.post(
                f"{self.base_url}/v1/approvals/request",
                json={
                    "agent_name": self.agent_name,
                    "action_type": action_type,
                    "action_name": action_name,
                    "inputs_preview": inputs,
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
            approval_id = resp.json()["approval_id"]

            consecutive_errors = 0
            while True:
                time.sleep(POLL_INTERVAL_SECONDS)
                try:
                    status_resp = client.get(f"{self.base_url}/v1/approvals/{approval_id}/status", headers=self._headers())
                    status_resp.raise_for_status()
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if not _is_transient_poll_error(exc):
                        raise
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                        raise
                    continue
                consecutive_errors = 0
                status = status_resp.json()
                if status["status"] != "pending":
                    return status
        finally:
            client.close()

    async def _request_approval_async(self, action_type: str, action_name: str, inputs: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(
                f"{self.base_url}/v1/approvals/request",
                json={
                    "agent_name": self.agent_name,
                    "action_type": action_type,
                    "action_name": action_name,
                    "inputs_preview": inputs,
                },
                headers=self._headers(),
            )
            resp.raise_for_status()
            approval_id = resp.json()["approval_id"]

            consecutive_errors = 0
            while True:
                # asyncio.sleep, not time.sleep: this must not block the host
                # app's event loop for the duration of the approval window.
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                try:
                    status_resp = await client.get(f"{self.base_url}/v1/approvals/{approval_id}/status", headers=self._headers())
                    status_resp.raise_for_status()
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if not _is_transient_poll_error(exc):
                        raise
                    consecutive_errors += 1
                    if consecutive_errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                        raise
                    continue
                consecutive_errors = 0
                status = status_resp.json()
                if status["status"] != "pending":
                    return status

    # -- the public decorator ---------------------------------------------

    def track(
        self,
        action_type: str,
        action_name: str | None = None,
        cost_fn: Callable[[Any], float] | None = None,
    ):
        """Wraps a tool call: enforces approval per policy (F2/F3), then logs
        the call — inputs, output, model, prompt hash, cost, latency (F1) —
        to Tracyn. Works on both sync and async functions."""

        def decorator(func: F) -> F:
            name = action_name or func.__name__

            if inspect.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    inputs = _bind_inputs(func, args, kwargs)

                    if self.policy.requires_approval(action_type, name):
                        decision = await self._request_approval_async(action_type, name, inputs)
                        self._log_approval_outcome(action_type, name, inputs, decision)
                        _raise_if_denied(name, decision)

                    start = time.perf_counter()
                    try:
                        output = await func(*args, **kwargs)
                    except Exception as exc:
                        latency_ms = int((time.perf_counter() - start) * 1000)
                        self._log_error(action_type, name, inputs, exc, latency_ms)
                        raise
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    self._log_success(action_type, name, inputs, output, latency_ms, cost_fn)
                    return output

                return async_wrapper  # type: ignore[return-value]

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                inputs = _bind_inputs(func, args, kwargs)

                if self.policy.requires_approval(action_type, name):
                    decision = self._request_approval_sync(action_type, name, inputs)
                    self._log_approval_outcome(action_type, name, inputs, decision)
                    _raise_if_denied(name, decision)

                start = time.perf_counter()
                try:
                    output = func(*args, **kwargs)
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    self._log_error(action_type, name, inputs, exc, latency_ms)
                    raise
                latency_ms = int((time.perf_counter() - start) * 1000)
                self._log_success(action_type, name, inputs, output, latency_ms, cost_fn)
                return output

            return sync_wrapper  # type: ignore[return-value]

        return decorator

    # -- logging helpers ---------------------------------------------------

    def _log_success(self, action_type: str, name: str, inputs: dict, output: Any, latency_ms: int, cost_fn) -> None:
        cost = None
        if cost_fn:
            try:
                cost = cost_fn(output)
            except Exception:
                cost = None
        self._enqueue_event(
            agent_name=self.agent_name,
            action_type=action_type,
            action_name=name,
            inputs=inputs,
            output=_safe_output(output),
            model=inputs.get("model"),
            prompt_hash=hash_prompt(inputs),
            cost_usd=cost,
            latency_ms=latency_ms,
            status="completed",
        )

    def _log_error(self, action_type: str, name: str, inputs: dict, exc: Exception, latency_ms: int) -> None:
        # The wrapped call raised. Still worth a row: "every action, on the
        # record" includes the ones that failed, not just the ones that
        # succeeded — an audit trail with a hole where errors go is a worse
        # product than one with fewer features.
        self._enqueue_event(
            agent_name=self.agent_name,
            action_type=action_type,
            action_name=name,
            inputs=inputs,
            output={"error": type(exc).__name__, "message": str(exc)[:2000]},
            model=inputs.get("model"),
            prompt_hash=hash_prompt(inputs),
            cost_usd=None,
            latency_ms=latency_ms,
            status="error",
        )

    def _log_approval_outcome(self, action_type: str, name: str, inputs: dict, decision: dict) -> None:
        self._enqueue_event(
            agent_name=self.agent_name,
            action_type=action_type,
            action_name=name,
            inputs=inputs,
            output=None,
            model=inputs.get("model"),
            prompt_hash=hash_prompt(inputs),
            cost_usd=None,
            latency_ms=None,
            status=decision["status"],
            approval_id=decision["id"],
        )


def _raise_if_denied(name: str, decision: dict) -> None:
    if decision["status"] == "approved":
        return
    if decision["status"] == "denied_timeout":
        raise ApprovalTimeoutError(name)
    raise ApprovalDeniedError(name, decision.get("decision_by"), decision.get("decision_note"))


def _bind_inputs(func: Callable, args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        return {k: v for k, v in bound.arguments.items() if k != "self"}
    except TypeError:
        return {"args": [repr(a) for a in args], "kwargs": kwargs}


def _safe_output(output: Any) -> Any:
    import json

    try:
        json.dumps(output, default=str)
        return output
    except Exception:
        return repr(output)
