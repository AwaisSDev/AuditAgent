# Deployment

Do [`MANUAL_SETUP.md`](MANUAL_SETUP.md) first — this assumes every account
already exists and you just need the env vars wired up.

## Backend + worker → Railway

Two services from the same repo (root directory `backend/`), sharing one Redis:

| Service | Start command | Notes |
|---|---|---|
| `web` | (default, from `backend/Dockerfile`) `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Generate a public domain for this one → `api.auditagent.dev` |
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
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
STRIPE_PRICE_STARTER
STRIPE_PRICE_GROWTH
STRIPE_PRICE_ENTERPRISE
APP_BASE_URL=https://api.auditagent.dev
DASHBOARD_BASE_URL=https://app.auditagent.dev
CORS_ORIGINS=https://app.auditagent.dev
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
NEXT_PUBLIC_API_BASE_URL=https://api.auditagent.dev
```

Domain: `app.auditagent.dev`, added under Vercel → Domains.

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
