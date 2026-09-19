"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/badge";
import { Dialog } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Tabs } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("pending");
  const [editing, setEditing] = useState<Approval | null>(null);
  const [editedInputs, setEditedInputs] = useState("");
  const [note, setNote] = useState("");

  const { data: approvals = [], isLoading } = useQuery({
    queryKey: ["approvals", workspace?.id, tab],
    queryFn: () => api.get<Approval[]>(`/v1/workspaces/${workspace!.id}/approvals?status=${tab}`),
    enabled: !!workspace,
    refetchInterval: 10_000,
  });

  const decide = useMutation({
    mutationFn: (vars: { id: string; decision: "approved" | "rejected"; decision_note?: string; edited_action?: Record<string, unknown> }) =>
      api.post(`/v1/workspaces/${workspace!.id}/approvals/${vars.id}/decide`, {
        // decision_by isn't sent — the backend always attributes the decision
        // to the authenticated user (Depends(require_workspace_member)),
        // never a client-supplied value.
        decision: vars.decision,
        decision_note: vars.decision_note,
        edited_action: vars.edited_action,
      }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["approvals", workspace?.id] }),
  });

  function openEdit(approval: Approval) {
    setEditing(approval);
    setEditedInputs(JSON.stringify(approval.requested_action.inputs_preview, null, 2));
    setNote("");
  }

  function submitEdit() {
    if (!editing) return;
    try {
      const parsed = JSON.parse(editedInputs);
      decide.mutate({
        id: editing.id,
        decision: "approved",
        decision_note: note || undefined,
        edited_action: { inputs_preview: parsed },
      });
      setEditing(null);
    } catch {
      alert("Inputs must be valid JSON");
    }
  }

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
      <Tabs
        tabs={[
          { value: "pending", label: "Pending" },
          { value: "approved", label: "Approved" },
          { value: "rejected", label: "Rejected" },
          { value: "denied_timeout", label: "Auto-denied" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] w-full rounded-lg" />
          ))}
        </div>
      )}

      {decide.isError && (
        <p className="text-[13px] text-error">
          {decide.error instanceof Error ? decide.error.message : "Couldn't record that decision. Please try again."}
        </p>
      )}

      {!isLoading && approvals.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">Nothing here.</CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {approvals.map((a) => (
          <Card key={a.id}>
            <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-base">
                  <span className="font-medium">{a.requested_action.agent_name}</span>
                  <span className="text-muted-foreground">wants to run</span>
                  <span className="font-medium">{a.requested_action.action_name}</span>
                  <StatusBadge status={a.status} />
                </div>
                <div className="text-sm text-muted-foreground">
                  {a.requested_action.action_type} · requested {formatDate(a.requested_at)}
                  {a.decided_at && ` · decided ${formatDate(a.decided_at)} by ${a.decision_by}`}
                </div>
                <pre className="mt-1 max-w-3xl overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-sm">
                  {JSON.stringify(a.requested_action.inputs_preview, null, 2)}
                </pre>
                {a.decision_note && <p className="text-sm italic text-muted-foreground">"{a.decision_note}"</p>}
              </div>

              {a.status === "pending" && (() => {
                // Scoped to this row, not every pending card at once — under
                // slow network the mutation can be in flight for seconds,
                // and without this a user unsure whether their click landed
                // could fire it again (harmless — the backend's
                // compare-and-swap guard rejects the second one — but
                // confusing: they'd see an "already decided" error for a
                // decision that was actually their own first click).
                const pendingHere = decide.isPending && decide.variables?.id === a.id;
                return (
                  <div className="flex shrink-0 gap-2">
                    <Button size="sm" disabled={pendingHere} onClick={() => decide.mutate({ id: a.id, decision: "approved" })}>
                      {pendingHere && decide.variables?.decision === "approved" ? "Approving..." : "Approve"}
                    </Button>
                    <Button size="sm" variant="outline" disabled={pendingHere} onClick={() => openEdit(a)}>
                      Edit...
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={pendingHere}
                      onClick={() => decide.mutate({ id: a.id, decision: "rejected" })}
                    >
                      {pendingHere && decide.variables?.decision === "rejected" ? "Rejecting..." : "Reject"}
                    </Button>
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!editing} onClose={() => setEditing(null)} title="Edit & approve">
        <div className="space-y-3">
          <Textarea
            rows={8}
            value={editedInputs}
            onChange={(e) => setEditedInputs(e.target.value)}
            className="font-mono text-base sm:text-xs"
          />
          <Textarea placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button onClick={submitEdit}>Approve with edits</Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
