"""Raw audit-log export (distinct from the SOC2 mapping export and the
evidence-pack export) — lets a workspace pull its own hash-chained event
log out for backup, an auditor handoff, or feeding into another analytics
tool. Every row includes prev_hash/row_hash so the export itself carries
the chain-integrity proof, not just the dashboard's live view of it."""

import csv
import io
import json

COLUMNS = [
    "id",
    "created_at",
    "agent_id",
    "action_type",
    "action_name",
    "status",
    "model",
    "cost_usd",
    "latency_ms",
    "inputs_redacted",
    "output_redacted",
    "prompt_hash",
    "prev_hash",
    "row_hash",
]


def build_events_csv(events: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(COLUMNS)
    for e in events:
        writer.writerow(
            [
                e.get("id"),
                e.get("created_at"),
                e.get("agent_id") or "",
                e.get("action_type"),
                e.get("action_name"),
                e.get("status"),
                e.get("model") or "",
                e.get("cost_usd") if e.get("cost_usd") is not None else "",
                e.get("latency_ms") if e.get("latency_ms") is not None else "",
                json.dumps(e.get("inputs_redacted") or {}, default=str),
                json.dumps(e.get("output_redacted"), default=str) if e.get("output_redacted") is not None else "",
                e.get("prompt_hash") or "",
                e.get("prev_hash"),
                e.get("row_hash"),
            ]
        )
    return buf.getvalue().encode("utf-8")
