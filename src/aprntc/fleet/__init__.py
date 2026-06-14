"""Multi-agent fleets + cross-agent lesson sharing (A6).

One apprentice, many parent agents. Each agent has its own lineage (Playbook
generations) — but **lessons can be shared** across agents so a fix learned by one
benefits the fleet. Sharing is scoped + gated so a support-agent lesson doesn't
pollute a coding-agent:

- :class:`Fleet` — registry of :class:`AgentRef`, each with its own lineage file.
- :func:`shareable_lessons` / :func:`share_lessons` — select high-reward, in-scope
  lessons from a source agent and offer them to a target agent (tagged with origin,
  reward-gated, domain-gated, deduped).
"""

from aprntc.fleet.registry import AgentRef, Fleet
from aprntc.fleet.sharing import ShareReport, share_lessons, shareable_lessons

__all__ = ["AgentRef", "Fleet", "ShareReport", "share_lessons", "shareable_lessons"]
