"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheck } from "lucide-react";
import { api, downloadFile } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Soc2ControlOut } from "@/lib/types";

export default function Soc2Page() {
  const { workspace } = useWorkspace();
  const { data: controls = [], isLoading } = useQuery({
    queryKey: ["soc2-controls", workspace?.id],
    queryFn: () => api.get<Soc2ControlOut[]>(`/v1/workspaces/${workspace!.id}/soc2/controls`),
    enabled: !!workspace,
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">SOC 2 control mapping</h1>
          <p className="max-w-2xl text-[15px] text-muted-foreground">
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
            <div key={c.control_id} className="flex flex-col gap-4 p-5 sm:flex-row sm:gap-8">
              <div className="flex shrink-0 items-start gap-3 sm:w-72">
                <span className="mt-0.5 rounded bg-muted px-1.5 py-0.5 font-mono text-xs font-medium text-muted-foreground">
                  {c.control_id}
                </span>
                <div>
                  <p className="text-base font-medium leading-snug">{c.title}</p>
                  <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">{c.description}</p>
                </div>
              </div>
              <div className="rounded-md bg-muted/60 px-4 py-3 sm:flex-1">
                <p className="font-mono text-xs text-muted-foreground">{c.evidence_type}</p>
                <div className="mt-1 flex items-start gap-1.5">
                  <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#2F5D3A] dark:text-[#8FCBA3]" strokeWidth={2} />
                  <p className="text-sm leading-relaxed text-foreground">{c.live_evidence}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
