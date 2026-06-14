"""B4 dashboard auth — session signing, user↔tenant mapping, OAuth callback flow."""

import pytest

from aprntc.auth import (
    MockProvider,
    OAuthProfile,
    SessionError,
    SessionSigner,
    UserStore,
)


# ─── session signing ─────────────────────────────────────────────────────────

def test_session_roundtrip():
    s = SessionSigner("x" * 32)
    tok = s.issue(user_id="google:1", tenant_id="acme", now=1000)
    p = s.verify(tok, now=1001)
    assert p["uid"] == "google:1" and p["tid"] == "acme"


def test_session_rejects_tamper():
    s = SessionSigner("x" * 32)
    tok = s.issue(user_id="u", tenant_id="t", now=1000)
    body, sig = tok.rsplit(".", 1)
    forged = body[:-2] + "AA" + "." + sig  # tweak payload, keep sig
    with pytest.raises(SessionError):
        s.verify(forged, now=1001)


def test_session_expires():
    s = SessionSigner("x" * 32, ttl_s=10)
    tok = s.issue(user_id="u", tenant_id="t", now=1000)
    with pytest.raises(SessionError):
        s.verify(tok, now=1011)   # past exp


def test_session_wrong_secret_fails():
    tok = SessionSigner("a" * 32).issue(user_id="u", tenant_id="t", now=1000)
    with pytest.raises(SessionError):
        SessionSigner("b" * 32).verify(tok, now=1001)


def test_session_missing_or_malformed():
    s = SessionSigner("x" * 32)
    for bad in (None, "", "no-dot", "a.b.c.d"):
        with pytest.raises(SessionError):
            s.verify(bad)


def test_session_secret_must_be_strong():
    with pytest.raises(ValueError):
        SessionSigner("short")


# ─── user store (one user = one tenant) ──────────────────────────────────────

def test_first_login_mints_tenant(tmp_path):
    us = UserStore(tmp_path / "u.json")
    user, created = us.upsert_from_oauth(provider="google", sub="123",
                                         email="maya@acme.com", name="Maya")
    assert created and user.user_id == "google:123"
    assert user.tenant_id == "maya"   # slug from email local-part

def test_returning_user_keeps_tenant(tmp_path):
    us = UserStore(tmp_path / "u.json")
    u1, c1 = us.upsert_from_oauth(provider="google", sub="123", email="a@x.com")
    u2, c2 = us.upsert_from_oauth(provider="google", sub="123", email="a@x.com", name="Updated")
    assert c1 is True and c2 is False
    assert u2.tenant_id == u1.tenant_id and u2.name == "Updated"

def test_distinct_users_get_distinct_tenants(tmp_path):
    us = UserStore(tmp_path / "u.json")
    a, _ = us.upsert_from_oauth(provider="google", sub="1", email="dev@x.com")
    b, _ = us.upsert_from_oauth(provider="google", sub="2", email="dev@y.com")  # same local-part
    assert a.tenant_id != b.tenant_id   # collision-resolved

def test_user_store_persists(tmp_path):
    path = tmp_path / "u.json"
    UserStore(path).upsert_from_oauth(provider="google", sub="1", email="a@x.com")
    assert UserStore(path).get("google:1").email == "a@x.com"


# ─── mock provider ───────────────────────────────────────────────────────────

def test_mock_provider_flow():
    p = MockProvider(OAuthProfile(provider="mock", sub="m1", email="d@e.com", name="Dev"))
    assert "code=mock-code" in p.authorize_url(state="s")
    prof = p.exchange_code("mock-code")
    assert prof.sub == "m1" and prof.email == "d@e.com"


# ─── API endpoints (offline via MockProvider) ────────────────────────────────

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aprntc.web.app import AppState, create_app  # noqa: E402


def _auth_client(tmp_path, profile=None):
    state = AppState(
        lineage_path=str(tmp_path / "l.json"),
        bundle_path=str(tmp_path / "b.json"),
        auth_provider=MockProvider(profile),
        session_signer=SessionSigner("k" * 32),
        users=UserStore(tmp_path / "u.json"),
    )
    return TestClient(create_app(state))


def test_auth_config_reports_enabled(tmp_path):
    c = _auth_client(tmp_path)
    assert c.get("/api/auth/config").json()["enabled"] is True
    # disabled when not configured
    plain = TestClient(create_app(AppState(lineage_path=str(tmp_path/"l"), bundle_path=str(tmp_path/"b"))))
    assert plain.get("/api/auth/config").json()["enabled"] is False


def test_me_anonymous_then_logged_in(tmp_path):
    c = _auth_client(tmp_path, OAuthProfile(provider="mock", sub="42",
                                            email="maya@acme.com", name="Maya"))
    # before login
    assert c.get("/api/auth/me").json()["authenticated"] is False
    # simulate the callback (mock exchange) — sets the session cookie
    cb = c.get("/api/auth/google/callback", params={"code": "mock-code"}, follow_redirects=False)
    assert cb.status_code in (302, 307) and "aprntc_session" in cb.cookies or cb.cookies
    # now /me reflects the user (TestClient persists cookies)
    me = c.get("/api/auth/me").json()
    assert me["authenticated"] is True and me["email"] == "maya@acme.com"
    assert me["tenant_id"]  # mapped to a tenant


def test_callback_requires_code(tmp_path):
    c = _auth_client(tmp_path)
    assert c.get("/api/auth/google/callback").status_code == 400


def test_logout_clears_session(tmp_path):
    c = _auth_client(tmp_path, OAuthProfile(provider="mock", sub="7", email="a@b.com"))
    c.get("/api/auth/google/callback", params={"code": "mock-code"})
    assert c.get("/api/auth/me").json()["authenticated"] is True
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").json()["authenticated"] is False


def test_login_redirects_to_provider(tmp_path):
    c = _auth_client(tmp_path)
    r = c.get("/api/auth/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "code=mock-code" in r.headers["location"]
