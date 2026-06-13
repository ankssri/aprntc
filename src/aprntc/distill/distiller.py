"""Distiller — mine lessons from scored episodes, propose an attributable Playbook diff.

Nightly-batch shape (ADR 0006): pull episodes + their fused rewards from the
Trajectory Store, bucket into success / failure, mine generalized lessons per
bucket with an LLM distiller, then turn high-reward lessons into directives/
exemplars and failure lessons into "watch out for" anti-patterns — a small,
attributable :class:`PlaybookDiff` (edit, not regenerate).

Provider-agnostic (any ``LLMProvider``); deterministic parsing so tests run offline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from aprntc.memory.base import Lesson, LessonType
from aprntc.providers.base import LLMProvider
from aprntc.trajectory.schema import Episode
from aprntc.trajectory.store import TrajectoryStore
from aprntc.distill.playbook import PlaybookDiff

_MINE_PROMPT = (
    "You distill reusable lessons from an AI agent's task attempts. "
    "Given several {bucket} examples (task + final answer), output STRICT JSON: "
    '{{"lessons": [{{"situation": "<when this applies>", "lesson": "<one actionable sentence>"}}]}}. '
    "Generalize; do not copy specifics. Return at most {limit} lessons."
)


@dataclass
class DistillationResult:
    lessons: list[Lesson] = field(default_factory=list)
    diff: PlaybookDiff = field(default_factory=PlaybookDiff)

    @property
    def n_success(self) -> int:
        return sum(1 for l in self.lessons if l.lesson_type is not LessonType.FAILURE_PATTERN)

    @property
    def n_failure(self) -> int:
        return sum(1 for l in self.lessons if l.lesson_type is LessonType.FAILURE_PATTERN)


class Distiller:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str,
        success_threshold: float = 0.7,
        failure_threshold: float = 0.4,
        max_lessons_per_bucket: int = 3,
    ) -> None:
        self._provider = provider
        self._model = model
        self._success_t = success_threshold
        self._failure_t = failure_threshold
        self._limit = max_lessons_per_bucket

    def distill(
        self,
        store: TrajectoryStore,
        *,
        generation: int = 0,
        episode_ids: list[str] | None = None,
    ) -> DistillationResult:
        """Bucket scored episodes, mine lessons, and build an attributable diff."""
        episodes = (
            [store.get_episode(eid) for eid in episode_ids]
            if episode_ids is not None
            else store.query()
        )
        success: list[Episode] = []
        failure: list[Episode] = []
        for ep in episodes:
            fused = store.fused_reward(ep.episode_id)
            if fused is None:
                continue
            reward, _ = fused
            if reward >= self._success_t:
                success.append(ep)
            elif reward <= self._failure_t:
                failure.append(ep)

        lessons: list[Lesson] = []
        lessons += self._mine(success, bucket="successful", failure=False, generation=generation)
        lessons += self._mine(failure, bucket="failed", failure=True, generation=generation)

        diff = self._to_diff(lessons)
        return DistillationResult(lessons=lessons, diff=diff)

    def _mine(self, episodes: list[Episode], *, bucket: str, failure: bool,
              generation: int) -> list[Lesson]:
        if not episodes:
            return []
        examples = "\n\n".join(
            f"Task: {ep.task_input}\nAnswer: {ep.final_output or '(none)'}"
            for ep in episodes[:10]
        )
        messages = [
            {"role": "system", "content": _MINE_PROMPT.format(bucket=bucket, limit=self._limit)},
            {"role": "user", "content": examples},
        ]
        result = self._provider.complete(model=self._model, messages=messages)
        data = _parse_json(result.text)
        out: list[Lesson] = []
        ltype = LessonType.FAILURE_PATTERN if failure else LessonType.DIRECTIVE
        # rough reward proxy for the lesson: mean bucket reward isn't available here,
        # so use threshold midpoints as a conservative quality signal.
        reward = 0.2 if failure else 0.85
        for item in data.get("lessons", [])[: self._limit]:
            situation = str(item.get("situation", "")).strip()
            text = str(item.get("lesson", "")).strip()
            if not text:
                continue
            out.append(Lesson(content=text, lesson_type=ltype,
                              situation=situation or text, reward=reward,
                              generation=generation))
        return out

    def _to_diff(self, lessons: list[Lesson]) -> PlaybookDiff:
        diff = PlaybookDiff()
        for l in lessons:
            if l.lesson_type is LessonType.FAILURE_PATTERN:
                diff.add_watch_out.append(l.content)
            else:
                diff.add_directives.append(l.content)
            diff.provenance.setdefault(l.content, []).append(l.lesson_id)
        return diff


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
