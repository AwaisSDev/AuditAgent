"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

interface ConsentInfo {
  client_name: string;
  client_uri: string | null;
  scopes: string[];
  workspaces: { id: string; name: string }[];
}

function ConsentCard() {
  const requestId = useSearchParams().get("request_id") ?? "";
  const [workspaceId, setWorkspaceId] = useState("");
  const [submitting, setSubmitting] = useState<"approve" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, error: loadError } = useQuery({
    queryKey: ["oauth-consent", requestId],
    queryFn: () => api.get<ConsentInfo>(`/v1/oauth/consent?request_id=${encodeURIComponent(requestId)}`),
    enabled: !!requestId,
    retry: false,
  });

  const workspaces = data?.workspaces ?? [];
  const selected = workspaceId || workspaces[0]?.id || "";

  async function approve() {
    setSubmitting("approve");
    setError(null);
    try {
      const res = await api.post<{ redirect_url: string }>("/v1/oauth/consent", {
        request_id: requestId,
        workspace_id: selected,
      });
      window.location.href = res.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setSubmitting(null);
    }
  }

  async function deny() {
    setSubmitting("deny");
    setError(null);
    try {
      const res = await api.post<{ redirect_url: string }>("/v1/oauth/deny", { request_id: requestId });
      window.location.href = res.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setSubmitting(null);
    }
  }

  if (!requestId) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-6">
        <CardContent className="space-y-2 p-0 text-center">
          <p className="text-[15px] font-medium">Nothing to approve here.</p>
          <p className="text-sm text-muted-foreground">
            This page is reached by clicking "Connect" in an app that supports Tracyn's MCP server, not by
            visiting it directly.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-6">
        <CardContent className="space-y-3 p-0">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-9 w-full rounded-md" />
          <Skeleton className="h-9 w-full rounded-md" />
        </CardContent>
      </Card>
    );
  }

  if (loadError || !data) {
    return (
      <Card className="mx-auto mt-16 max-w-md p-6">
        <CardContent className="space-y-2 p-0 text-center">
          <p className="text-[15px] font-medium">This connection request has expired or was already used.</p>
          <p className="text-sm text-muted-foreground">Go back to the app you were connecting and try "Connect" again.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="mx-auto mt-16 max-w-md p-6 shadow-subtle">
      <CardContent className="space-y-4 p-0">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{data.client_name} wants to connect</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            It'll be able to read your agent activity, approvals, and compliance summary. It can't change your
            policy, decide approvals, or access billing.
          </p>
        </div>

        {workspaces.length === 0 ? (
          <p className="text-sm text-error">You don't belong to any workspace yet. Create one in the dashboard first.</p>
        ) : (
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">Workspace</label>
            <Select value={selected} onChange={(e) => setWorkspaceId(e.target.value)}>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </Select>
          </div>
        )}

        {error && <p className="text-[13px] text-error">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={!!submitting} onClick={deny}>
            {submitting === "deny" ? "Denying..." : "Deny"}
          </Button>
          <Button disabled={!!submitting || workspaces.length === 0} onClick={approve}>
            {submitting === "approve" ? "Connecting..." : "Approve"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function OAuthAuthorizePage() {
  return (
    <Suspense fallback={null}>
      <ConsentCard />
    </Suspense>
  );
}
