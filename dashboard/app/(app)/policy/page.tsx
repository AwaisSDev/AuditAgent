"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import yaml from "js-yaml";
import { FileCode, Check, Mail, Trash2, Database, Cog, ChevronRight, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { diffLines } from "@/lib/diff-lines";
import { useWorkspace } from "@/lib/workspace-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { RULE_DEFS, DEFAULT_TOGGLES, togglesToYaml, yamlToToggles, isSimpleYaml, type ToggleState } from "@/lib/policy-rules";
import type { Policy, PolicyDraft } from "@/lib/types";

const ICONS: Record<string, typeof Mail> = {
  delete_data: Trash2,
  data_access: Database,
  external: Mail,
  internal: Cog,
};

export default function PolicyPage() {
  const { workspace } = useWorkspace();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<PolicyDraft | null>(null);

  const { data: policy, isLoading } = useQuery({
    queryKey: ["policy", workspace?.id],
    queryFn: () => api.get<Policy>(`/v1/workspaces/${workspace!.id}/policy`),
    enabled: !!workspace,
  });

  useEffect(() => {
    if (policy) setDraft(policy.rules_yaml);
  }, [policy]);

  const save = useMutation({
    mutationFn: (rules_yaml: string) => api.put(`/v1/workspaces/${workspace!.id}/policy`, { name: "default", rules_yaml }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["policy", workspace?.id] });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (e: Error) => setError(e.message),
  });

  function handleSave(text: string) {
    setError(null);
    try {
      yaml.load(text); // sanity check before hitting the API
      save.mutate(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That doesn't look like valid YAML");
    }
  }

  const draftFromInstruction = useMutation({
    mutationFn: () => api.post<PolicyDraft>(`/v1/workspaces/${workspace!.id}/policy/draft`, { instruction }),
    onSuccess: (result) => setProposal(result),
    onError: (e: Error) => setProposal({ proposed_yaml: null, explanation: e.message }),
  });

  function applyProposal() {
    if (!proposal?.proposed_yaml) return;
    setDraft(proposal.proposed_yaml);
    handleSave(proposal.proposed_yaml);
    setProposal(null);
    setInstruction("");
    setAdvancedOpen(true); // the applied rule may not fit the 4 simple toggles -- show the real YAML
  }

  const toggles: ToggleState = yamlToToggles(draft) ?? DEFAULT_TOGGLES;
  const hasCustomRules = draft.trim() !== "" && !isSimpleYaml(draft);

  function setToggle(key: keyof ToggleState, value: boolean) {
    const next = togglesToYaml({ ...toggles, [key]: value });
    setDraft(next);
    handleSave(next);
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Policy</h1>
        <p className="text-sm text-muted-foreground">
          Choose which kinds of things your AI agent does need a person's okay before they happen. Everything else
          runs on its own.
        </p>
      </div>

      <div className="space-y-3 rounded-lg border border-border p-4">
        <div className="flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5" strokeWidth={1.75} />
          Describe a policy change in plain English
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            placeholder="e.g. Require approval before deleting a customer account"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && instruction.trim() && !draftFromInstruction.isPending) draftFromInstruction.mutate();
            }}
            className="flex-1"
          />
          <Button
            onClick={() => draftFromInstruction.mutate()}
            disabled={!instruction.trim() || draftFromInstruction.isPending || !policy}
          >
            {draftFromInstruction.isPending ? "Thinking..." : "Draft change"}
          </Button>
        </div>

        {proposal && !proposal.proposed_yaml && (
          <p className="rounded-md bg-muted px-3 py-2 text-[13px] text-muted-foreground">{proposal.explanation}</p>
        )}

        {proposal?.proposed_yaml && (
          <div className="space-y-2 rounded-md border border-border">
            <p className="border-b border-border bg-muted/60 px-3 py-2 text-[13px] text-muted-foreground">
              {proposal.explanation}
            </p>
            <pre className="overflow-x-auto px-3 py-2 font-mono text-[13px] leading-relaxed">
              {diffLines(draft, proposal.proposed_yaml).map((line, i) => (
                <div
                  key={i}
                  className={cn(
                    "px-1",
                    line.type === "add" && "bg-[#DBEDDB] text-[#2F5D3A] dark:bg-[#1F3D2B] dark:text-[#8FCBA3]",
                    line.type === "remove" && "bg-error/15 text-error line-through"
                  )}
                >
                  {line.type === "add" ? "+ " : line.type === "remove" ? "- " : "  "}
                  {line.text}
                </div>
              ))}
            </pre>
            <div className="flex justify-end gap-2 border-t border-border px-3 py-2">
              <Button variant="outline" size="sm" onClick={() => setProposal(null)}>
                Discard
              </Button>
              <Button size="sm" onClick={applyProposal}>
                Apply
              </Button>
            </div>
          </div>
        )}
      </div>

      {isLoading || !policy ? (
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {RULE_DEFS.map((def) => {
            const Icon = ICONS[def.key];
            return (
              <div key={def.key} className="flex items-center gap-3 p-4">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted">
                  <Icon className="h-4 w-4 text-muted-foreground" strokeWidth={1.75} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[15px] font-semibold text-foreground">{def.label}</p>
                  <p className="text-sm text-muted-foreground">{def.description}</p>
                </div>
                <span
                  className={cn(
                    "hidden text-sm sm:block",
                    toggles[def.key] ? "font-semibold text-foreground" : "font-medium text-muted-foreground"
                  )}
                >
                  {toggles[def.key] ? "Needs approval" : "Runs automatically"}
                </span>
                <Switch checked={toggles[def.key]} onCheckedChange={(v) => setToggle(def.key, v)} disabled={save.isPending} />
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-center gap-2 text-[13px] text-muted-foreground">
        {saved && (
          <span className="flex items-center gap-1">
            <Check className="h-3.5 w-3.5" /> Saved
          </span>
        )}
        {error && <span className="text-error">{error}</span>}
      </div>

      {hasCustomRules && (
        <p className="rounded-md bg-muted px-3 py-2 text-[13px] text-muted-foreground">
          Your policy also has custom rules beyond these four. Open "Advanced" below to see the full picture.
        </p>
      )}

      <div className="rounded-lg border border-border">
        <button
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="flex w-full items-center gap-1.5 px-4 py-3 text-left text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronRight className={`h-3.5 w-3.5 transition-transform ${advancedOpen ? "rotate-90" : ""}`} />
          Advanced: edit the underlying rules as code
        </button>
        {advancedOpen && (
          <div className="border-t border-border">
            <div className="flex items-center justify-between border-b border-border bg-muted/60 px-3 py-2">
              <div className="flex items-center gap-1.5 text-[13px] text-muted-foreground">
                <FileCode className="h-3.5 w-3.5" strokeWidth={1.75} />
                auditagent.policy.yaml
              </div>
              <Button size="sm" onClick={() => handleSave(draft)} disabled={save.isPending}>
                {save.isPending ? "Saving..." : "Save"}
              </Button>
            </div>
            <textarea
              rows={12}
              spellCheck={false}
              className="block w-full resize-none border-0 bg-card p-4 font-mono text-base leading-relaxed text-foreground outline-none sm:text-[13px]"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <p className="border-t border-border px-4 py-3 text-[13px] leading-relaxed text-muted-foreground">
              Rules are checked in order; the first match wins. A rule like{" "}
              <code className="rounded bg-muted px-1 py-0.5">action_name: &quot;delete_*&quot;</code> matches any
              action name starting with "delete_".
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
