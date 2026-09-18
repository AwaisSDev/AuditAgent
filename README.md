# AuditAgent

Compliance infrastructure for AI agent startups: a Python SDK that logs every
agent action, a policy engine that routes risky actions to a human via
Slack, an audit dashboard, an evidence-pack generator for security
questionnaires, and a Claude MCP server to query it all conversationally.

Live at: dashboard `https://auditagent.cloud`, API `https://awais1290-auditagent.hf.space`.

## Repo map

```
supabase/schema.sql       F5 data model — tables, RLS, hash-chain triggers  [build step 1]
backend/                  FastAPI app + arq worker                          [steps 2, 3, 6, 9]
sdk/                      `auditagent` — pip-installable SDK                [step 4]
slack-app/manifest.yaml   Slack app manifest (F3)                           [step 5]
dashboard/                Next.js 14 dashboard                              [step 7]
mcp-server/               `auditagent-mcp` — Claude MCP server              [step 8]
docs/MANUAL_SETUP.md      Every account/dashboard click a human must do
docs/DEPLOYMENT.md        Env vars + how each piece ships
docs/GETTING_STARTED.md   Customer-facing onboarding walkthrough
docs/legal/               ToS/Privacy Policy drafts (need a lawyer's review — not final)
SUPPORT.md                Support channels, response-time targets, security reporting
```

## Architecture, in one pass

1. Dev installs `auditagent`, wraps a tool call with `@audit.track(...)`.
2. On init, the SDK fetches the workspace's policy YAML (F2).
3. If the policy flags the action, the SDK calls `POST /v1/approvals/request`
   *before* running the wrapped function, then blocks (polling) until a
   human decides in Slack (or email, if Slack isn't configured) — F3.
4. Once resolved (or immediately, if no approval was needed), the SDK runs
   the real function and fires the finished event at `POST /v1/events`. This
   call returns in milliseconds — it only writes to a staging table
   (`event_intake`) and enqueues an arq job.
5. The arq worker redacts PII (Presidio, then a Haiku pass for anything
   Presidio's NER misses), resolves/creates the agent, and inserts the
   final row into the **immutable, hash-chained** `events` table — F1.
6. The dashboard (Next.js) reads all of this — timeline, approvals queue,
   policy editor, SOC2 mapping, settings — via the same backend, JWT-authed
   as a logged-in user (F5, F7).
7. Uploading a questionnaire (F4) parses it into questions, finds candidate
   log events per question, and has Claude Sonnet draft a cited answer — a
   human always reviews before DOCX/CSV export.
8. The MCP server (F6) is a thin client over four read-only, API-key-authed
   backend endpoints, so asking Claude "any approvals waiting on me?" hits
   the same data as the dashboard.

## Every cut, and why

- **Redaction happens in the worker, not the SDK.** Presidio's NER pipeline
  cannot run in the SDK's <5ms overhead budget. The SDK's "overhead" is
  really just an in-memory queue `put()` — the network call and redaction
  happen on a background thread/job, fully decoupled from the wrapped call.
- **Two-stage ingest (`event_intake` → `events`).** Because `events` is
  append-only (a DB trigger rejects UPDATE/DELETE), redaction has to happen
  *before* a row is born, not via a later edit. The staging table exists
  only so the worker has something durable to process.
- **The SDK blocks synchronously on approval, before running the wrapped
  function**, rather than logging a `pending_approval` event and updating it
  later. This means `events.status` is written once, correctly, forever —
  no conflict with append-only, and no second state machine to keep in
  sync. The tradeoff: the agent process must be able to sit in an `await`
  (or a blocking thread) for up to 30 minutes, which is fine for async
  Python but wouldn't suit every runtime.
- **"Classification" (build step 3) became a second redaction pass**, not a
  separate action-type classifier — `action_type` is already explicit input
  from the developer (the policy engine matches on it), so there's nothing
  to infer. Haiku's job is catching PII/secrets Presidio's regex+NER misses.
- **Policy enforcement is trust-based.** The SDK checks the policy and calls
  the approval endpoint itself; nothing stops a developer from not wrapping
  a call. The threat model here is "give an honest team a real governance
  trail," not "stop a malicious developer from evading their own compliance
  tool" — that's a different, much bigger product.
- **Evidence search is keyword/ILIKE, not semantic/vector search.** Good
  enough to surface plausible candidate events per question; a human always
  reviews the draft before anything ships, which is the actual safety net.
- **Dashboard UI primitives are hand-written**, not the real shadcn/ui CLI
  output (no CLI in this environment) — same file/prop shapes, so swapping
  in genuine shadcn components later is a mechanical, low-risk change.
- **No RBAC enforcement yet**, even though `workspace_members.role` exists.
  Any member can currently edit policy or decide approvals. Fine for a
  single-team MVP; worth hardening before selling to teams that need it.
- **No websockets/realtime** — the dashboard polls (10–15s) via TanStack
  Query. Simpler, no extra infra, acceptable latency for an approvals queue.
- **Audit checkpoints are a daily arq cron job**, not Postgres `pg_cron` —
  avoids an extra Supabase extension/add-on for a job that doesn't need
  second-level precision.
- **No automated test suite beyond the SDK's policy unit tests** plus
  compile/type/build checks on everything. Right call for 10–15 hrs/week;
  add integration tests once real customer data is at stake.

## Local development

```bash
# 1. backend
cd backend
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt   # includes the en_core_web_sm spaCy model as a wheel — no separate `spacy download` step needed
cp .env.example .env   # fill in Supabase/Anthropic/Redis keys
uvicorn app.main:app --reload            # terminal 1
arq app.worker.worker_settings.WorkerSettings   # terminal 2 (needs Redis running locally)

# 2. dashboard
cd dashboard
npm install
cp .env.local.example .env.local
npm run dev

# 3. SDK (editable install for local testing against your own agent code)
cd sdk
pip install -e .
```

See [`docs/MANUAL_SETUP.md`](docs/MANUAL_SETUP.md) for every account/dashboard
step (Supabase project, Slack app, Whop plans, PyPI, DNS) and
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for shipping to Railway + Vercel.
