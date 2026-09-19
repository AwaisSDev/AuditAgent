---
title: Tracyn API
emoji: 🪶
colorFrom: yellow
colorTo: gray
sdk: gradio
sdk_version: 6.27.0
python_version: "3.10"
app_file: space_app.py
pinned: false
---

# Tracyn backend

FastAPI API plus an arq worker. This directory is deployable two ways:

- **Hugging Face Spaces (free Gradio Space):** the front matter above makes
  this folder a Space whose entry point is `space_app.py`; it starts Redis
  (`packages.txt`) and the worker, then serves the API on port 7860. Set the
  variables below under the Space's *Settings → Variables and secrets*.
- **Any Docker host:** `Dockerfile` + `start.sh` run the same three things in
  one container.
- **Railway:** `railway.json` starts uvicorn only; add a Redis plugin and a
  second service running `arq app.worker.worker_settings.WorkerSettings`.

## Variables

Required:

| Name | Where to get it |
| --- | --- |
| `SUPABASE_URL` | Supabase → Project Settings → API |
| `SUPABASE_SERVICE_ROLE_KEY` | same page, the `service_role` key (secret: never put it in the front end) |
| `CORS_ORIGINS` | the site origin(s) the dashboard is served from, comma separated, e.g. `https://tracyn.online,https://www.tracyn.online` |
| `DASHBOARD_BASE_URL` | e.g. `https://tracyn.online` (used in Slack/email links) |
| `APP_BASE_URL` | this API's public URL, e.g. `https://<user>-tracyn-api.hf.space` |

Optional, each feature degrades gracefully without it:

| Name | Enables |
| --- | --- |
| `ANTHROPIC_API_KEY` | second-pass PII redaction and evidence-pack drafting |
| `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` | approvals in Slack (otherwise email) |
| `RESEND_API_KEY`, `EMAIL_FROM` | email approvals |
| `WHOP_*` | billing |
| `SUPABASE_JWT_SECRET` | only for older Supabase projects with the legacy HS256 secret |
| `REDIS_URL` | an external Redis; unset means the in-container one |

Health check: `GET /healthz`.

## Tests

Pure-logic unit tests (policy engine, plan limits, API key hashing, the
approval decision race-condition guard) run without Supabase/Redis:

```bash
pip install -r requirements-dev.txt
pytest
```
