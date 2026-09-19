"use client";

import { useQuery } from "@tanstack/react-query";
import { api, downloadFile } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Soc2Control } from "@/lib/types";

export default function Soc2Page() {
  const { workspace } = useWorkspace();
  const { data: controls = [], isLoading } = useQuery({
    queryKey: ["soc2-controls"],
    queryFn: () => api.get<Soc2Control[]>("/v1/soc2/controls"),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">SOC 2 control mapping</h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            Which of your Tracyn evidence already speaks to common SOC 2 controls. Not audit certification, just
            a head start for your auditor conversation.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => downloadFile(`/v1/workspaces/${workspace!.id}/soc2/export.csv`, "tracyn-soc2-mapping.csv")}
          disabled={!workspace}
        >
          Export CSV
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {controls.map((c) => (
            <div key={c.control_id} className="flex flex-col gap-3 p-4 sm:flex-row sm:gap-6">
              <div className="flex shrink-0 items-start gap-3 sm:w-64">
                <span className="mt-0.5 rounded bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground">
                  {c.control_id}
                </span>
                <div>
                  <p className="text-sm font-medium leading-snug">{c.title}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{c.description}</p>
                </div>
              </div>
              <div className="rounded-md bg-muted/60 px-3 py-2 sm:flex-1">
                <p className="text-[13px] font-medium text-foreground">{c.evidence_type}</p>
                <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{c.evidence_note}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
