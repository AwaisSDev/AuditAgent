"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Workspace } from "@/lib/types";

interface WorkspaceContextValue {
  workspaces: Workspace[];
  workspace: Workspace | null;
  isLoading: boolean;
  setWorkspaceId: (id: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);

  const { data: workspaces = [], isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.get<Workspace[]>("/v1/workspaces"),
  });

  useEffect(() => {
    if (workspaceId) return;
    const stored = typeof window !== "undefined" ? localStorage.getItem("tracyn_workspace_id") : null;
    const initial = stored && workspaces.some((w) => w.id === stored) ? stored : workspaces[0]?.id;
    if (initial) setWorkspaceIdState(initial);
  }, [workspaces, workspaceId]);

  function setWorkspaceId(id: string) {
    setWorkspaceIdState(id);
    localStorage.setItem("tracyn_workspace_id", id);
  }

  const workspace = workspaces.find((w) => w.id === workspaceId) ?? null;

  return (
    <WorkspaceContext.Provider value={{ workspaces, workspace, isLoading, setWorkspaceId }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
