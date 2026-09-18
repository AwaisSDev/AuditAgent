from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute path so `.env` loads correctly regardless of the process's cwd
# (e.g. `uvicorn app.main:app --app-dir backend` run from the repo root).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    # Only needed for older projects still on the legacy static HS256 JWT
    # secret. Newer projects (the new sb_publishable_/sb_secret_ key system)
    # sign session JWTs asymmetrically (ES256) and are verified via their
    # JWKS endpoint instead — see security.py::get_current_user.
    supabase_jwt_secret: str = ""

    # Redis / arq
    redis_url: str = "redis://localhost:6379"

    # Anthropic — required only for the worker's LLM redaction pass and
    # evidence-pack drafting; both degrade gracefully (see services/
    # classification.py, worker/tasks.py) if this is left unset.
    anthropic_api_key: str = ""
    anthropic_sonnet_model: str = "claude-sonnet-4-6"
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    # Email fallback (Resend) -- Resend requires a verified sending domain.
    # auditagent.cloud is owned now, but this default won't actually send
    # until that domain is verified in Resend and EMAIL_FROM is updated.
    resend_api_key: str = ""
    email_from: str = "alerts@auditagent.cloud"

    # Whop -- the billing provider. whop_api_base_url points at the
    # sandbox by default (https://sandbox-api.whop.com/api/v1); switch it to
    # https://api.whop.com/api/v1 for real charges once ready, alongside
    # swapping in a production API key and plan ids -- sandbox and
    # production are entirely separate accounts/keys/plans per Whop's docs.
    whop_api_base_url: str = "https://sandbox-api.whop.com/api/v1"
    whop_api_key: str = ""
    whop_webhook_secret: str = ""
    whop_plan_starter: str = ""
    whop_plan_pro: str = ""

    # Error tracking (Sentry) -- unset by default (see main.py's sentry_sdk.init
    # call, guarded on this being non-empty) until a real DSN from a Sentry
    # project is provided.
    sentry_dsn: str = ""
    sentry_environment: str = "production"

    # App -- backend stays on the HF Space URL; auditagent.cloud is the
    # dashboard's custom domain (attached in Vercel, DNS verified).
    app_base_url: str = "https://awais1290-auditagent.hf.space"
    dashboard_base_url: str = "https://auditagent.cloud"
    cors_origins: str = "http://localhost:3000,https://auditagent.cloud,https://www.auditagent.cloud,https://getauditagent.vercel.app"
    approval_timeout_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
