import yaml from "js-yaml";

// The plain-English categories a non-technical user can toggle. Order matters:
// more specific rules must come before more general ones that would otherwise
// shadow them (the policy engine uses "first match wins"), so "deleting data"
// is listed before the general "accessing data" rule.
export const RULE_DEFS = [
  {
    key: "delete_data",
    label: "Deleting stored data",
    description: "e.g. deleting a customer record or a row in a database",
    match: { action_type: "data_access", action_name: "delete_*" },
  },
  {
    key: "data_access",
    label: "Reading or accessing stored data",
    description: "e.g. looking up customer records",
    match: { action_type: "data_access" },
  },
  {
    key: "external",
    label: "Sending things outside your system",
    description: "e.g. emailing a customer, posting to Slack, calling an outside service",
    match: { action_type: "external" },
  },
  {
    key: "internal",
    label: "Internal, background actions",
    description: "e.g. summarizing text, classifying a ticket. Nothing leaves your system",
    match: { action_type: "internal" },
  },
] as const;

export type RuleKey = (typeof RULE_DEFS)[number]["key"];
export type ToggleState = Record<RuleKey, boolean>;

export const DEFAULT_TOGGLES: ToggleState = {
  delete_data: true,
  data_access: false,
  external: true,
  internal: false,
};

export function togglesToYaml(state: ToggleState): string {
  const rules = RULE_DEFS.map((def) => ({
    match: def.match,
    require_approval: state[def.key],
  }));
  return yaml.dump({ rules });
}

function matchEquals(a: Record<string, string>, b: Record<string, string>): boolean {
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  return aKeys.length === bKeys.length && aKeys.every((k) => a[k] === b[k]);
}

/** Best-effort: reads the 4 known rule shapes out of arbitrary policy YAML.
 * Returns null if the YAML doesn't parse, so the caller can fall back to
 * showing the raw editor instead of silently guessing wrong. */
export function yamlToToggles(text: string): ToggleState | null {
  if (text.trim() === "") return null; // no policy loaded yet — never treat this as "everything off"
  try {
    const parsed = yaml.load(text) as { rules?: { match?: Record<string, string>; require_approval?: boolean }[] };
    const rules = parsed?.rules ?? [];
    const state = { ...DEFAULT_TOGGLES };
    for (const def of RULE_DEFS) {
      const found = rules.find((r) => r.match && matchEquals(r.match, def.match));
      state[def.key] = found ? Boolean(found.require_approval) : false;
    }
    return state;
  } catch {
    return null;
  }
}

/** True if the YAML is exactly representable by the 4 toggles (no extra
 * custom rules) — used to decide whether simple mode is safe to show as the
 * accurate picture, vs. nudging the user toward the advanced editor. */
export function isSimpleYaml(text: string): boolean {
  try {
    const parsed = yaml.load(text) as { rules?: unknown[] };
    return (parsed?.rules?.length ?? 0) <= RULE_DEFS.length;
  } catch {
    return false;
  }
}
