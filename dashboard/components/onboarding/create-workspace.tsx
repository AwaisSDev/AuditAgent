"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { Workspace } from "@/lib/types";

export function CreateWorkspace() {
  const [name, setName] = useState("");
  const queryClient = useQueryClient();

  const create = useMutation({
    mutationFn: () => api.post<Workspace>("/v1/workspaces", { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });

  return (
    <div className="flex min-h-screen items-center justify-center bg-sidebar px-4">
      <div className="w-full max-w-[360px]">
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold tracking-tight">Create your workspace</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            This is where your agents, events, and API keys will live.
          </p>
        </div>
        <Card className="p-5 shadow-subtle">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create.mutate();
            }}
            className="space-y-3"
          >
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Workspace name</label>
              <Input placeholder="Acme Inc" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </div>
            {create.isError && (
              <p className="text-[13px] text-error">
                {create.error instanceof Error ? create.error.message : "Couldn't create your workspace. Please try again."}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create workspace"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
