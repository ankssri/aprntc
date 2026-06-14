"""Dashboard auth (B4) — human login for the console (distinct from B2 API keys).

B2 = machine auth (API keys identify a tenant/agent). This = HUMAN auth: a person
signs in to the dashboard with Google, gets a session, and is mapped to a tenant so
they only see their own data.

- :mod:`aprntc.auth.session` — sign/verify stateless session tokens (HMAC, stdlib).
- :mod:`aprntc.auth.users` — User store + user↔tenant mapping (one user = one tenant).
- :mod:`aprntc.auth.providers` — pluggable OAuth: GoogleProvider + a MockProvider for
  offline tests. The session layer + user mapping are 100% testable; the live Google
  handshake is verified in-browser with real credentials.
"""

from aprntc.auth.session import SessionError, SessionSigner
from aprntc.auth.users import User, UserStore
from aprntc.auth.providers import (
    GoogleProvider,
    MockProvider,
    OAuthProfile,
    OAuthProvider,
)

__all__ = [
    "SessionError", "SessionSigner",
    "User", "UserStore",
    "OAuthProfile", "OAuthProvider", "MockProvider", "GoogleProvider",
]
