"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { StatusBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EventDetailDialog } from "@/components/timeline/event-detail-dialog";
import { formatDate } from "@/lib/utils";
import type { Agent, AuditEvent } from "@/lib/types";

export default function TimelinePage() {
  const { workspace } = useWorkspace();
  const [agentId, setAgentId] = useState("");
  const [actionType, setActionType] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<AuditEvent | null>(null);

  const { data: agents = [] } = useQuery({
    queryKey: ["agents", workspace?.id],
    queryFn: () => api.get<Agent[]>(`/v1/workspaces/${workspace!.id}/agents`),
    enabled: !!workspace,
  });

  const params = new URLSearchParams();
  if (agentId) params.set("agent_id", agentId);
  if (actionType) params.set("action_type", actionType);
  if (status) params.set("status", status);

  const { data: events, isLoading } = useQuery({
    queryKey: ["events", workspace?.id, agentId, actionType, status],
    queryFn: () => api.get<AuditEvent[]>(`/v1/workspaces/${workspace!.id}/events?${params.toString()}`),
    enabled: !!workspace,
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Timeline</h1>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={agentId} onChange={(e) => setAgentId(e.target.value)} className="w-40">
          <option value="">All agents</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Filter by action type..."
          value={actionType}
          onChange={(e) => setActionType(e.target.value)}
          className="w-52"
        />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="denied_timeout">Denied (timeout)</option>
          <option value="error">Error</option>
        </Select>
      </div>

      <Card>
        <Table>
          <THead>
            <TR>
              <TH>When</TH>
              <TH>Agent action</TH>
              <TH>Type</TH>
              <TH>Status</TH>
              <TH>Latency</TH>
              <TH>Cost</TH>
            </TR>
          </THead>
          <TBody>
            {isLoading &&
              Array.from({ length: 8 }).map((_, i) => (
                <TR key={i}>
                  <TD>
                    <Skeleton className="h-4 w-24" />
                  </TD>
                  <TD>
                    <Skeleton className="h-4 w-36" />
                  </TD>
                  <TD>
                    <Skeleton className="h-4 w-20" />
                  </TD>
                  <TD>
                    <Skeleton className="h-5 w-20 rounded-full" />
                  </TD>
                  <TD>
                    <Skeleton className="h-4 w-12" />
                  </TD>
                  <TD>
                    <Skeleton className="h-4 w-14" />
                  </TD>
                </TR>
              ))}
            {!isLoading && (
              <>
                {events?.map((e) => (
                  <TR key={e.id} className="cursor-pointer" onClick={() => setSelected(e)}>
                    <TD className="whitespace-nowrap text-muted-foreground">{formatDate(e.created_at)}</TD>
                    <TD className="font-medium">{e.action_name}</TD>
                    <TD className="text-muted-foreground">{e.action_type}</TD>
                    <TD>
                      <StatusBadge status={e.status} />
                    </TD>
                    <TD className="tabular-nums text-muted-foreground">
                      {e.latency_ms != null ? `${e.latency_ms}ms` : "—"}
                    </TD>
                    <TD className="tabular-nums text-muted-foreground">
                      {e.cost_usd != null ? `$${e.cost_usd.toFixed(4)}` : "—"}
                    </TD>
                  </TR>
                ))}
                {events?.length === 0 && (
                  <TR>
                    <TD colSpan={6} className="py-10 text-center text-muted-foreground">
                      No events yet. Install the SDK and run your agent to see activity here.
                    </TD>
                  </TR>
                )}
              </>
            )}
          </TBody>
        </Table>
      </Card>

      <EventDetailDialog event={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
