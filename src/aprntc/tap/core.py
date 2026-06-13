"""Tap core: AgentTap + recorders that build canonical Trajectories.

``AgentTap`` is the entry point a collector (or an instrumented agent) uses to
record an episode. Recorders accumulate turns/steps and, on finish, normalize
into an :class:`~aprntc.trajectory.schema.Episode` and hand it to a **sink**
(typically ``TrajectoryStore.put_episode``).

**Fail-open invariant (CLAUDE.md):** nothing the tap does may break the parent
agent. The sink is called inside a guard; a sink error is swallowed (optionally
reported via ``on_error``) rather than propagated. Recording is also the *only*
side effect — recorders never alter the values flowing through the agent.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from aprntc.trajectory.schema import (
    Collector,
    ContentPart,
    Episode,
    PiiStatus,
    Step,
    StepType,
    Turn,
)

# A sink receives a finished Episode (e.g. store.put_episode). Returns anything.
Sink = Callable[[Episode], Any]
ErrorHandler = Callable[[BaseException], None]


class AgentTap:
    """Factory for episode recorders, bound to a sink and a collector identity."""

    def __init__(
        self,
        sink: Sink,
        *,
        collector: Collector = Collector.SDK_WRAPPER,
        on_error: ErrorHandler | None = None,
    ) -> None:
        self._sink = sink
        self._collector = collector
        self._on_error = on_error

    def start_episode(
        self,
        task_input: str,
        *,
        trace_id: str | None = None,
        generation_id: str | None = None,
        model_id: str | None = None,
        input_context: list[str] | None = None,
    ) -> "EpisodeRecorder":
        """Begin recording a task. Call ``.finish()`` (or use as a context manager)."""
        episode = Episode(
            task_input=task_input,
            collector=self._collector,
            trace_id=trace_id,
            generation_id=generation_id,
            model_id=model_id,
            input_context=list(input_context or []),
            pii_status=PiiStatus.RAW,
        )
        return EpisodeRecorder(episode, self._sink, on_error=self._on_error)

    def _emit(self, episode: Episode) -> None:
        """Fail-open emit: a sink error never escapes to the parent agent."""
        try:
            self._sink(episode)
        except BaseException as exc:  # noqa: BLE001 - fail-open is the whole point
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except BaseException:
                    pass


class EpisodeRecorder:
    """Accumulates turns for one episode, then normalizes + emits it."""

    def __init__(
        self,
        episode: Episode,
        sink: Sink,
        *,
        on_error: ErrorHandler | None = None,
    ) -> None:
        self.episode = episode
        self._sink = sink
        self._on_error = on_error
        self._finished = False
        self._start = time.perf_counter()

    def turn(self, user_text: str | None = None) -> "TurnRecorder":
        """Open a new turn. Optionally seed it with the user's text."""
        tr = TurnRecorder(turn_index=len(self.episode.turns))
        if user_text is not None:
            tr.add_user_text(user_text)
        self.episode.add_turn(tr.turn)
        return tr

    def finish(
        self,
        *,
        final_output: str | None = None,
        partial: bool = False,
    ) -> Episode:
        """Stamp metrics, emit the episode (fail-open), and return it."""
        if self._finished:
            raise RuntimeError("episode already finished")
        self.episode.ts_end = _now_iso()
        if final_output is not None:
            self.episode.final_output = final_output
        if partial:
            self.episode.partial = True
        if self.episode.latency_ms is None:
            self.episode.latency_ms = (time.perf_counter() - self._start) * 1000
        self._emit()
        self._finished = True
        return self.episode

    def _emit(self) -> None:
        try:
            self._sink(self.episode)
        except BaseException as exc:  # noqa: BLE001 - fail-open
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except BaseException:
                    pass

    # context manager: a leaking exception → record a partial episode, never raise
    def __enter__(self) -> "EpisodeRecorder":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if not self._finished:
            self.finish(partial=exc is not None)
        return False  # never suppress the agent's own exceptions


class TurnRecorder:
    """Accumulates content + steps for a single turn."""

    def __init__(self, turn_index: int) -> None:
        self.turn = Turn(turn_index=turn_index)

    # -- content ---------------------------------------------------------
    def add_user_text(self, text: str) -> "TurnRecorder":
        self.turn.user_content.append(ContentPart.text_part(text))
        return self

    def add_user_content(self, part: ContentPart) -> "TurnRecorder":
        self.turn.user_content.append(part)
        return self

    def add_agent_text(self, text: str) -> "TurnRecorder":
        self.turn.agent_content.append(ContentPart.text_part(text))
        return self

    def add_agent_content(self, part: ContentPart) -> "TurnRecorder":
        self.turn.agent_content.append(part)
        return self

    def set_reasoning(self, reasoning: str | None) -> "TurnRecorder":
        self.turn.reasoning_content = reasoning
        return self

    def mark_partial(self) -> "TurnRecorder":
        self.turn.partial = True
        return self

    # -- steps -----------------------------------------------------------
    def record_step(
        self,
        type: StepType | str,
        *,
        tool_name: str | None = None,
        tool_args: Any | None = None,
        tool_result: Any | None = None,
        duration_ms: float | None = None,
        tokens: int | None = None,
        error: str | None = None,
        source_fidelity: str = "full",
    ) -> Step:
        step = Step(
            step_index=len(self.turn.steps),
            type=type,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            duration_ms=duration_ms,
            tokens=tokens,
            error=error,
            source_fidelity=source_fidelity,
        )
        self.turn.steps.append(step)
        return step


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
