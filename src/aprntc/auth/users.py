"""User store + user↔tenant mapping (one user = one tenant).

A human who signs in (via Google) becomes a :class:`User`, keyed by a stable
provider identity (``provider:sub``). On first login we mint a tenant for them
(one user = one tenant, per the chosen model) so their data is isolated; returning
users resolve to their existing tenant. JSON-file backed.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "user"


@dataclass
class User:
    user_id: str          # stable: "{provider}:{sub}"
    email: str
    name: str
    tenant_id: str
    created_at: str
    picture: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UserStore:
    """Maps OAuth identities → Users (+ their tenant). JSON-persisted."""

    def __init__(self, path: str | os.PathLike[str] = "users.json") -> None:
        self._path = Path(path)
        self._by_id: dict[str, User] = {}
        self._load()

    def get(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def upsert_from_oauth(self, *, provider: str, sub: str, email: str,
                          name: str = "", picture: str = "",
                          now: str | None = None) -> tuple[User, bool]:
        """Return (user, created). First login mints a tenant (one user = one tenant);
        returning users keep their tenant. ``sub`` is the provider's stable id."""
        user_id = f"{provider}:{sub}"
        existing = self._by_id.get(user_id)
        if existing is not None:
            # refresh mutable profile fields on each login
            existing.email = email or existing.email
            existing.name = name or existing.name
            existing.picture = picture or existing.picture
            self._save()
            return existing, False

        tenant_id = self._mint_tenant_id(email or user_id)
        user = User(
            user_id=user_id, email=email, name=name or email,
            tenant_id=tenant_id, picture=picture,
            created_at=now or _now(),
        )
        self._by_id[user_id] = user
        self._save()
        return user, True

    def _mint_tenant_id(self, seed: str) -> str:
        base = _slug(seed.split("@")[0])
        tid = base
        n = 1
        existing = {u.tenant_id for u in self._by_id.values()}
        while tid in existing:
            n += 1
            tid = f"{base}-{n}"
        return tid

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._by_id = {u["user_id"]: User(**u) for u in data.get("users", [])}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"users": [u.to_dict() for u in self._by_id.values()]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
