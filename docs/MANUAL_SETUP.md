# Manual setup checklist

Everything in this repo is real, runnable code. These are the steps only a
human can do — account creation, dashboard clicking, DNS. Do them in this
order; later steps depend on earlier ones.

## 1. Supabase

1. Create a project at https://supabase.com/dashboard (free tier is fine to start).
2. Project Settings → API: copy the **Project URL**, **anon public key**, and
   **service_role key**.
3. Project Settings → API → JWT Settings: copy the **JWT Secret**.
4. SQL Editor → paste and run [`supabase/schema.sql`](../supabase/schema.sql) in full.
5. Storage → create a new **private** bucket named `questionnaires` (used by F4's upload flow).
6. Authentication → Providers: enable **Email** (magic link) — it's on by default. Authentication → URL Configuration: add
   `http://localhost:3000/auth/callback` and `https://app.auditagent.dev/auth/callback` as redirect URLs.

## 2. Anthropic

1. Create an API key at https://console.anthropic.com/settings/keys.
2. Confirm you have access to `claude-sonnet-4-6` and `claude-haiku-4-5-20251001` (or swap the model ids in `backend/.env` if your account's available models differ).

## 3. Slack app (F3 — skip if starting on email-only approvals)

1. Go to https://api.slack.com/apps → **Create New App** → **From an app manifest**.
2. Paste [`slack-app/manifest.yaml`](../slack-app/manifest.yaml) (update the `request_url` to your real backend URL first).
3. Install the app to your workspace.
4. OAuth & Permissions → copy the **Bot User OAuth Token** (`xoxb-...`).
5. Basic Information → App Credentials → copy the **Signing Secret**.
6. In each customer workspace: invite the bot to whichever channel should receive approval requests (`/invite @AuditAgent`), then copy that channel's ID (right-click the channel → View channel details) into the workspace's Settings page in the AuditAgent dashboard.

## 4. Resend (email fallback for approvals)

1. Create an account at https://resend.com.
2. Verify a sending domain (or use their shared testing domain while developing).
3. Create an API key.

## 5. Stripe (F9)

1. Create a Stripe account, stay in **test mode** until you're ready to charge real customers.
2. Product catalog → create 3 products, each with one recurring monthly price:
   - Starter — $49/mo
   - Growth — $199/mo
   - Enterprise — $999/mo
   (Free has no Stripe price; it's the default `plan` value with no subscription row.)
3. Copy each price's ID (`price_...`) into `STRIPE_PRICE_STARTER` / `_GROWTH` / `_ENTERPRISE`.
4. Developers → API keys → copy the **Secret key**.
5. Developers → Webhooks → **Add endpoint**: URL = `{APP_BASE_URL}/v1/billing/webhook`, events = `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`. Copy the **Signing secret**.

## 6. Railway (backend + worker + Redis)

1. Create a Railway project, add a **Redis** plugin (gives you a `REDIS_URL`).
2. Add a service from this repo, root directory `backend/` — this becomes the **web** service (uses `backend/Dockerfile` and `backend/railway.json`, which starts uvicorn).
3. Add a **second** service from the same repo/root directory — this is the **worker**. In its Settings → Deploy, override the start command to:
   ```
   arq app.worker.worker_settings.WorkerSettings
   ```
4. Set the environment variables from `backend/.env.example` on **both** services (web and worker need the same config).
5. Generate a public domain for the web service only (Settings → Networking) — this is your `APP_BASE_URL` / `api.auditagent.dev`.

## 7. Vercel (dashboard)

1. Import this repo into Vercel, set **Root Directory** to `dashboard/`.
2. Add the env vars from `dashboard/.env.local.example`.
3. Point `auditagent.dev` / `app.auditagent.dev` at the Vercel project (Vercel → Domains).

## 8. DNS

At your registrar (or wherever `auditagent.dev` is managed):
- `app.auditagent.dev` → CNAME to Vercel (Vercel's UI gives you the exact record once you add the domain).
- `api.auditagent.dev` → CNAME to Railway's provided domain for the web service.

## 9. PyPI (F1 SDK + F6 MCP server) — done

Both packages are published:
- SDK: `pip install AudAgent` (https://pypi.org/project/AudAgent/) — PyPI
  rejected the obvious name `auditagent` as "too similar to an existing
  project" (an unrelated `audit-agent` package already exists; PyPI treats
  hyphens/underscores/case as equivalent for this check). Renamed the
  package/module/CLI to `audagent` everywhere, not just the PyPI listing
  name — `from audagent import AuditAgent`, CLI command `audagent`, one
  consistent name instead of a split between install name and import name.
- MCP server: `pip install auditagent-mcp` (https://pypi.org/project/auditagent-mcp/)
  — this name wasn't blocked (different normalized string than the
  colliding package), so it kept its original name.

To ship a new version of either later: bump `version` in the package's
`pyproject.toml`, then from that package's directory: `pip install build
twine`, `rm -rf dist build *.egg-info`, `python -m build`, `twine check
dist/*`, `twine upload dist/*` (needs a PyPI API token — Account Settings
→ API tokens). PyPI never lets you re-upload or overwrite an existing
version number, so double-check the version bump first.

Optional, separate step: getting `auditagent-mcp` listed inside Claude
Desktop/claude.ai's own UI (not just installable via pip) requires a
different, additional submission — see the note in `PRODUCTION_READINESS.md`
about the Desktop Extension (MCPB) process, since our server currently
runs over stdio, not remote HTTP.

## 10. First login

Once Supabase, backend, and dashboard are all deployed: sign in at
`app.auditagent.dev`, create your first workspace, create an API key under
Settings, and use it with the SDK (`pip install AudAgent`) or MCP server.
