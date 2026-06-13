"""SDK wrapper collector — the full-fidelity, our-code tap path (ADR 0004).

When we own the agent code, the richest capture is to wrap the model client so
every ``complete()`` call is recorded into the active turn as a ``model_call``
step with **full** fidelity (real messages, reasoning, tool_calls, tokens,
timing). One-line integration:

    provider = wrap(provider, turn_provider=lambda: recorder.current_turn)

The wrapper is transparent (returns the provider's result unchanged) and
**fail-open**: a recording error never affects the call's return value.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from aprntc.providers.base import CompletionResult, LLMProvider
from aprntc.tap.core import TurnRecorder
from aprntc.trajectory.schema import StepType

# Resolves the TurnRecorder a call should be recorded into (None → skip recording).
TurnResolver = Callable[[], "TurnRecorder | None"]


class _TappedProvider:
    """Transparent wrapper around an LLMProvider that records each completion."""

    def __init__(self, inner: LLMProvider, turn_provider: TurnResolver) -> None:
        self._inner = inner
        self._turn_provider = turn_provider

    def complete(self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> CompletionResult:
        start = time.perf_counter()
        error: str | None = None
        result: CompletionResult | None = None
        try:
            result = self._inner.complete(model=model, messages=messages, **kwargs)
            return result
        except BaseException as exc:  # record the failure, then re-raise unchanged
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._record(start, model, messages, result, error)

    def _record(
        self,
        start: float,
        model: str,
        messages: list[dict[str, Any]],
        result: CompletionResult | None,
        error: str | None,
    ) -> None:
        # Fail-open: never let recording affect the wrapped call.
        try:
            turn = self._turn_provider()
            if turn is None:
                return
            duration_ms = (time.perf_counter() - start) * 1000
            usage = result.usage if result else {}
            turn.record_step(
                StepType.MODEL_CALL,
                tool_name=model,
                tool_args={"messages": messages},
                tool_result=None if result is None else {
                    "text": result.text,
                    "tool_calls": result.tool_calls,
                },
                duration_ms=duration_ms,
                tokens=(usage or {}).get("total_tokens"),
                error=error,
                source_fidelity="full",
            )
            if result is not None and result.reasoning_content:
                # Surface the reasoning trace on the turn (separate from the answer).
                if turn.turn.reasoning_content is None:
                    turn.set_reasoning(result.reasoning_content)
        except BaseException:
            return  # swallow — recording must never break the agent

    # Delegate any other attribute access to the wrapped provider.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def wrap(provider: LLMProvider, *, turn_provider: TurnResolver) -> LLMProvider:
    """Wrap an LLMProvider so completions are tapped into the resolved turn.

    ``turn_provider`` returns the active :class:`TurnRecorder` (or ``None`` to
    skip). Returns an object that is API-compatible with the original provider.
    """
    return _TappedProvider(provider, turn_provider)
