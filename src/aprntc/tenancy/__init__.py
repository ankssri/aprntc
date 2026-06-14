"""Auth + multi-tenancy (B2) — isolate each customer's data behind an API key.

B0 exposed per-agent endpoints that, unscoped, any caller could read/write. Before
serving real external customers each **tenant** must be (1) authenticated and (2)
isolated — tenant A can never see tenant B's trajectories / playbooks / lineage.

- :class:`Tenant` / :class:`TenantStore` — registry of tenants + their API keys
  (keys stored HASHED, never plaintext).
- :class:`TenantResolver` — maps a request's API key → tenant, and hands back that
  tenant's **own** storage paths (per-tenant namespace) so every backend the API
  touches is scoped to the caller.

Design: **opt-in.** If no `TenantResolver` is configured the API runs in
single-tenant/dev mode exactly as before (all existing tests unaffected).
"""

from aprntc.tenancy.auth import Tenant, TenantStore, hash_key, new_api_key
from aprntc.tenancy.resolver import TenantContext, TenantResolver

__all__ = [
    "Tenant", "TenantStore", "hash_key", "new_api_key",
    "TenantContext", "TenantResolver",
]
