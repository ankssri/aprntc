"""Distiller — mine lessons from scored episodes, propose an attributable Playbook diff.

Nightly-batch shape (ADR 0006): pull episodes + their fused rewards from the
Trajectory Store, bucket into success / failure, **cluster by situation**, mine
generalized lessons per cluster with an LLM distiller, then turn:
  - high-reward successes → **exemplars** (concrete situation→good-answer the child
    imitates) AND **directives** (generalized rules), and
  - failures → **failure-pattern** "watch out for" anti-patterns,
into a small, attributable :class:`PlaybookDiff` (edit, not regenerate).

Quality (A0): exemplars + richer mining context (tools used) + clustering +
anti-generic prompt make lessons specific enough to actually move a child.

Provider-agnostic (any ``LLMProvider``); deterministic parsing so tests run offline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from aprntc.memory.base import Lesson, LessonType
from aprntc.providers.base import LLMProvider
from aprntc.trajectory.schema import Episode, StepType
from aprntc.trajectory.store import TrajectoryStore
from aprntc.distill.playbook import PlaybookDiff

_DIRECTIVE_PROMPT = (
    "You extract REUSABLE, SPECIFIC lessons from an AI agent's {bucket} task attempts. "
    "Each example shows the task, the tools the agent used, and its answer. "
    "Output STRICT JSON: {{\"lessons\": [{{\"situation\": \"<the kind of request this applies to>\", "
    "\"lesson\": \"<one concrete, actionable instruction>\"}}]}}. "
    "RULES: be specific to the situation and reference the right tool/approach when relevant "
    "(e.g. 'for order-status questions, call the order_status tool and quote the status + ETA'). "
    "Do NOT output vague platitudes like 'be concise' or 'be helpful'. "
    "Return at most {limit} lessons, each for a distinct situation."
)


@dataclass
class DistillationResult:
    lessons: list[Lesson] = field(default_factory=list)
    diff: PlaybookDiff = field(default_factory=PlaybookDiff)

    @property
    def n_exemplars(self) -> int:
        return sum(1 for l in self.lessons if l.lesson_type is LessonType.EXEMPLAR)

    @property
    def n_directives(self) -> int:
        return sum(1 for l in self.lessons if l.lesson_type is LessonType.DIRECTIVE)

    @property
    def n_failure(self) -> int:
        return sum(1 for l in self.lessons if l.lesson_type is LessonType.FAILURE_PATTERN)

    # kept for back-compat with earlier callers/tests
    @property
    def n_success(self) -> int:
        return self.n_exemplars + self.n_directives


class Distiller:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        model: str,
        success_threshold: float = 0.7,
        failure_threshold: float = 0.4,
        max_lessons_per_bucket: int = 4,
        max_exemplars: int = 4,
        make_exemplars: bool = True,
    ) -> None:
        self._provider = provider
        self._model = model
        self._success_t = success_threshold
        self._failure_t = failure_threshold
        self._limit = max_lessons_per_bucket
        self._max_exemplars = max_exemplars
        self._make_exemplars = make_exemplars

    def distill(
        self,
        store: TrajectoryStore,
        *,
        generation: int = 0,
        episode_ids: list[str] | None = None,
    ) -> DistillationResult:
        """Bucket scored episodes, cluster, mine lessons, build an attributable diff."""
        episodes = (
            [store.get_episode(eid) for eid in episode_ids]
            if episode_ids is not None
            else store.query()
        )
        success: list[tuple[Episode, float]] = []
        failure: list[Episode] = []
        for ep in episodes:
            fused = store.fused_reward(ep.episode_id)
            if fused is None:
                continue
            reward, _ = fused
            if reward >= self._success_t:
                success.append((ep, reward))
            elif reward <= self._failure_t:
                failure.append(ep)

        lessons: list[Lesson] = []
        # 1) directives from successes (generalized, mined per situation cluster)
        lessons += self._mine_directives([e for e, _ in success], generation=generation)
        # 2) exemplars from the strongest successes (concrete, imitable)
        if self._make_exemplars:
            lessons += self._exemplars(success, generation=generation)
        # 3) failure-pattern warnings
        lessons += self._mine_failures(failure, generation=generation)

        return DistillationResult(lessons=lessons, diff=_to_diff(lessons))

    # -- directives (mined, clustered) -----------------------------------

    def _mine_directives(self, episodes: list[Episode], *, generation: int) -> list[Lesson]:
        if not episodes:
            return []
        out: list[Lesson] = []
        for cluster in _cluster_by_situation(episodes):
            out += self._mine_one(cluster, bucket="successful", failure=False,
                                  generation=generation)
        return out[: self._limit]

    def _mine_failures(self, episodes: list[Episode], *, generation: int) -> list[Lesson]:
        if not episodes:
            return []
        return self._mine_one(episodes, bucket="failed", failure=True, generation=generation)

    def _mine_one(self, episodes: list[Episode], *, bucket: str, failure: bool,
                  generation: int) -> list[Lesson]:
        examples = "\n\n".join(_format_example(ep) for ep in episodes[:8])
        messages = [
            {"role": "system",
             "content": _DIRECTIVE_PROMPT.format(bucket=bucket, limit=self._limit)},
            {"role": "user", "content": examples},
        ]
        result = self._provider.complete(model=self._model, messages=messages)
        data = _parse_json(result.text)
        ltype = LessonType.FAILURE_PATTERN if failure else LessonType.DIRECTIVE
        reward = 0.2 if failure else 0.85
        out: list[Lesson] = []
        for item in data.get("lessons", [])[: self._limit]:
            situation = str(item.get("situation", "")).strip()
            text = str(item.get("lesson", "")).strip()
            if not text or _is_generic(text):
                continue
            out.append(Lesson(content=text, lesson_type=ltype,
                              situation=situation or text, reward=reward,
                              generation=generation))
        return out

    # -- exemplars (concrete, no LLM call needed) ------------------------

    def _exemplars(self, success: list[tuple[Episode, float]], *, generation: int) -> list[Lesson]:
        """Turn the strongest successes into concrete situation→answer exemplars.

        Deterministic (no LLM): the best real answers ARE the best teaching material.
        """
        ranked = sorted(success, key=lambda t: t[1], reverse=True)[: self._max_exemplars]
        out: list[Lesson] = []
        seen: set[str] = set()
        for ep, reward in ranked:
            if not ep.final_output:
                continue
            situation = ep.task_input.strip()
            key = situation.lower()
            if key in seen:
                continue
            seen.add(key)
            content = f"Q: {situation}\nA: {ep.final_output.strip()}"
            out.append(Lesson(content=content, lesson_type=LessonType.EXEMPLAR,
                              situation=situation, reward=reward, generation=generation))
        return out


def _to_diff(lessons: list[Lesson]) -> PlaybookDiff:
    diff = PlaybookDiff()
    for l in lessons:
        if l.lesson_type is LessonType.FAILURE_PATTERN:
            diff.add_watch_out.append(l.content)
        elif l.lesson_type is LessonType.EXEMPLAR:
            diff.add_exemplars.append(l.content)
        else:
            diff.add_directives.append(l.content)
        diff.provenance.setdefault(l.content, []).append(l.lesson_id)
    return diff


# ─── helpers ────────────────────────────────────────────────────────────────

def _format_example(ep: Episode) -> str:
    """Task + tools used + answer — richer than task+answer so lessons stay specific."""
    tools = [
        s.tool_name
        for turn in ep.turns
        for s in turn.steps
        if s.type is StepType.TOOL_CALL and s.tool_name
    ]
    tool_line = f"\nTools used: {', '.join(tools)}" if tools else ""
    return f"Task: {ep.task_input}{tool_line}\nAnswer: {ep.final_output or '(none)'}"


def _cluster_by_situation(episodes: list[Episode]) -> list[list[Episode]]:
    """Group episodes by a coarse situation key (first tool used, else first keyword).

    Keeps mined lessons situation-specific instead of averaged across everything.
    Lightweight + deterministic; a semantic-embedding cluster can replace it later.
    """
    clusters: dict[str, list[Episode]] = {}
    for ep in episodes:
        key = _situation_key(ep)
        clusters.setdefault(key, []).append(ep)
    return list(clusters.values())


def _situation_key(ep: Episode) -> str:
    for turn in ep.turns:
        for s in turn.steps:
            if s.type is StepType.TOOL_CALL and s.tool_name:
                return f"tool:{s.tool_name}"
    words = [w.lower().strip("?.,") for w in ep.task_input.split() if len(w) > 3]
    return f"kw:{words[0]}" if words else "kw:_"


_GENERIC = re.compile(
    r"^\W*(be |provide |give |ensure |make sure |always be |try to )?"
    r"(concise|clear|helpful|polite|accurate|direct|brief|professional|friendly)\W*$",
    re.IGNORECASE,
)


def _is_generic(text: str) -> bool:
    """Reject vague platitudes that don't change behavior."""
    return bool(_GENERIC.match(text.strip()))


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
