import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings
from app.db import get_db, run_db


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    """Supabase's newer projects sign session JWTs asymmetrically (ES256)
    and publish the verification keys here, rather than a shared secret."""
    settings = get_settings()
    return jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


@dataclass
class CurrentUser:
    id: str
    email: str | None = None


@dataclass
class WorkspaceKeyAuth:
    workspace_id: str
    api_key_id: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    """Verifies the Supabase-issued JWT the dashboard sends on every request."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing bearer token")
    token = authorization.split(" ", 1)[1]
    settings = get_settings()
    try:
        if settings.supabase_jwt_secret:
            # Legacy projects: static HS256 secret.
            payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        else:
            # New projects: verify against Supabase's published JWKS. Only
            # actually hits the network on a cache miss (PyJWKClient caches
            # signing keys), but that fetch is itself a blocking call, so it
            # still needs to run off the event loop.
            signing_key = await asyncio.to_thread(_jwks_client().get_signing_key_from_jwt, token)
            payload = jwt.decode(token, signing_key.key, algorithms=["ES256"], audience="authenticated")
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc
    return CurrentUser(id=payload["sub"], email=payload.get("email"))


async def require_workspace_member(workspace_id: str, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    db = get_db()
    res = await run_db(
        lambda: db.table("workspace_members")
        .select("user_id")
        .eq("workspace_id", workspace_id)
        .eq("user_id", user.id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this workspace")
    return user


def hash_api_key(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (full_key_to_show_once, prefix_for_lookup, hash_to_store)."""
    secret = secrets.token_urlsafe(32)
    prefix = "al_live_" + secrets.token_hex(4)
    full_key = f"{prefix}_{secret}"
    return full_key, prefix, hash_api_key(full_key)


async def verify_api_key(api_key: str) -> WorkspaceKeyAuth | None:
    """The actual validation behind get_api_key_auth, factored out so
    anything else that receives a bearer token from a non-HTTP-header
    source can reuse the exact same check rather than re-implementing it
    -- see services/mcp_oauth_provider.py's load_access_token, which
    verifies the *same* API keys when a caller connects to the MCP server
    via a manually-pasted key instead of the OAuth flow. Returns None
    (never raises) on any failure, so callers decide their own error
    handling instead of inheriting an HTTPException shaped for this
    module's own FastAPI dependency use."""
    if "_" not in api_key:
        return None

    prefix = "_".join(api_key.split("_")[:3])  # al_live_xxxxxxxx
    key_hash = hash_api_key(api_key)

    db = get_db()
    res = await run_db(
        lambda: db.table("api_keys")
        .select("id, workspace_id, revoked_at, key_hash")
        .eq("key_prefix", prefix)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    row = res.data[0]
    if row["revoked_at"] is not None:
        return None
    if not secrets.compare_digest(row["key_hash"], key_hash):
        return None

    await run_db(
        lambda: db.table("api_keys")
        .update({"last_used_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", row["id"])
        .execute()
    )

    return WorkspaceKeyAuth(workspace_id=row["workspace_id"], api_key_id=row["id"])


async def get_api_key_auth(authorization: str | None = Header(default=None)) -> WorkspaceKeyAuth:
    """Auth for the SDK ingest endpoint: `Authorization: Bearer <api_key>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Missing API key")
    api_key = authorization.split(" ", 1)[1].strip()
    auth = await verify_api_key(api_key)
    if auth is None:
        raise _unauthorized("Invalid API key")
    return auth
