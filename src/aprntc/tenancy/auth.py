"""Tenant registry + API-key auth.

API keys are stored **hashed** (SHA-256), never in plaintext — the registry can
verify a presented key but can't reveal it. Each tenant has a stable ``tenant_id``
used to namespace all their data.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def new_api_key() -> str:
    """Generate a fresh opaque API key to hand to a tenant (shown once)."""
    return "aprntc_sk_" + secrets.token_urlsafe(32)


def hash_key(api_key: str) -> str:
    """Stable SHA-256 hash of an API key (what we store + compare)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


@dataclass
class Tenant:
    tenant_id: str
    name: str = ""
    key_hashes: list[str] = field(default_factory=list)  # supports key rotation
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"tenant_id": self.tenant_id, "name": self.name,
                "key_hashes": list(self.key_hashes), "active": self.active}


class TenantStore:
    """Registry of tenants + their hashed API keys (JSON-file backed)."""

    def __init__(self, path: str | os.PathLike[str] = "tenants.json") -> None:
        self._path = Path(path)
        self._tenants: dict[str, Tenant] = {}
        self._by_hash: dict[str, str] = {}   # key_hash -> tenant_id
        self._load()

    # -- management ------------------------------------------------------
    def create_tenant(self, tenant_id: str, *, name: str = "") -> tuple[Tenant, str]:
        """Create a tenant and issue its first API key. Returns (tenant, plaintext_key).

        The plaintext key is returned ONCE here; only its hash is stored.
        """
        if tenant_id in self._tenants:
            raise ValueError(f"tenant {tenant_id!r} already exists")
        key = new_api_key()
        t = Tenant(tenant_id=tenant_id, name=name, key_hashes=[hash_key(key)])
        self._tenants[tenant_id] = t
        self._by_hash[t.key_hashes[0]] = tenant_id
        self._save()
        return t, key

    def issue_key(self, tenant_id: str) -> str:
        """Issue an additional key for a tenant (rotation). Returns plaintext once."""
        t = self._require(tenant_id)
        key = new_api_key()
        h = hash_key(key)
        t.key_hashes.append(h)
        self._by_hash[h] = tenant_id
        self._save()
        return key

    def revoke_key(self, api_key: str) -> bool:
        h = hash_key(api_key)
        tid = self._by_hash.pop(h, None)
        if tid is None:
            return False
        self._tenants[tid].key_hashes = [k for k in self._tenants[tid].key_hashes if k != h]
        self._save()
        return True

    def deactivate(self, tenant_id: str) -> None:
        self._require(tenant_id).active = False
        self._save()

    # -- auth ------------------------------------------------------------
    def authenticate(self, api_key: str | None) -> Tenant | None:
        """Return the active Tenant for an API key, or None if invalid/inactive."""
        if not api_key:
            return None
        tid = self._by_hash.get(hash_key(api_key))
        if tid is None:
            return None
        t = self._tenants.get(tid)
        return t if (t and t.active) else None

    def get(self, tenant_id: str) -> Tenant:
        return self._require(tenant_id)

    def tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    # -- internals -------------------------------------------------------
    def _require(self, tenant_id: str) -> Tenant:
        if tenant_id not in self._tenants:
            raise KeyError(f"no tenant {tenant_id!r}")
        return self._tenants[tenant_id]

    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for d in data.get("tenants", []):
            t = Tenant(**d)
            self._tenants[t.tenant_id] = t
            for h in t.key_hashes:
                self._by_hash[h] = t.tenant_id

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"tenants": [t.to_dict() for t in self._tenants.values()]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
