"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";
import type { ApiKey } from "@/lib/types";

const PLANS = [
  { id: "starter", name: "Starter", price: "$49/mo", blurb: "5 agents, 50k events, 5 questionnaires/mo" },
  { id: "growth", name: "Growth", price: "$199/mo", blurb: "Unlimited questionnaires, Slack approvals, SOC2 export" },
  { id: "enterprise", name: "Enterprise", price: "$999/mo", blurb: "Custom retention, SSO, DPA" },
] as const;

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <WorkspaceSettingsCard />
      <ApiKeysCard />
      <BillingCard />
    </div>
  );
}

function WorkspaceSettingsCard() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [slackChannel, setSlackChannel] = useState("");
  const [notifyEmail, setNotifyEmail] = useState("");

  useEffect(() => {
    setSlackChannel(workspace?.slack_channel_id ?? "");
    setNotifyEmail(workspace?.notify_email ?? "");
  }, [workspace]);

  const save = useMutation({
    mutationFn: () =>
      api.patch(`/v1/workspaces/${workspace!.id}`, { slack_channel_id: slackChannel || null, notify_email: notifyEmail || null }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Approval routing</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Set a Slack channel ID once you've installed the AuditAgent Slack app and invited the bot to a channel.
          Otherwise, approval requests fall back to email.
        </p>
        <div>
          <label className="mb-1 block text-xs font-medium">Slack channel ID</label>
          <Input placeholder="C0123456789" value={slackChannel} onChange={(e) => setSlackChannel(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">Fallback email</label>
          <Input placeholder="you@company.com" value={notifyEmail} onChange={(e) => setNotifyEmail(e.target.value)} />
        </div>
        <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
          Save
        </Button>
      </CardContent>
    </Card>
  );
}

function ApiKeysCard() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  const { data: keys = [] } = useQuery({
    queryKey: ["api-keys", workspace?.id],
    queryFn: () => api.get<ApiKey[]>(`/v1/workspaces/${workspace!.id}/api-keys`),
    enabled: !!workspace,
  });

  const create = useMutation({
    mutationFn: () => api.post<{ full_key: string }>(`/v1/workspaces/${workspace!.id}/api-keys`, { name }),
    onSuccess: (res) => {
      setNewKey(res.full_key);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["api-keys", workspace?.id] });
    },
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api.delete(`/v1/workspaces/${workspace!.id}/api-keys/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-keys", workspace?.id] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>API keys</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input placeholder="Key name (e.g. production)" value={name} onChange={(e) => setName(e.target.value)} />
          <Button size="sm" onClick={() => create.mutate()} disabled={!name || create.isPending}>
            Create key
          </Button>
        </div>

        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Prefix</TH>
              <TH>Created</TH>
              <TH>Last used</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {keys.map((k) => (
              <TR key={k.id}>
                <TD>{k.name}</TD>
                <TD className="font-mono text-xs">{k.key_prefix}...</TD>
                <TD className="text-xs text-muted-foreground">{formatDate(k.created_at)}</TD>
                <TD className="text-xs text-muted-foreground">{k.last_used_at ? formatDate(k.last_used_at) : "never"}</TD>
                <TD>
                  {k.revoked_at ? (
                    <Badge variant="secondary">revoked</Badge>
                  ) : (
                    <Button size="sm" variant="ghost" onClick={() => revoke.mutate(k.id)}>
                      Revoke
                    </Button>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>

      <Dialog open={!!newKey} onClose={() => setNewKey(null)} title="Your new API key">
        <p className="mb-3 text-sm text-muted-foreground">
          Copy this now. It won't be shown again. Set it as <code>AUDITAGENT_API_KEY</code>.
        </p>
        <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">{newKey}</pre>
        <div className="mt-4 flex justify-end">
          <Button onClick={() => setNewKey(null)}>Done</Button>
        </div>
      </Dialog>
    </Card>
  );
}

function BillingCard() {
  const { workspace } = useWorkspace();

  const checkout = useMutation({
    mutationFn: (plan: string) =>
      api.post<{ checkout_url: string }>(`/v1/workspaces/${workspace!.id}/billing/checkout`, { plan }),
    onSuccess: (res) => {
      window.location.href = res.checkout_url;
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Plan &amp; billing</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm">
          Current plan: <Badge variant="outline">{workspace?.plan ?? "free"}</Badge>
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.id} className="rounded-md border border-border p-3">
              <div className="font-medium">{p.name}</div>
              <div className="text-sm text-muted-foreground">{p.price}</div>
              <p className="mt-1 text-xs text-muted-foreground">{p.blurb}</p>
              <Button
                size="sm"
                className="mt-3 w-full"
                variant={workspace?.plan === p.id ? "outline" : "default"}
                disabled={workspace?.plan === p.id || checkout.isPending}
                onClick={() => checkout.mutate(p.id)}
              >
                {workspace?.plan === p.id ? "Current plan" : "Upgrade"}
              </Button>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
