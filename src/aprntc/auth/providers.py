"""Pluggable OAuth providers — Google (live) + Mock (offline tests).

An :class:`OAuthProvider` does two things: build the authorize-redirect URL, and
exchange the returned ``code`` for a verified :class:`OAuthProfile` (sub/email/name).
The web layer is provider-agnostic, so GitHub/SSO can be added later.

GoogleProvider implements the real OpenID Connect flow; its ``exchange_code`` hits
Google's live endpoints (not offline-testable). MockProvider returns a scripted
profile so the session + user-mapping + callback logic is fully unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from urllib.parse import urlencode


@dataclass
class OAuthProfile:
    provider: str
    sub: str            # provider's stable user id
    email: str
    name: str = ""
    picture: str = ""


@runtime_checkable
class OAuthProvider(Protocol):
    name: str
    def authorize_url(self, *, state: str) -> str: ...
    def exchange_code(self, code: str) -> OAuthProfile: ...


class MockProvider:
    """Test/dev provider — returns a scripted profile, no network."""

    name = "mock"

    def __init__(self, profile: OAuthProfile | None = None,
                 *, redirect_uri: str = "http://localhost:8000/api/auth/mock/callback") -> None:
        self._profile = profile or OAuthProfile(
            provider="mock", sub="mock-123", email="dev@example.com", name="Dev User")
        self._redirect = redirect_uri

    def authorize_url(self, *, state: str) -> str:
        return f"{self._redirect}?state={state}&code=mock-code"

    def exchange_code(self, code: str) -> OAuthProfile:
        if not code:
            raise ValueError("missing code")
        return self._profile


class GoogleProvider:
    """Real Google OpenID Connect provider (live endpoints)."""

    name = "google"
    _AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
    _TOKEN = "https://oauth2.googleapis.com/token"
    _USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

    def __init__(self, *, client_id: str, client_secret: str, redirect_uri: str) -> None:
        if not (client_id and client_secret and redirect_uri):
            raise ValueError("GoogleProvider needs client_id, client_secret, redirect_uri")
        self._cid = client_id
        self._secret = client_secret
        self._redirect = redirect_uri

    def authorize_url(self, *, state: str) -> str:
        params = {
            "client_id": self._cid,
            "redirect_uri": self._redirect,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{self._AUTH}?{urlencode(params)}"

    def exchange_code(self, code: str) -> OAuthProfile:
        import httpx  # part of the byteplus/web extra

        tok = httpx.post(self._TOKEN, data={
            "code": code,
            "client_id": self._cid,
            "client_secret": self._secret,
            "redirect_uri": self._redirect,
            "grant_type": "authorization_code",
        }, timeout=15.0)
        tok.raise_for_status()
        access_token = tok.json()["access_token"]

        info = httpx.get(self._USERINFO,
                         headers={"Authorization": f"Bearer {access_token}"}, timeout=15.0)
        info.raise_for_status()
        d = info.json()
        return OAuthProfile(
            provider="google",
            sub=str(d["sub"]),
            email=d.get("email", ""),
            name=d.get("name", ""),
            picture=d.get("picture", ""),
        )
