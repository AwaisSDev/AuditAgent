"use client";

import { useRef } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import type { Questionnaire } from "@/lib/types";

export default function QuestionnairesPage() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);

  const { data: questionnaires = [], isLoading } = useQuery({
    queryKey: ["questionnaires", workspace?.id],
    queryFn: () => api.get<Questionnaire[]>(`/v1/workspaces/${workspace!.id}/questionnaires`),
    enabled: !!workspace,
    refetchInterval: 5_000,
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.postForm(`/v1/workspaces/${workspace!.id}/questionnaires`, form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["questionnaires", workspace?.id] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Evidence packs</h1>
          <p className="text-sm text-muted-foreground">
            Upload a security questionnaire (PDF/CSV/XLSX). Claude drafts answers from your logs, citing specific
            events. You review and edit before exporting.
          </p>
        </div>
        <div className="shrink-0">
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.csv,.xlsx,.xls"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
          <Button onClick={() => fileInput.current?.click()} disabled={upload.isPending || !workspace}>
            {upload.isPending ? "Uploading..." : "Upload questionnaire"}
          </Button>
        </div>
      </div>

      {upload.isError && (
        <p className="text-[13px] text-error">
          {upload.error instanceof Error ? upload.error.message : "Upload failed. Please try again."}
        </p>
      )}

      <Card>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <Table className="text-[17px]">
            <THead>
              <TR>
                <TH className="h-12 text-base">File</TH>
                <TH className="h-12 text-base">Status</TH>
                <TH className="h-12 text-base">Uploaded</TH>
                <TH className="h-12" />
              </TR>
            </THead>
            <TBody>
              {questionnaires.map((q) => (
                <TR key={q.id}>
                  <TD className="py-5">{q.filename}</TD>
                  <TD className="py-5">
                    <StatusBadge status={q.status === "ready" ? "completed" : q.status === "error" ? "error" : "pending"} />
                  </TD>
                  <TD className="py-5 text-sm text-muted-foreground">{formatDate(q.created_at)}</TD>
                  <TD className="py-5">
                    {q.status === "ready" && (
                      <Link href={`/questionnaires/${q.id}`} className="text-base font-medium text-primary underline">
                        Review answers
                      </Link>
                    )}
                    {q.status === "error" && <span className="text-sm text-error">{q.error_message}</span>}
                  </TD>
                </TR>
              ))}
              {questionnaires.length === 0 && (
                <TR>
                  <TD colSpan={4} className="py-8 text-center text-muted-foreground">
                    No questionnaires uploaded yet.
                  </TD>
                </TR>
              )}
            </TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
