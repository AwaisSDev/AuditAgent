# Deployment

Do [`MANUAL_SETUP.md`](MANUAL_SETUP.md) first — this assumes every account
already exists and you just need the env vars wired up.

## Backend + worker → Hugging Face Spaces (free) or Railway

### Option A: Hugging Face Spaces (free, one container)

`backend/` is a ready-made Gradio Space (Docker Spaces are paid, Gradio
Spaces are free): its `README.md` front matter points at `space_app.py`,
which starts Redis and the worker and serves the API on port 7860.

1. Create a Space at huggingface.co/new-space: SDK **Gradio**, template
   **Blank**, hardware **CPU basic (free)**. Note its id, e.g. `you/Tracyn`.
2. In the Space's *Settings → Variables and secrets* add the variables listed
   in `backend/README.md` (only `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `CORS_ORIGINS`, `DASHBOARD_BASE_URL` and `APP_BASE_URL` are required).
3. In this GitHub repo add secret `HF_TOKEN` (a Hugging Face token with
   *write* access) and variable `HF_SPACE` (the id from step 1). The
   `deploy-backend-hf.yml` workflow then pushes `backend/` to the Space on
   every change; run it once by hand from the Actions tab to deploy now.
4. The API is at `https://<you>-<space>.hf.space`; check `/healthz`. Use that
   as `NEXT_PUBLIC_API_BASE_URL` on the website.

Free Spaces sleep after ~48 hours idle and take about a minute to wake.

### Option B: Railway

Two services from the same repo (root directory `backend/`), sharing one Redis:

| Service | Start command | Notes |
|---|---|---|
| `web` | (default, from `backend/Dockerfile`) `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Generate a public domain for this one — Railway's own `*.up.railway.app` domain works fine, or point a subdomain of `tracyn.online` at it |
| `worker` | override to `arq app.worker.worker_settings.WorkerSettings` | No public domain needed |
| `Redis` | Railway plugin | Gives both services `REDIS_URL` |

Environment variables (set on **both** `web` and `worker`) — see
[`backend/.env.example`](../backend/.env.example) for the full list:

```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_JWT_SECRET
REDIS_URL
ANTHROPIC_API_KEY
ANTHROPIC_SONNET_MODEL=claude-sonnet-4-6
ANTHROPIC_HAIKU_MODEL=claude-haiku-4-5-20251001
SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
RESEND_API_KEY
EMAIL_FROM
WHOP_API_BASE_URL=https://sandbox-api.whop.com/api/v1  # or https://api.whop.com/api/v1 for real charges
WHOP_API_KEY
WHOP_WEBHOOK_SECRET
WHOP_PLAN_STARTER
WHOP_PLAN_PRO
APP_BASE_URL=https://awais1290-auditagent.hf.space  # or this Railway service's own domain
DASHBOARD_BASE_URL=https://tracyn.online
CORS_ORIGINS=https://tracyn.online,https://www.tracyn.online
APPROVAL_TIMEOUT_MINUTES=30
```

Redeploy on every push to `main` (Railway does this automatically once
connected to the GitHub repo).

## Dashboard → Vercel

Root directory: `dashboard/`. Environment variables (see
[`dashboard/.env.local.example`](../dashboard/.env.local.example)):

```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
NEXT_PUBLIC_API_BASE_URL=https://awais1290-auditagent.hf.space
```

Domain: `tracyn.online` (and `www.tracyn.online`), attached in Vercel's
Domains settings — the Vercel-assigned `https://tracyn.vercel.app`
still works too.

## Database → Supabase

Nothing to "deploy" — `supabase/schema.sql` is run once via the SQL editor
(see MANUAL_SETUP.md step 1). Schema changes going forward: add a new
`supabase/migrations/NNNN_description.sql` file and run it the same way;
this MVP doesn't use the Supabase CLI's migration tooling to keep the
toolchain small, but nothing stops adopting it later.

## SDK + MCP server → PyPI

Both are independent of the above — publish whenever the code changes:

```bash
cd sdk && python -m build && twine upload dist/*
cd mcp-server && python -m build && twine upload dist/*
```

Bump the `version` in each `pyproject.toml` before re-publishing — PyPI
rejects re-uploading an existing version.

## Rollback

- Railway: redeploy a previous build from the service's Deployments tab.
- Vercel: "Promote to Production" any previous deployment from its dashboard.
- Database: `schema.sql` is additive-by-convention (new tables/columns);
  there's no down-migration tooling in this MVP — restore from a Supabase
  point-in-time backup if a schema change needs undoing.
