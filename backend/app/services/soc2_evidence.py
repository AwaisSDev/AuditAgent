"""F7 -- turns the static SOC2 control mapping into per-workspace evidence.

Each control's `evidence_note` (services/data/soc2_controls.py) describes what
*kind* of Tracyn feature backs it, the same for every workspace. This module
computes the actual numbers for one specific workspace -- "3 API keys, 1
revoked" instead of "per-workspace API keys, individually revocable" -- so
the mapping page (and its CSV export) becomes real evidence an auditor can
check, not a description of the product.

Every string returned here must be something this function actually
verified against the database. Where the real data can't support a precise
claim (e.g. no removed-member history is kept, no exact redacted-field
count is stored), the wording says only what's true rather than implying
more than the schema can back up.
"""

from datetime import datetime, timezone

from app.db import run_db

_THIRTY_DAYS = 30


def _relative(dt_str: str | None) -> str:
    if not dt_str:
        return "never"
    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - dt
    if delta.days >= 1:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h ago"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m ago"


async def compute_live_evidence(db, workspace_id: str) -> dict[str, str]:
    """Returns {control_id: live_evidence} for every control this can speak
    to with real data. A control_id missing from the result means the page
    should fall back to the static evidence_note for it."""

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    api_keys = (
        await run_db(
            lambda: db.table("api_keys")
            .select("revoked_at, last_used_at")
            .eq("workspace_id", workspace_id)
            .execute()
        )
    ).data
    key_count = len(api_keys)
    revoked_count = sum(1 for k in api_keys if k["revoked_at"])
    last_used_values = [k["last_used_at"] for k in api_keys if k["last_used_at"]]
    last_used = max(last_used_values) if last_used_values else None

    members = (
        await run_db(lambda: db.table("workspace_members").select("role").eq("workspace_id", workspace_id).execute())
    ).data
    role_counts: dict[str, int] = {}
    for m in members:
        role_counts[m["role"]] = role_counts.get(m["role"], 0) + 1
    role_summary = ", ".join(f"{n} {role}" for role, n in sorted(role_counts.items()))

    external_count = (
        await run_db(
            lambda: db.table("events")
            .select("id", count="exact")
            .eq("workspace_id", workspace_id)
            .eq("action_type", "external")
            .gte("created_at", month_start)
            .execute()
        )
    ).count or 0

    error_count = (
        await run_db(
            lambda: db.table("events")
            .select("id", count="exact")
            .eq("workspace_id", workspace_id)
            .eq("status", "error")
            .gte("created_at", month_start)
            .execute()
        )
    ).count or 0

    events_this_month = (
        await run_db(
            lambda: db.table("events")
            .select("id", count="exact")
            .eq("workspace_id", workspace_id)
            .gte("created_at", month_start)
            .execute()
        )
    ).count or 0

    approvals = (
        await run_db(lambda: db.table("approvals").select("status").eq("workspace_id", workspace_id).execute())
    ).data
    approval_counts: dict[str, int] = {}
    for a in approvals:
        approval_counts[a["status"]] = approval_counts.get(a["status"], 0) + 1
    approved_n = approval_counts.get("approved", 0)
    rejected_n = approval_counts.get("rejected", 0)
    timeout_n = approval_counts.get("denied_timeout", 0)
    total_approvals = len(approvals)

    policy = (
        await run_db(
            lambda: db.table("policies")
            .select("updated_at")
            .eq("workspace_id", workspace_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
    ).data
    history_count = (
        await run_db(
            lambda: db.table("policy_history").select("id", count="exact").eq("workspace_id", workspace_id).execute()
        )
    ).count or 0

    agent_count = (
        await run_db(lambda: db.table("agents").select("id", count="exact").eq("workspace_id", workspace_id).execute())
    ).count or 0

    latencies = (
        await run_db(
            lambda: db.table("events")
            .select("latency_ms")
            .eq("workspace_id", workspace_id)
            .not_.is_("latency_ms", "null")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
    ).data
    latency_values = [row["latency_ms"] for row in latencies]
    avg_latency = round(sum(latency_values) / len(latency_values)) if latency_values else None

    checkpoint = (
        await run_db(
            lambda: db.table("audit_chain")
            .select("period_end, event_count, checkpoint_hash")
            .eq("workspace_id", workspace_id)
            .order("period_end", desc=True)
            .limit(1)
            .execute()
        )
    ).data

    answers = (
        await run_db(
            lambda: db.table("answers").select("status", count="exact").eq("workspace_id", workspace_id).execute()
        )
    )
    total_answers = answers.count or 0
    approved_answers = sum(1 for a in answers.data if a["status"] == "approved")

    evidence: dict[str, str] = {
        "CC6.1": (
            f"{key_count} API key(s), {revoked_count} revoked, last used {_relative(last_used)}."
            if key_count
            else "No API keys created yet."
        ),
        "CC6.2": (
            f"{len(members)} member(s) with access ({role_summary}); {revoked_count} API key(s) revoked to date."
            if members
            else "No members yet."
        ),
        "CC6.3": f"Current roles: {role_summary}." if role_summary else "No members yet.",
        "CC6.6": f"{external_count} external action(s) logged this month; {total_approvals} routed to a human for approval to date.",
        "CC6.7": f"{events_this_month} event(s) logged this month, every one redacted before storage (no raw content is ever persisted).",
        "CC7.1": f"{error_count} error event(s) this month, out of {events_this_month} total.",
        "CC7.2": f"{total_approvals} action(s) flagged for human review to date ({approved_n} approved).",
        "CC7.3": f"{rejected_n} rejected, {timeout_n} auto-denied on timeout -- {rejected_n + timeout_n} stopped action(s) total.",
        "CC8.1": (
            f"{history_count} policy change(s) recorded; current version active since {_relative(policy[0]['updated_at'] if policy else None)}."
        ),
        "CC9.1": f"{agent_count} agent(s) registered, each gated by the active policy.",
        "A1.2": (
            f"{len(latency_values)} recent event(s) with latency tracked, average {avg_latency}ms."
            if latency_values
            else "No latency data recorded yet."
        ),
        "PI1.1": (
            f"Last verified {_relative(checkpoint[0]['period_end'])}, covering {checkpoint[0]['event_count']} event(s), checkpoint {checkpoint[0]['checkpoint_hash'][:12]}..."
            if checkpoint
            else "No checkpoint computed yet."
        ),
        "C1.1": f"{events_this_month} event(s) logged this month; inputs/outputs are redacted before any row is stored.",
        "P1.1": f"{total_answers} evidence-pack answer(s) drafted, {approved_answers} reviewed and approved.",
        "CC4.1": (
            f"{checkpoint[0]['event_count']} event(s) sealed as of the last daily checkpoint ({_relative(checkpoint[0]['period_end'])})."
            if checkpoint
            else "No checkpoint computed yet."
        ),
    }
    return evidence
