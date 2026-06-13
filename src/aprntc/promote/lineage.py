"""Lineage registry — versioned generations + one-click rollback.

Records the promoted path as a linear chain of generations (G0 parent → G1 → …),
each pinning the playbook hash, the gate report summary, and a pointer to its
parent. Promotion appends a generation and advances ``current``; rollback moves
``current`` back to the prior generation (instant revert). JSON-file backed so it
survives across runs and is inspectable by the UI.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Generation:
    generation: int
    playbook_hash: str
    parent_generation: int | None
    gate_summary: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LineageRegistry:
    """Append-only generations with a movable ``current`` pointer (promote/rollback)."""

    def __init__(self, path: str | os.PathLike[str] = "lineage.json") -> None:
        self._path = Path(path)
        self._generations: list[Generation] = []
        self._current: int | None = None
        self._load()

    # -- state -----------------------------------------------------------
    @property
    def current(self) -> Generation | None:
        if self._current is None:
            return None
        return self._generations[self._current]

    def history(self) -> list[Generation]:
        return list(self._generations)

    # -- operations ------------------------------------------------------
    def register_parent(self, playbook_hash: str, *, note: str = "initial parent") -> Generation:
        """Seed G0 (the original parent). Only valid when the registry is empty."""
        if self._generations:
            raise RuntimeError("parent already registered")
        gen = Generation(generation=0, playbook_hash=playbook_hash,
                         parent_generation=None, note=note)
        self._generations.append(gen)
        self._current = 0
        self._save()
        return gen

    def promote(self, playbook_hash: str, *, gate_summary: str = "", note: str = "") -> Generation:
        """Append a new generation built on the current one and advance ``current``."""
        if self._current is None:
            raise RuntimeError("no parent registered; call register_parent first")
        new_gen = Generation(
            generation=len(self._generations),
            playbook_hash=playbook_hash,
            parent_generation=self.current.generation,
            gate_summary=gate_summary,
            note=note,
        )
        self._generations.append(new_gen)
        self._current = new_gen.generation
        self._save()
        return new_gen

    def rollback(self) -> Generation:
        """Revert ``current`` to the prior generation (instant one-click rollback)."""
        cur = self.current
        if cur is None or cur.parent_generation is None:
            raise RuntimeError("nothing to roll back to")
        self._current = cur.parent_generation
        self._save()
        return self.current  # type: ignore[return-value]

    # -- persistence -----------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._generations = [Generation(**g) for g in data.get("generations", [])]
        self._current = data.get("current")

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "current": self._current,
            "generations": [g.to_dict() for g in self._generations],
        }
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
