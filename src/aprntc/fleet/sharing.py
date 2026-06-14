"""Cross-agent lesson sharing — let one agent's lessons benefit the fleet.

A lesson learned by agent A (e.g. "always cite the doc section") can help agent B —
but only if it's good and in-scope. Sharing is **gated**:

- **reward gate:** only share lessons above ``min_reward`` (don't spread mediocre ones).
- **type gate:** by default share directives + failure-patterns (generalizable);
  NOT exemplars (those are situation-specific to the source agent).
- **dedup:** skip lessons the target already has (by stable content id).
- **provenance:** shared copies are tagged ``shared_from`` in metadata so origin is
  auditable and a target can weight borrowed lessons differently if desired.

Domain scoping is the caller's job (use ``Fleet.by_domain``); these functions take
an explicit source/target lesson set so they're pure + testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from aprntc.memory.base import Lesson, LessonType, content_lesson_id

# Lesson types that generalize across agents (exemplars are source-specific).
_SHAREABLE_TYPES = (LessonType.DIRECTIVE, LessonType.FAILURE_PATTERN, LessonType.ROUTING_HEURISTIC)


@dataclass
class ShareReport:
    shared: list[Lesson] = field(default_factory=list)
    skipped_low_reward: int = 0
    skipped_wrong_type: int = 0
    skipped_duplicate: int = 0

    def summary(self) -> str:
        return (f"shared {len(self.shared)} | skipped: "
                f"{self.skipped_low_reward} low-reward, "
                f"{self.skipped_wrong_type} wrong-type, "
                f"{self.skipped_duplicate} duplicate")


def shareable_lessons(
    source: list[Lesson],
    *,
    min_reward: float = 0.7,
    types: tuple[LessonType, ...] = _SHAREABLE_TYPES,
) -> list[Lesson]:
    """Filter a source agent's lessons down to the ones worth sharing."""
    out = []
    for l in source:
        if l.lesson_type in types and l.reward >= min_reward:
            out.append(l)
    return out


def share_lessons(
    source: list[Lesson],
    target: list[Lesson],
    *,
    source_agent_id: str,
    min_reward: float = 0.7,
    types: tuple[LessonType, ...] = _SHAREABLE_TYPES,
) -> ShareReport:
    """Select shareable lessons from ``source`` not already in ``target``.

    Returns a :class:`ShareReport` whose ``shared`` lessons are tagged with
    ``shared_from`` provenance (and given fresh target-scoped content ids). The
    caller upserts ``report.shared`` into the target agent's memory.
    """
    existing = {content_lesson_id(l.situation, l.content) for l in target}
    report = ShareReport()
    for l in source:
        if l.lesson_type not in types:
            report.skipped_wrong_type += 1
            continue
        if l.reward < min_reward:
            report.skipped_low_reward += 1
            continue
        cid = content_lesson_id(l.situation, l.content)
        if cid in existing:
            report.skipped_duplicate += 1
            continue
        existing.add(cid)
        shared = replace(
            l,
            lesson_id=cid,
            metadata={**l.metadata, "shared_from": source_agent_id},
        )
        report.shared.append(shared)
    return report
