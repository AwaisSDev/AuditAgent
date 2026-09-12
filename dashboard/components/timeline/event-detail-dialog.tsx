"use client";

import { Dialog } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import type { AuditEvent } from "@/lib/types";

export function EventDetailDialog({ event, onClose }: { event: AuditEvent | null; onClose: () => void }) {
  return (
    <Dialog open={!!event} onClose={onClose} title={event?.action_name ?? ""}>
      {event && (
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <StatusBadge status={event.status} />
            <span className="text-muted-foreground">{event.action_type}</span>
            <span className="text-muted-foreground">· {formatDate(event.created_at)}</span>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium text-muted-foreground">Inputs (redacted)</div>
            <pre className="max-h-40 overflow-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(event.inputs_redacted, null, 2)}
            </pre>
          </div>

          {event.output_redacted != null && (
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">Output (redacted)</div>
              <pre className="max-h-40 overflow-auto rounded-md bg-muted p-2 text-xs">
                {JSON.stringify(event.output_redacted, null, 2)}
              </pre>
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <div className="text-muted-foreground">Model</div>
              <div>{event.model ?? "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Latency</div>
              <div>{event.latency_ms != null ? `${event.latency_ms}ms` : "—"}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Cost</div>
              <div>{event.cost_usd != null ? `$${event.cost_usd.toFixed(4)}` : "—"}</div>
            </div>
          </div>

          <div className="rounded-md border border-border p-2">
            <div className="mb-1 text-xs font-medium text-muted-foreground">Hash chain (immutability proof)</div>
            <div className="break-all font-mono text-[10px] text-muted-foreground">prev: {event.prev_hash}</div>
            <div className="break-all font-mono text-[10px] text-muted-foreground">row: {event.row_hash}</div>
          </div>
        </div>
      )}
    </Dialog>
  );
}
