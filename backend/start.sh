#!/bin/sh
# Runs the whole backend in one container: Redis, the arq worker, and the API.
# Used by hosts that give you a single container (Hugging Face Spaces). Railway
# ignores this and starts uvicorn directly via railway.json.
set -e

# Redis is only a job queue here (durable state lives in Supabase), so no
# persistence and no pid file: nothing to write, so it runs fine as a
# non-root user.
redis-server --save "" --appendonly no --bind 127.0.0.1 --port 6379 --loglevel warning --pidfile "" &
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"

arq app.worker.worker_settings.WorkerSettings &

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}"
