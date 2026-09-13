"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadFile } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Answer } from "@/lib/types";

export default function QuestionnaireDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { workspace } = useWorkspace();

  const { data: answers = [], isLoading } = useQuery({
    queryKey: ["answers", id],
    queryFn: () => api.get<Answer[]>(`/v1/workspaces/${workspace!.id}/questionnaires/${id}/answers`),
    enabled: !!workspace,
  });

  return (
    <div className="max-w-3xl space-y-5">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Review answers</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => downloadFile(`/v1/workspaces/${workspace!.id}/questionnaires/${id}/export.csv`, "evidence-pack.csv")}
          >
            Export CSV
          </Button>
          <Button
            onClick={() => downloadFile(`/v1/workspaces/${workspace!.id}/questionnaires/${id}/export.docx`, "evidence-pack.docx")}
          >
            Export DOCX
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-lg" />
          ))}
        </div>
      )}

      <div className="space-y-3">
        {answers.map((a) => (
          <AnswerCard key={a.id} answer={a} questionnaireId={id} workspaceId={workspace?.id} />
        ))}
      </div>
    </div>
  );
}

function AnswerCard({
  answer,
  questionnaireId,
  workspaceId,
}: {
  answer: Answer;
  questionnaireId: string;
  workspaceId?: string;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState(answer.final_answer ?? answer.draft_answer ?? "");

  const save = useMutation({
    mutationFn: (status: "reviewed" | "approved") =>
      api.patch(`/v1/workspaces/${workspaceId}/answers/${answer.id}`, { final_answer: text, status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["answers", questionnaireId] }),
  });

  return (
    <Card>
      <CardContent className="space-y-2 pt-4">
        <div className="flex items-start justify-between gap-3">
          <p className="min-w-0 flex-1 font-medium">{answer.question_text}</p>
          <StatusBadge status={answer.status === "draft" ? "pending" : "completed"} />
        </div>
        <Textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
        {answer.evidence_event_ids.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Evidence: {answer.evidence_event_ids.map((id) => id.slice(0, 8)).join(", ")}
          </p>
        )}
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => save.mutate("reviewed")} disabled={save.isPending}>
            Save as reviewed
          </Button>
          <Button size="sm" onClick={() => save.mutate("approved")} disabled={save.isPending}>
            Approve final wording
          </Button>
        </div>
        {save.isError && (
          <p className="text-[13px] text-error">
            {save.error instanceof Error ? save.error.message : "Couldn't save. Please try again."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
