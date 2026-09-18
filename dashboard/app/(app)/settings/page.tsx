"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PartyPopper } from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { ThemeToggle } from "@/components/settings/theme-toggle";
import { cn, formatDate } from "@/lib/utils";
import type { ApiKey } from "@/lib/types";

const PLANS = [
  { id: "starter", name: "Starter", price: "$49/mo", blurb: "10 agents, 50k events/mo, 10 evidence pack drafts/mo" },
  { id: "pro", name: "Pro", price: "$99/mo", blurb: "50 agents, 250k events/mo, unlimited evidence pack drafts" },
  { id: "enterprise", name: "Enterprise", price: "Contact us", blurb: "Unlimited agents, pay as you go events, custom contracts" },
] as const;

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <BillingCard />
      <AppearanceCard />
      <WorkspaceSettingsCard />
      <ApiKeysCard />
      <Suspense fallback={null}>
        <PaymentSuccessDialog />
      </Suspense>
    </div>
  );
}

const PLAN_NAMES: Record<string, string> = { starter: "Starter", pro: "Pro", enterprise: "Enterprise" };

function PaymentSuccessDialog() {
  const { workspace } = useWorkspace();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [open, setOpen] = useState(false);
  const [purchasedPlan, setPurchasedPlan] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get("billing") !== "success") return;
    setPurchasedPlan(searchParams.get("plan"));
    setOpen(true);
    // Strip the query string so a refresh doesn't re-trigger this, without
    // losing the values already captured into state above.
    router.replace("/settings");
  }, [searchParams, router]);

  // The webhook that actually flips workspace.plan can lag a few seconds
  // behind Whop's redirect back here -- poll briefly while the dialog is
  // open so "activating" can turn into a confirmed checkmark instead of
  // just claiming success before the backend has caught up.
  const confirmed = !!purchasedPlan && workspace?.plan === purchasedPlan;
  const { data: polledWorkspace } = useQuery({
    queryKey: ["workspaces", "billing-poll"],
    queryFn: () => api.get<{ plan: string }[]>("/v1/workspaces"),
    enabled: open && !confirmed,
    refetchInterval: 2000,
  });
  const activated = confirmed || polledWorkspace?.some((w) => w.plan === purchasedPlan);

  if (!open) return null;

  return (
    <Dialog open={open} onClose={() => setOpen(false)} title="">
      <div className="flex flex-col items-center py-4 text-center">
        <div
          className="flex h-14 w-14 items-center justify-center rounded-full bg-[#DBEDDB] text-[#2F5D3A] dark:bg-[#1F3D2B] dark:text-[#8FCBA3]"
          style={{ animation: "pop-in 0.5s cubic-bezier(0.34, 1.56, 0.64, 1)" }}
        >
          <PartyPopper className="h-7 w-7" strokeWidth={1.75} />
        </div>
        <h2 className="mt-4 text-lg font-semibold tracking-tight">Payment successful</h2>
        <p className={cn("mt-1 text-sm text-muted-foreground", !activated && "animate-pulse")}>
          {activated
            ? `You're on the ${PLAN_NAMES[purchasedPlan ?? ""] ?? purchasedPlan} plan now.`
            : `Activating your ${PLAN_NAMES[purchasedPlan ?? ""] ?? purchasedPlan} plan...`}
        </p>
        <Button size="sm" className="mt-5 w-full" onClick={() => setOpen(false)}>
          Done
        </Button>
      </div>
    </Dialog>
  );
}

function AppearanceCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-muted-foreground">Matches your device by default. Override it here.</p>
        <ThemeToggle />
      </CardContent>
    </Card>
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
          <Input
            placeholder="C0123456789"
            value={slackChannel}
            onChange={(e) => setSlackChannel(e.target.value)}
            autoComplete="off"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">Fallback email</label>
          <Input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={notifyEmail}
            onChange={(e) => setNotifyEmail(e.target.value)}
          />
        </div>
        <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
          Save
        </Button>
        {save.isError && (
          <p className="text-[13px] text-error">
            {save.error instanceof Error ? save.error.message : "Couldn't save. Please try again."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ApiKeysCard() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [canReview, setCanReview] = useState(false);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  const { data: keys = [] } = useQuery({
    queryKey: ["api-keys", workspace?.id],
    queryFn: () => api.get<ApiKey[]>(`/v1/workspaces/${workspace!.id}/api-keys`),
    enabled: !!workspace,
  });

  const create = useMutation({
    mutationFn: () =>
      api.post<{ full_key: string }>(`/v1/workspaces/${workspace!.id}/api-keys`, { name, can_review: canReview }),
    onSuccess: (res) => {
      setNewKey(res.full_key);
      setName("");
      setCanReview(false);
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
          <Input
            placeholder="Key name (e.g. production)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-0 flex-1"
          />
          <Button size="sm" className="shrink-0" onClick={() => create.mutate()} disabled={!name || create.isPending}>
            Create key
          </Button>
        </div>

        <div className="flex items-start justify-between gap-3 rounded-md border border-border p-3">
          <div className="min-w-0">
            <p className="text-sm font-medium">Allow this key to approve or reject actions</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Every key can log and track an agent's actions. Turn this on only if you'll also use this same key from
              Claude, ChatGPT, or another MCP client to decide pending requests. Leave it off for a key an agent uses
              on its own, so it can never decide its own pending request.
            </p>
          </div>
          <Switch checked={canReview} onCheckedChange={setCanReview} />
        </div>
        {(create.isError || revoke.isError) && (
          <p className="text-[13px] text-error">
            {(create.error ?? revoke.error) instanceof Error
              ? ((create.error ?? revoke.error) as Error).message
              : "Something went wrong. Please try again."}
          </p>
        )}

        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Prefix</TH>
              <TH>Type</TH>
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
                <TD>{k.can_review ? <Badge variant="warning">reviewer</Badge> : <Badge variant="secondary">agent</Badge>}</TD>
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

      <Dialog
        open={!!newKey}
        onClose={() => {
          setNewKey(null);
          setCopyState("idle");
        }}
        title="Your new API key"
      >
        <p className="mb-3 text-sm text-muted-foreground">
          Copy this now. It won't be shown again. Set it as <code>AUDITAGENT_API_KEY</code>.
        </p>
        <pre className="overflow-auto whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">{newKey}</pre>
        {copyState === "failed" && (
          <p className="mt-1 text-[13px] text-error">Couldn't copy automatically. Select the text above and copy it manually.</p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            variant="outline"
            onClick={async () => {
              if (!newKey) return;
              try {
                await navigator.clipboard.writeText(newKey);
                setCopyState("copied");
              } catch {
                // Clipboard access can be denied (insecure context, browser
                // permission, some in-app browsers) — fail visibly instead
                // of leaving the button looking like it silently did nothing.
                setCopyState("failed");
              }
            }}
          >
            {copyState === "copied" ? "Copied!" : "Copy"}
          </Button>
          <Button
            onClick={() => {
              setNewKey(null);
              setCopyState("idle");
            }}
          >
            Done
          </Button>
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
        {checkout.isError && (
          <p className="text-[13px] text-error">
            {checkout.error instanceof Error ? checkout.error.message : "Couldn't start checkout. Please try again."}
          </p>
        )}
        <div className="grid gap-3 sm:grid-cols-3">
          {PLANS.map((p) => (
            <div key={p.id} className="rounded-md border border-border p-3">
              <div className="font-medium">{p.name}</div>
              <div className="text-sm text-muted-foreground">{p.price}</div>
              <p className="mt-1 text-xs text-muted-foreground">{p.blurb}</p>
              {p.id === "enterprise" ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-3 w-full"
                  onClick={() => window.open("https://cal.com/awais-siddique/30min", "_blank", "noopener,noreferrer")}
                >
                  Book a call
                </Button>
              ) : (
                <Button
                  size="sm"
                  className="mt-3 w-full"
                  variant={workspace?.plan === p.id ? "outline" : "default"}
                  disabled={workspace?.plan === p.id || checkout.isPending}
                  onClick={() => checkout.mutate(p.id)}
                >
                  {workspace?.plan === p.id ? "Current plan" : checkout.isPending ? "Loading..." : "Upgrade"}
                </Button>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
