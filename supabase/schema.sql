-- AuditAgent — Supabase schema
-- Run in the Supabase SQL editor (or via `supabase db push`) on a fresh project.
-- Requires: pgcrypto (for gen_random_uuid/digest) — enabled by default on Supabase.

create extension if not exists pgcrypto;

-- =========================================================================
-- CORE TABLES
-- =========================================================================

create table workspaces (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text not null unique,
  owner_id    uuid not null references auth.users(id) on delete restrict,
  plan        text not null default 'free' check (plan in ('free','starter','pro','enterprise')),
  slack_channel_id text,        -- set once the bot is invited to a channel (dashboard settings)
  notify_email     text,        -- fallback for approvals when no Slack channel is set
  created_at  timestamptz not null default now()
);

-- Bridge table so RLS can check "does auth.uid() belong to this workspace".
create table workspace_members (
  workspace_id uuid not null references workspaces(id) on delete cascade,
  user_id      uuid not null references auth.users(id) on delete cascade,
  role         text not null default 'member' check (role in ('owner','admin','member')),
  created_at   timestamptz not null default now(),
  primary key (workspace_id, user_id)
);

create table agents (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  name         text not null,
  description  text,
  is_active    bool not null default true,
  created_by   uuid references auth.users(id),
  created_at   timestamptz not null default now(),
  unique (workspace_id, name)
);

-- API keys used by the SDK to authenticate ingest requests.
-- Only a bcrypt/sha256 hash of the secret is ever stored — the raw key is
-- shown once at creation time, same pattern as Stripe/GitHub tokens.
create table api_keys (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  name         text not null,
  key_prefix   text not null,        -- e.g. "al_live_ab12" — shown in the UI for identification
  key_hash     text not null,        -- sha256(secret), never the raw secret
  -- Separate from ordinary agent-tracking privileges: an agent's own key
  -- must never be able to decide its own pending approval (see mcp_data.py's
  -- decide-via-MCP endpoint), so this defaults to false and is only set true
  -- for a key a human explicitly creates for that purpose.
  can_review   bool not null default false,
  created_by   uuid references auth.users(id),
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz
);
create unique index idx_api_keys_prefix on api_keys(key_prefix);

-- Policy Engine (F2): the YAML a dev commits to their repo is mirrored here
-- so the dashboard can show/edit it and the backend can evaluate it at
-- ingest time without round-tripping to the dev's repo.
create table policies (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  name         text not null default 'default',
  rules_yaml   text not null,
  is_active    bool not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Tracks the tip of each workspace's hash chain so the trigger below can
-- compute prev_hash without scanning the events table on every insert.
create table workspace_chain_heads (
  workspace_id uuid primary key references workspaces(id) on delete cascade,
  last_hash    text not null default repeat('0', 64)
);

-- =========================================================================
-- INTAKE STAGING — mutable, short-lived
-- =========================================================================
-- The ingest endpoint (F1) writes here and returns immediately (~ms). The
-- arq worker (F3 build step) drains this queue: redacts PII with Presidio,
-- classifies the action, evaluates the policy, and only THEN inserts the
-- final row into `events`. This split exists because `events` is append-only
-- (see triggers below) — redaction must happen before the row is born, not
-- via a later UPDATE, which the immutability trigger would reject anyway.

create table event_intake (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  api_key_id   uuid references api_keys(id) on delete set null,
  payload      jsonb not null,
  status       text not null default 'queued' check (status in ('queued','processing','done','error')),
  error_message text,
  created_at   timestamptz not null default now(),
  processed_at timestamptz
);
create index idx_event_intake_status on event_intake(status, created_at);

-- =========================================================================
-- EVENTS — append-only, hash-chained
-- =========================================================================

create table events (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  agent_id         uuid references agents(id) on delete set null,
  action_type      text not null,        -- e.g. 'internal' | 'external' | 'data_access' | ... (policy engine matches on this)
  action_name      text not null,
  inputs_redacted  jsonb not null default '{}'::jsonb,
  output_redacted  jsonb,
  model            text,
  prompt_hash      text,
  cost_usd         numeric(12,6),
  latency_ms       integer,
  -- Set once, at insert time, by the worker — reflects the FINAL outcome
  -- (the SDK already resolved any approval before ever calling ingest; see
  -- backend/app/worker/tasks.py for why events never need a later status
  -- change, which would violate append-only anyway).
  status           text not null default 'completed'
                   check (status in ('completed','approved','rejected','denied_timeout','error')),
  created_at       timestamptz not null default now(),
  -- immutability chain
  prev_hash        text not null,
  row_hash         text not null
);

create index idx_events_workspace_id on events(workspace_id);
create index idx_events_agent_id on events(agent_id);
create index idx_events_created_at on events(created_at);
create index idx_events_action_type on events(action_type);
create index idx_events_workspace_created on events(workspace_id, created_at desc);

-- Computes row_hash = sha256(row contents || prev_hash) and chains it to the
-- workspace's current head, under a row lock so concurrent inserts for the
-- same workspace can't compute the same prev_hash.
create or replace function events_chain_hash() returns trigger as $$
declare
  prev text;
begin
  insert into workspace_chain_heads (workspace_id) values (new.workspace_id)
    on conflict (workspace_id) do nothing;

  select last_hash into prev from workspace_chain_heads
    where workspace_id = new.workspace_id
    for update;

  new.prev_hash := prev;
  new.row_hash := encode(
    digest(
      concat_ws('|',
        new.workspace_id::text,
        coalesce(new.agent_id::text, ''),
        new.action_type,
        new.action_name,
        coalesce(new.inputs_redacted::text, ''),
        coalesce(new.output_redacted::text, ''),
        coalesce(new.model, ''),
        coalesce(new.prompt_hash, ''),
        coalesce(new.cost_usd::text, ''),
        coalesce(new.latency_ms::text, ''),
        new.status,
        new.created_at::text,
        prev
      ),
      'sha256'
    ),
    'hex'
  );

  update workspace_chain_heads set last_hash = new.row_hash where workspace_id = new.workspace_id;

  return new;
end;
$$ language plpgsql security definer;

create trigger trg_events_chain_hash
  before insert on events
  for each row execute function events_chain_hash();

-- Enforce append-only at the database level (not just app convention).
create or replace function reject_mutation() returns trigger as $$
begin
  raise exception '% is append-only: % is not allowed', tg_table_name, tg_op;
end;
$$ language plpgsql;

create trigger trg_events_no_update before update on events
  for each row execute function reject_mutation();
create trigger trg_events_no_delete before delete on events
  for each row execute function reject_mutation();

-- =========================================================================
-- AUDIT_CHAIN — periodic checkpoints over the event log
-- =========================================================================
-- Distinct from events.row_hash (which chains individual rows): this table
-- stores one checkpoint per period (computed by the arq worker, see
-- backend/app/worker/tasks.py::compute_audit_checkpoint), chaining
-- checkpoint_hash -> prev_checkpoint_hash. Evidence packs cite a checkpoint
-- as "the log covering event X was sealed and unaltered as of Y".

create table audit_chain (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references workspaces(id) on delete cascade,
  period_start        timestamptz not null,
  period_end          timestamptz not null,
  event_count         integer not null,
  checkpoint_hash      text not null,
  prev_checkpoint_hash text not null,
  created_at          timestamptz not null default now()
);
create index idx_audit_chain_workspace on audit_chain(workspace_id, period_end desc);

create trigger trg_audit_chain_no_update before update on audit_chain
  for each row execute function reject_mutation();
create trigger trg_audit_chain_no_delete before delete on audit_chain
  for each row execute function reject_mutation();

-- =========================================================================
-- HUMAN-IN-THE-LOOP APPROVALS (F3)
-- =========================================================================

create table approvals (
  id               uuid primary key default gen_random_uuid(),
  workspace_id     uuid not null references workspaces(id) on delete cascade,
  -- Nullable: the approval is requested (and Slack pinged) BEFORE the SDK's
  -- wrapped function ever runs, so the event it will eventually produce
  -- doesn't exist yet. The worker back-fills this once ingest happens.
  event_id         uuid references events(id) on delete set null,
  agent_id         uuid references agents(id) on delete set null,
  requested_action jsonb not null,
  status           text not null default 'pending'
                   check (status in ('pending','approved','rejected','denied_timeout')),
  decision_by      text,              -- Slack user id or email of whoever decided
  decision_note    text,              -- free-text reason, or the "Edit" contents
  slack_channel    text,
  slack_message_ts text,
  requested_at     timestamptz not null default now(),
  decided_at       timestamptz,
  expires_at       timestamptz not null default (now() + interval '30 minutes')
);
create index idx_approvals_workspace on approvals(workspace_id, status);
create index idx_approvals_expires on approvals(expires_at) where status = 'pending';

-- =========================================================================
-- EVIDENCE PACK GENERATOR (F4)
-- =========================================================================

create table questionnaires (
  id           uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references workspaces(id) on delete cascade,
  filename     text not null,
  file_type    text not null check (file_type in ('pdf','csv','xlsx')),
  storage_path text not null,        -- path in the `questionnaires` Supabase Storage bucket
  status       text not null default 'processing'
               check (status in ('processing','ready','error')),
  error_message text,
  uploaded_by  uuid references auth.users(id),
  created_at   timestamptz not null default now()
);

create table answers (
  id              uuid primary key default gen_random_uuid(),
  questionnaire_id uuid not null references questionnaires(id) on delete cascade,
  workspace_id    uuid not null references workspaces(id) on delete cascade,
  question_text   text not null,
  draft_answer    text,
  final_answer    text,
  status          text not null default 'draft' check (status in ('draft','reviewed','approved')),
  reviewed_by     uuid references auth.users(id),
  reviewed_at     timestamptz,
  created_at      timestamptz not null default now()
);
create index idx_answers_questionnaire on answers(questionnaire_id);

create table evidence_links (
  id             uuid primary key default gen_random_uuid(),
  answer_id      uuid not null references answers(id) on delete cascade,
  event_id       uuid not null references events(id) on delete cascade,
  relevance_note text,
  created_at     timestamptz not null default now()
);
create index idx_evidence_links_answer on evidence_links(answer_id);

-- =========================================================================
-- BILLING (F9 — Stripe state mirror)
-- =========================================================================

create table subscriptions (
  workspace_id          uuid primary key references workspaces(id) on delete cascade,
  -- Stripe columns kept nullable, not dropped: Stripe is dormant, not
  -- removed (see whop_client.py's module docstring), so a config flip back
  -- to it later doesn't need a migration to bring these back.
  stripe_customer_id     text unique,
  stripe_subscription_id text unique,
  whop_membership_id     text unique,
  plan                   text not null default 'free' check (plan in ('free','starter','pro','enterprise')),
  status                 text not null default 'active',
  current_period_end     timestamptz,
  updated_at             timestamptz not null default now()
);

-- =========================================================================
-- ROW LEVEL SECURITY
-- =========================================================================
-- Design: the backend (FastAPI) talks to Postgres with the Supabase
-- service_role key, which bypasses RLS entirely — so all writes and
-- business logic (policy evaluation, hash chaining, Slack notifications)
-- go through the API, never directly from the browser.
-- The Next.js dashboard reads directly via the Supabase client with the
-- user's JWT for snappy, realtime-capable reads — so every table gets a
-- SELECT policy scoped to workspace membership, and no INSERT/UPDATE/DELETE
-- policy for the `authenticated` role (default-deny; only service_role,
-- which ignores RLS, can write).

create or replace function is_workspace_member(ws_id uuid) returns boolean as $$
  select exists (
    select 1 from workspace_members
    where workspace_id = ws_id and user_id = auth.uid()
  );
$$ language sql security definer stable;

alter table event_intake enable row level security;
alter table workspaces enable row level security;
alter table workspace_members enable row level security;
alter table agents enable row level security;
alter table api_keys enable row level security;
alter table policies enable row level security;
alter table events enable row level security;
alter table audit_chain enable row level security;
alter table approvals enable row level security;
alter table questionnaires enable row level security;
alter table answers enable row level security;
alter table evidence_links enable row level security;
alter table subscriptions enable row level security;

create policy select_own_workspaces on workspaces
  for select using (is_workspace_member(id));

create policy select_own_membership on workspace_members
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_agents on agents
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_api_keys on api_keys
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_policies on policies
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_events on events
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_audit_chain on audit_chain
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_approvals on approvals
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_questionnaires on questionnaires
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_answers on answers
  for select using (is_workspace_member(workspace_id));

create policy select_workspace_evidence_links on evidence_links
  for select using (
    exists (
      select 1 from answers a
      where a.id = evidence_links.answer_id and is_workspace_member(a.workspace_id)
    )
  );

create policy select_workspace_subscription on subscriptions
  for select using (is_workspace_member(workspace_id));
