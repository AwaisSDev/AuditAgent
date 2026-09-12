"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace-context";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { Workspace } from "@/lib/types";

function Avatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded bg-primary font-semibold text-primary-foreground",
        className
      )}
    >
      {name[0]?.toUpperCase() ?? "?"}
    </span>
  );
}

export function WorkspaceSwitcher() {
  const { workspaces, workspace, setWorkspaceId } = useWorkspace();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const create = useMutation({
    mutationFn: () => api.post<Workspace>("/v1/workspaces", { name: newName }),
    onSuccess: async (ws) => {
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setWorkspaceId(ws.id);
      setNewName("");
      setCreating(false);
      setOpen(false);
    },
  });

  if (!workspace) return null;

  return (
    <div ref={containerRef} className="relative px-3 pb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 rounded-md border border-border bg-card px-2.5 py-2 text-left transition-colors hover:bg-muted"
      >
        <Avatar name={workspace.name} className="h-6 w-6 text-xs" />
        <span className="flex-1 truncate text-sm font-medium text-foreground">{workspace.name}</span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute left-3 right-3 top-[calc(100%-4px)] z-50 rounded-lg border border-border bg-card p-1 shadow-popover">
            <p className="px-2 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Organizations
            </p>
            {workspaces.map((w) => (
              <button
                key={w.id}
                onClick={() => {
                  setWorkspaceId(w.id);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-muted"
              >
                <Avatar name={w.name} className="h-6 w-6 text-xs" />
                <span className="flex-1 truncate text-sm font-medium text-foreground">{w.name}</span>
                {w.id === workspace.id && <Check className="h-4 w-4 shrink-0 text-foreground" />}
              </button>
            ))}
            <div className="my-1 border-t border-border" />
            <button
              onClick={() => {
                setCreating(true);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-dashed border-border">
                <Plus className="h-3.5 w-3.5" />
              </span>
              Add organization
            </button>
          </div>
        </>
      )}

      <Dialog open={creating} onClose={() => setCreating(false)} title="Add organization">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (newName.trim()) create.mutate();
          }}
          className="space-y-3"
        >
          <Input placeholder="Organization name" value={newName} onChange={(e) => setNewName(e.target.value)} autoFocus />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setCreating(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!newName.trim() || create.isPending}>
              {create.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
