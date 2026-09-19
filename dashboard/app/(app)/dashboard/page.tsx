"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, downloadFile } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
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
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Timeline</h1>
        <Button
          variant="outline"
          size="sm"
          disabled={!workspace}
          onClick={() => downloadFile(`/v1/workspaces/${workspace!.id}/events/export.csv?${params.toString()}`, "tracyn-events.csv")}
        >
          Export CSV
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={agentId} onChange={(e) => setAgentId(e.target.value)} className="w-[calc(50%-4px)] sm:w-40">
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
          className="w-full sm:w-52"
        />
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-[calc(50%-4px)] sm:w-40">
          <option value="">All statuses</option>
          <option value="completed">Completed</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="denied_timeout">Denied (timeout)</option>
          <option value="error">Error</option>
        </Select>
      </div>

      <Card>
        <Table className="text-[17px]">
          <THead>
            <TR>
              <TH className="h-12 text-base">When</TH>
              <TH className="h-12 text-base">Agent action</TH>
              <TH className="hidden h-12 text-base sm:table-cell">Type</TH>
              <TH className="h-12 text-base">Status</TH>
              <TH className="hidden h-12 text-base md:table-cell">Latency</TH>
              <TH className="hidden h-12 text-base md:table-cell">Cost</TH>
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
                  <TD className="hidden sm:table-cell">
                    <Skeleton className="h-4 w-20" />
                  </TD>
                  <TD>
                    <Skeleton className="h-5 w-20 rounded-full" />
                  </TD>
                  <TD className="hidden md:table-cell">
                    <Skeleton className="h-4 w-12" />
                  </TD>
                  <TD className="hidden md:table-cell">
                    <Skeleton className="h-4 w-14" />
                  </TD>
                </TR>
              ))}
            {!isLoading && (
              <>
                {events?.map((e) => (
                  <TR key={e.id} className="cursor-pointer" onClick={() => setSelected(e)}>
                    <TD className="whitespace-nowrap py-5 text-muted-foreground">{formatDate(e.created_at)}</TD>
                    <TD
                      className="max-w-[84px] overflow-hidden text-ellipsis whitespace-nowrap py-5 font-medium sm:max-w-none sm:overflow-visible sm:whitespace-normal"
                      title={e.action_name}
                    >
                      {e.action_name}
                    </TD>
                    <TD className="hidden py-5 text-muted-foreground sm:table-cell">{e.action_type}</TD>
                    <TD className="py-5">
                      <StatusBadge status={e.status} />
                    </TD>
                    <TD className="hidden py-5 tabular-nums text-muted-foreground md:table-cell">
                      {e.latency_ms != null ? `${e.latency_ms}ms` : "-"}
                    </TD>
                    <TD className="hidden py-5 tabular-nums text-muted-foreground md:table-cell">
                      {e.cost_usd != null ? `$${e.cost_usd.toFixed(4)}` : "-"}
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
