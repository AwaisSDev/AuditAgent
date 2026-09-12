export interface Workspace {
  id: string;
  name: string;
  slug: string;
  plan: "free" | "starter" | "growth" | "enterprise";
  slack_channel_id: string | null;
  notify_email: string | null;
  created_at: string;
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface AuditEvent {
  id: string;
  workspace_id: string;
  agent_id: string | null;
  action_type: string;
  action_name: string;
  inputs_redacted: Record<string, unknown>;
  output_redacted: unknown;
  model: string | null;
  prompt_hash: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  status: "completed" | "approved" | "rejected" | "denied_timeout" | "error";
  created_at: string;
  prev_hash: string;
  row_hash: string;
}

export interface Approval {
  id: string;
  workspace_id: string;
  event_id: string | null;
  agent_id: string | null;
  requested_action: {
    agent_name: string;
    action_type: string;
    action_name: string;
    inputs_preview: Record<string, unknown>;
  };
  status: "pending" | "approved" | "rejected" | "denied_timeout";
  decision_by: string | null;
  decision_note: string | null;
  requested_at: string;
  decided_at: string | null;
  expires_at: string;
}

export interface Policy {
  id: string;
  workspace_id: string;
  name: string;
  rules_yaml: string;
  is_active: boolean;
  updated_at: string;
}

export interface Questionnaire {
  id: string;
  workspace_id: string;
  filename: string;
  file_type: "pdf" | "csv" | "xlsx";
  status: "processing" | "ready" | "error";
  error_message: string | null;
  created_at: string;
}

export interface Answer {
  id: string;
  questionnaire_id: string;
  question_text: string;
  draft_answer: string | null;
  final_answer: string | null;
  status: "draft" | "reviewed" | "approved";
  evidence_event_ids: string[];
}

export interface Soc2Control {
  control_id: string;
  title: string;
  description: string;
  evidence_type: string;
  evidence_note: string;
}
