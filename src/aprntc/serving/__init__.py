"""Playbook serving (B0) — the OUTBOUND integration for EXTERNAL agents.

The missing half of external integration (see docs/PRODUCTION.md): aprntc can't
push config into a customer's process, so the agent PULLS its active playbook.

- :class:`PlaybookRegistry` — per-agent store of playbooks: register G0
  (or infer it from observed traffic), set the active version on promotion,
  fetch the active playbook, roll back.
- REST endpoints (in :mod:`aprntc.web.app`) expose register / get-active so an
  external agent does a one-line ``get_active_playbook(agent_id)`` fetch.
"""

from aprntc.serving.registry import (
    ActivePlaybook,
    PlaybookRegistry,
    infer_g0_from_messages,
)

__all__ = ["ActivePlaybook", "PlaybookRegistry", "infer_g0_from_messages"]
