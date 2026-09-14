"""Integration tests for POST /v1/auth/signup: the password-length guard,
successful account creation via the fake Supabase admin API, and a
Supabase-side error (e.g. duplicate email) surfacing as a clean 400
instead of an unhandled exception."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app


class _FakeAdmin:
    def __init__(self, existing_emails=None, should_fail=False):
        self.existing_emails = existing_emails or set()
        self.should_fail = should_fail
        self.created = []

    def create_user(self, payload):
        if self.should_fail or payload["email"] in self.existing_emails:
            raise Exception("User already registered")
        self.created.append(payload)
        return SimpleNamespace(user=SimpleNamespace(id=f"user-{len(self.created)}"))


class _FakeAuth:
    def __init__(self, admin):
        self.admin = admin


class _FakeDb:
    def __init__(self, admin):
        self.auth = _FakeAuth(admin)


@pytest.fixture
def client(monkeypatch):
    admin = _FakeAdmin()
    monkeypatch.setattr("app.routers.auth.get_db", lambda: _FakeDb(admin))
    with TestClient(app) as c:
        yield c, admin


def test_signup_creates_a_pre_confirmed_user(client):
    c, admin = client
    resp = c.post("/v1/auth/signup", json={"email": "new@example.com", "password": "hunter22"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["user_id"] == "user-1"
    assert admin.created[0]["email"] == "new@example.com"
    assert admin.created[0]["email_confirm"] is True


def test_signup_rejects_a_too_short_password(client):
    c, admin = client
    resp = c.post("/v1/auth/signup", json={"email": "new@example.com", "password": "abc"})
    assert resp.status_code == 400
    assert "6 characters" in resp.json()["detail"]
    assert admin.created == []


def test_signup_surfaces_a_duplicate_email_as_a_clean_400(monkeypatch):
    admin = _FakeAdmin(existing_emails={"taken@example.com"})
    monkeypatch.setattr("app.routers.auth.get_db", lambda: _FakeDb(admin))
    with TestClient(app) as c:
        resp = c.post("/v1/auth/signup", json={"email": "taken@example.com", "password": "hunter22"})
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()
