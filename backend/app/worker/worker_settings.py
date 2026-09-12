from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.worker.tasks import (
    compute_audit_checkpoints,
    process_event_intake,
    process_questionnaire,
    sweep_expired_approvals,
)


class WorkerSettings:
    functions = [process_event_intake, process_questionnaire]
    cron_jobs = [
        cron(sweep_expired_approvals, minute=set(range(60)), run_at_startup=True),
        cron(compute_audit_checkpoints, hour=3, minute=0),  # once a day, low-traffic hour
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 20
