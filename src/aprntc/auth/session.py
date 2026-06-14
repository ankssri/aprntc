"""Stateless session tokens — signed with HMAC-SHA256 (stdlib only).

A session is a compact ``base64(payload).base64(sig)`` token stored in a cookie.
The payload is signed with ``APRNTC_SESSION_SECRET`` so it can't be forged/tampered;
it carries the user id, tenant id, and an expiry. No DB lookup needed to validate a
request (stateless) — though revocation lists can be layered on later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class SessionError(Exception):
    """Raised when a session token is missing, malformed, tampered, or expired."""


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class SessionSigner:
    """Issues + verifies signed session tokens."""

    def __init__(self, secret: str, *, ttl_s: int = 7 * 24 * 3600) -> None:
        if not secret or len(secret) < 16:
            raise ValueError("session secret must be set and >= 16 chars")
        self._secret = secret.encode("utf-8")
        self._ttl = ttl_s

    def issue(self, *, user_id: str, tenant_id: str, now: float | None = None,
              extra: dict[str, Any] | None = None) -> str:
        issued = int(now if now is not None else time.time())
        payload = {
            "uid": user_id,
            "tid": tenant_id,
            "iat": issued,
            "exp": issued + self._ttl,
            **(extra or {}),
        }
        body = _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        return f"{body}.{self._sign(body)}"

    def verify(self, token: str | None, *, now: float | None = None) -> dict[str, Any]:
        if not token or "." not in token:
            raise SessionError("missing or malformed session")
        body, sig = token.rsplit(".", 1)
        # constant-time signature check
        if not hmac.compare_digest(sig, self._sign(body)):
            raise SessionError("bad session signature")
        try:
            payload = json.loads(_b64d(body))
        except (ValueError, json.JSONDecodeError):
            raise SessionError("corrupt session payload")
        exp = payload.get("exp", 0)
        if (now if now is not None else time.time()) >= exp:
            raise SessionError("session expired")
        return payload

    def _sign(self, body: str) -> str:
        return _b64e(hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest())
