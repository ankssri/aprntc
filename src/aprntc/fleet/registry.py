"""Fleet registry — many parent agents under one apprentice, each its own lineage.

A :class:`Fleet` tracks :class:`AgentRef`s (id + domain + tags). Each agent gets its
own :class:`~aprntc.promote.lineage.LineageRegistry` (separate generations/playbook
path) so promotions are per-agent. JSON-file backed; the per-agent lineage files
live under a fleet directory.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from aprntc.promote.lineage import LineageRegistry


@dataclass
class AgentRef:
    agent_id: str
    domain: str = "generic"      # e.g. "support", "rag", "coding" — scopes lesson sharing
    name: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Fleet:
    """Registry of agents, each with its own lineage."""

    def __init__(self, root: str | os.PathLike[str] = "fleet") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._index = self._root / "fleet.json"
        self._agents: dict[str, AgentRef] = {}
        self._load()

    # -- agents ----------------------------------------------------------
    def register(self, ref: AgentRef) -> AgentRef:
        self._agents[ref.agent_id] = ref
        self._save()
        return ref

    def get(self, agent_id: str) -> AgentRef:
        if agent_id not in self._agents:
            raise KeyError(f"no agent {agent_id!r} in fleet")
        return self._agents[agent_id]

    def agents(self) -> list[AgentRef]:
        return list(self._agents.values())

    def by_domain(self, domain: str, *, exclude: str | None = None) -> list[AgentRef]:
        return [a for a in self._agents.values()
                if a.domain == domain and a.agent_id != exclude]

    # -- per-agent lineage ----------------------------------------------
    def lineage(self, agent_id: str) -> LineageRegistry:
        """The LineageRegistry for one agent (own generations / playbook path)."""
        self.get(agent_id)  # validates existence
        return LineageRegistry(self._root / f"{agent_id}.lineage.json")

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        if not self._index.exists():
            return
        data = json.loads(self._index.read_text(encoding="utf-8"))
        self._agents = {a["agent_id"]: AgentRef(**a) for a in data.get("agents", [])}

    def _save(self) -> None:
        self._index.write_text(
            json.dumps({"agents": [a.to_dict() for a in self._agents.values()]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
