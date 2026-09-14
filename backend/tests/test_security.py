"""Unit tests for app/security.py — the auth layer every router depends on.
Covers API-key hashing/lookup/revocation, the HS256 JWT verification path
(legacy Supabase projects with a static secret), and workspace-membership
enforcement. The ES256/JWKS path (newer Supabase projects) is exercised
via test_approvals_integration.py's dependency overrides rather than here,
since it needs a real network-backed JWKS client to test meaningfully."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app.security import (
    generate_api_key,
    get_api_key_auth,
    get_current_user,
    hash_api_key,
    require_workspace_member,
)

JWT_SECRET = "test-secret-at-least-32-bytes-long!!"


def _settings(**overrides):
    base = SimpleNamespace(supabase_jwt_secret=JWT_SECRET, supabase_url="https://example.supabase.co")
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# -- hash_api_key / generate_api_key -----------------------------------------


def test_hash_api_key_is_deterministic():
    assert hash_api_key("secret-value") == hash_api_key("secret-value")


def test_hash_api_key_differs_for_different_input():
    assert hash_api_key("a") != hash_api_key("b")


def test_generate_api_key_hash_matches_the_full_key():
    full_key, prefix, key_hash = generate_api_key()
    assert full_key.startswith(prefix + "_")
    assert prefix.startswith("al_live_")
    assert key_hash == hash_api_key(full_key)


def test_generate_api_key_is_unique_each_call():
    key1, prefix1, _ = generate_api_key()
    key2, prefix2, _ = generate_api_key()
    assert key1 != key2
    assert prefix1 != prefix2


# -- get_current_user (HS256 / legacy secret path) ---------------------------


@pytest.mark.anyio
async def test_get_current_user_rejects_missing_header(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: _settings())
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_accepts_a_valid_hs256_token(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: _settings())
    token = jwt.encode({"sub": "user-1", "email": "a@example.com", "aud": "authenticated"}, JWT_SECRET, algorithm="HS256")

    user = await get_current_user(authorization=f"Bearer {token}")

    assert user.id == "user-1"
    assert user.email == "a@example.com"


@pytest.mark.anyio
async def test_get_current_user_rejects_a_token_signed_with_the_wrong_secret(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: _settings())
    token = jwt.encode({"sub": "user-1", "aud": "authenticated"}, "a-different-32-byte-wrong-secret!", algorithm="HS256")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_rejects_an_expired_token(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: _settings())
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode({"sub": "user-1", "aud": "authenticated", "exp": expired}, JWT_SECRET, algorithm="HS256")

    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


# -- require_workspace_member -------------------------------------------------


class _FakeQuery:
    def __init__(self, matches):
        self.matches = matches

    def eq(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return SimpleNamespace(data=self.matches)


class _FakeTable:
    def __init__(self, matches):
        self.matches = matches

    def select(self, *_a, **_kw):
        return _FakeQuery(self.matches)


class _FakeDb:
    def __init__(self, matches):
        self.matches = matches

    def table(self, _name):
        return _FakeTable(self.matches)


@pytest.mark.anyio
async def test_require_workspace_member_allows_a_real_member(monkeypatch):
    from app.security import CurrentUser

    monkeypatch.setattr("app.security.get_db", lambda: _FakeDb([{"user_id": "user-1"}]))
    user = CurrentUser(id="user-1", email="a@example.com")

    result = await require_workspace_member("ws-1", user=user)

    assert result is user


@pytest.mark.anyio
async def test_require_workspace_member_rejects_a_non_member(monkeypatch):
    from app.security import CurrentUser

    monkeypatch.setattr("app.security.get_db", lambda: _FakeDb([]))
    user = CurrentUser(id="user-1", email="a@example.com")

    with pytest.raises(HTTPException) as exc:
        await require_workspace_member("ws-1", user=user)
    assert exc.value.status_code == 403


# -- get_api_key_auth ---------------------------------------------------------


class _FakeApiKeyQuery:
    def __init__(self, rows):
        self.rows = rows
        self.filters = {}
        self.payload = None
        self.op = "select"

    def eq(self, field, value):
        self.filters[field] = value
        return self

    def limit(self, _n):
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def execute(self):
        matches = [r for r in self.rows if all(r.get(k) == v for k, v in self.filters.items())]
        if self.op == "update":
            for r in matches:
                r.update(self.payload)
        return SimpleNamespace(data=matches)


class _FakeApiKeyTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_a, **_kw):
        return _FakeApiKeyQuery(self.rows)

    def update(self, payload):
        q = _FakeApiKeyQuery(self.rows)
        return q.update(payload)


class _FakeApiKeyDb:
    def __init__(self, rows):
        self.rows = rows

    def table(self, _name):
        return _FakeApiKeyTable(self.rows)


@pytest.mark.anyio
async def test_get_api_key_auth_rejects_missing_header():
    with pytest.raises(HTTPException) as exc:
        await get_api_key_auth(authorization=None)
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_api_key_auth_rejects_a_malformed_key():
    with pytest.raises(HTTPException) as exc:
        await get_api_key_auth(authorization="Bearer notarealkey")
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_api_key_auth_rejects_an_unknown_prefix(monkeypatch):
    monkeypatch.setattr("app.security.get_db", lambda: _FakeApiKeyDb([]))
    full_key, _prefix, _hash = generate_api_key()

    with pytest.raises(HTTPException) as exc:
        await get_api_key_auth(authorization=f"Bearer {full_key}")
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_api_key_auth_rejects_a_revoked_key(monkeypatch):
    full_key, prefix, key_hash = generate_api_key()
    row = {"id": "key-1", "workspace_id": "ws-1", "revoked_at": "2026-01-01T00:00:00Z", "key_hash": key_hash, "key_prefix": prefix}
    monkeypatch.setattr("app.security.get_db", lambda: _FakeApiKeyDb([row]))

    with pytest.raises(HTTPException) as exc:
        await get_api_key_auth(authorization=f"Bearer {full_key}")
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_api_key_auth_rejects_a_prefix_match_with_wrong_secret(monkeypatch):
    full_key, prefix, key_hash = generate_api_key()
    row = {"id": "key-1", "workspace_id": "ws-1", "revoked_at": None, "key_hash": key_hash, "key_prefix": prefix}
    monkeypatch.setattr("app.security.get_db", lambda: _FakeApiKeyDb([row]))

    forged_key = f"{prefix}_completely-different-secret"
    with pytest.raises(HTTPException) as exc:
        await get_api_key_auth(authorization=f"Bearer {forged_key}")
    assert exc.value.status_code == 401


@pytest.mark.anyio
async def test_get_api_key_auth_accepts_a_valid_key_and_updates_last_used(monkeypatch):
    full_key, prefix, key_hash = generate_api_key()
    row = {"id": "key-1", "workspace_id": "ws-1", "revoked_at": None, "key_hash": key_hash, "key_prefix": prefix}
    monkeypatch.setattr("app.security.get_db", lambda: _FakeApiKeyDb([row]))

    auth = await get_api_key_auth(authorization=f"Bearer {full_key}")

    assert auth.workspace_id == "ws-1"
    assert auth.api_key_id == "key-1"
    assert row["last_used_at"] is not None
