"""Playbook — the child agent's mutable, versioned artifact.

A Playbook = system prompt + curated exemplars + directives (+ "watch out for"
anti-patterns). Distillation **edits** it via an attributable :class:`PlaybookDiff`
(never regenerates it), so every change is traceable to its source lessons and a
single lesson can be reverted (ADR 0006). Content-addressed ``hash`` gives
reproducible lineage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Playbook:
    """The child's editable policy artifact."""

    system_prompt: str
    exemplars: list[str] = field(default_factory=list)      # situation→good-approach snippets
    directives: list[str] = field(default_factory=list)     # generalized "do this" rules
    watch_out: list[str] = field(default_factory=list)      # anti-patterns / failure warnings
    generation: int = 0

    @property
    def hash(self) -> str:
        """Content-addressed id for reproducible lineage."""
        blob = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        return "pb_" + hashlib.sha256(blob).hexdigest()[:16]

    def render(self, *, max_exemplars: int = 4, max_watch_out: int = 4) -> str:
        """Render the playbook into a system prompt for the child (token-budgeted)."""
        parts = [self.system_prompt.strip()]
        if self.directives:
            parts.append("Guidelines:\n" + "\n".join(f"- {d}" for d in self.directives))
        if self.exemplars:
            ex = self.exemplars[:max_exemplars]
            parts.append("Examples to follow:\n" + "\n".join(f"- {e}" for e in ex))
        if self.watch_out:
            wo = self.watch_out[:max_watch_out]
            parts.append("Watch out for:\n" + "\n".join(f"- {w}" for w in wo))
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "exemplars": list(self.exemplars),
            "directives": list(self.directives),
            "watch_out": list(self.watch_out),
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Playbook":
        return cls(
            system_prompt=d["system_prompt"],
            exemplars=list(d.get("exemplars", [])),
            directives=list(d.get("directives", [])),
            watch_out=list(d.get("watch_out", [])),
            generation=int(d.get("generation", 0)),
        )


@dataclass
class PlaybookDiff:
    """An attributable, reversible edit to a Playbook.

    Each added item links back to the lesson_id(s) that produced it, so a single
    bad lesson can be reverted without rebuilding the playbook.
    """

    add_directives: list[str] = field(default_factory=list)
    add_exemplars: list[str] = field(default_factory=list)
    add_watch_out: list[str] = field(default_factory=list)
    # provenance: item text -> list of source lesson ids
    provenance: dict[str, list[str]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not (self.add_directives or self.add_exemplars or self.add_watch_out)

    def apply(self, base: Playbook, *, cap_per_kind: int = 5) -> Playbook:
        """Return a NEW playbook (generation+1) with the diff applied.

        De-duplicates against existing content and caps how much can change per
        generation (catastrophic-forgetting guard / bounded change)."""
        def merged(existing: list[str], additions: list[str]) -> list[str]:
            out = list(existing)
            for item in additions:
                if item not in out:
                    out.append(item)
            return out

        return Playbook(
            system_prompt=base.system_prompt,
            directives=merged(base.directives, self.add_directives[:cap_per_kind]),
            exemplars=merged(base.exemplars, self.add_exemplars[:cap_per_kind]),
            watch_out=merged(base.watch_out, self.add_watch_out[:cap_per_kind]),
            generation=base.generation + 1,
        )

    def revert(self, playbook: Playbook, lesson_id: str) -> Playbook:
        """Remove items attributed to ``lesson_id`` (single-lesson rollback)."""
        drop = {text for text, ids in self.provenance.items() if lesson_id in ids}
        return Playbook(
            system_prompt=playbook.system_prompt,
            directives=[d for d in playbook.directives if d not in drop],
            exemplars=[e for e in playbook.exemplars if e not in drop],
            watch_out=[w for w in playbook.watch_out if w not in drop],
            generation=playbook.generation,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "add_directives": list(self.add_directives),
            "add_exemplars": list(self.add_exemplars),
            "add_watch_out": list(self.add_watch_out),
            "provenance": {k: list(v) for k, v in self.provenance.items()},
        }
