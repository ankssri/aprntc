"""Tap core + SDK wrapper tests — recording flow, fail-open, full-fidelity capture."""

import pytest

from aprntc.providers.base import CompletionResult, LLMProvider
from aprntc.tap import AgentTap, wrap
from aprntc.tap.core import EpisodeRecorder
from aprntc.trajectory import Collector, Episode, SourceFidelity, StepType, TrajectoryStore


# ─── fakes ──────────────────────────────────────────────────────────────────

class FakeProvider:
    """An LLMProvider stand-in with scriptable result / error."""

    def __init__(self, result: CompletionResult | None = None, error: Exception | None = None):
        self._result = result or CompletionResult(text="hi", usage={"total_tokens": 7})
        self._error = error
        self.calls = 0

    def complete(self, *, model, messages, **kwargs) -> CompletionResult:
        self.calls += 1
        if self._error:
            raise self._error
        return self._result


def _collecting_tap():
    captured: list[Episode] = []
    return AgentTap(captured.append, collector=Collector.SDK_WRAPPER), captured


# ─── recorder flow ──────────────────────────────────────────────────────────

def test_basic_episode_records_turns_and_emits():
    tap, captured = _collecting_tap()
    rec = tap.start_episode("do a thing", trace_id="t1")
    t = rec.turn(user_text="hello")
    t.add_agent_text("hi there")
    rec.finish(final_output="hi there")

    assert len(captured) == 1
    ep = captured[0]
    assert ep.task_input == "do a thing" and ep.trace_id == "t1"
    assert ep.collector is Collector.SDK_WRAPPER
    assert ep.final_output == "hi there"
    assert ep.latency_ms is not None and ep.ts_end is not None
    assert ep.turns[0].user_content[0].text == "hello"
    assert ep.turns[0].agent_content[0].text == "hi there"


def test_double_finish_raises():
    tap, _ = _collecting_tap()
    rec = tap.start_episode("x")
    rec.finish()
    with pytest.raises(RuntimeError):
        rec.finish()


def test_context_manager_emits_on_exit():
    tap, captured = _collecting_tap()
    with tap.start_episode("x") as rec:
        rec.turn(user_text="q")
    assert len(captured) == 1 and captured[0].partial is False


def test_context_manager_marks_partial_on_exception():
    tap, captured = _collecting_tap()
    with pytest.raises(ValueError):
        with tap.start_episode("x") as rec:
            rec.turn(user_text="q")
            raise ValueError("boom")
    assert len(captured) == 1 and captured[0].partial is True


def test_steps_recorded_with_fidelity():
    tap, captured = _collecting_tap()
    rec = tap.start_episode("x")
    t = rec.turn()
    t.record_step(StepType.TOOL_CALL, tool_name="search", tool_args={"q": "a"},
                  source_fidelity="inferred")
    rec.finish()
    step = captured[0].turns[0].steps[0]
    assert step.tool_name == "search"
    assert step.source_fidelity is SourceFidelity.INFERRED


# ─── fail-open invariant ────────────────────────────────────────────────────

def test_sink_error_does_not_propagate():
    errors = []
    def bad_sink(_ep):
        raise RuntimeError("store down")
    tap = AgentTap(bad_sink, on_error=errors.append)
    rec = tap.start_episode("x")
    rec.turn(user_text="q")
    # finish must NOT raise even though the sink throws (fail-open)
    ep = rec.finish()
    assert isinstance(ep, Episode)
    assert len(errors) == 1 and isinstance(errors[0], RuntimeError)


# ─── SDK wrapper collector ──────────────────────────────────────────────────

def test_wrap_is_runtime_llmprovider():
    wrapped = wrap(FakeProvider(), turn_provider=lambda: None)
    assert isinstance(wrapped, LLMProvider)


def test_wrap_records_model_call_into_active_turn():
    tap, captured = _collecting_tap()
    rec = tap.start_episode("ask")
    t = rec.turn(user_text="q")
    provider = wrap(
        FakeProvider(CompletionResult(text="ans", reasoning_content="thinking",
                                      tool_calls=[{"id": "1"}], usage={"total_tokens": 9})),
        turn_provider=lambda: t,
    )
    out = provider.complete(model="ep-seed", messages=[{"role": "user", "content": "q"}])
    rec.finish(final_output=out.text)

    step = captured[0].turns[0].steps[0]
    assert step.type is StepType.MODEL_CALL
    assert step.tool_name == "ep-seed"
    assert step.tokens == 9
    assert step.source_fidelity is SourceFidelity.FULL
    assert step.tool_result["text"] == "ans"
    # reasoning surfaced on the turn, separate from the answer
    assert captured[0].turns[0].reasoning_content == "thinking"


def test_wrap_returns_result_unchanged():
    res = CompletionResult(text="unchanged", usage={"total_tokens": 3})
    provider = wrap(FakeProvider(res), turn_provider=lambda: None)
    out = provider.complete(model="m", messages=[])
    assert out is res  # transparent passthrough


def test_wrap_records_error_and_reraises():
    tap, captured = _collecting_tap()
    rec = tap.start_episode("ask")
    t = rec.turn()
    provider = wrap(FakeProvider(error=ValueError("api 500")), turn_provider=lambda: t)
    with pytest.raises(ValueError):
        provider.complete(model="m", messages=[])
    rec.finish(partial=True)
    step = captured[0].turns[0].steps[0]
    assert step.error and "api 500" in step.error


def test_wrap_recording_failure_does_not_break_call():
    # turn_provider explodes → call must still return normally (fail-open)
    def boom():
        raise RuntimeError("resolver broke")
    provider = wrap(FakeProvider(CompletionResult(text="ok")), turn_provider=boom)
    out = provider.complete(model="m", messages=[])
    assert out.text == "ok"


# ─── end-to-end with the real store ─────────────────────────────────────────

def test_tap_into_real_store_scrubs_pii():
    store = TrajectoryStore(":memory:")
    try:
        tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
        rec = tap.start_episode("contact me at a@b.com")
        rec.turn(user_text="my email a@b.com")
        ep = rec.finish()
        stored = store.get_episode(ep.episode_id)
        # scrub-at-ingest happened through the store sink
        assert "a@b.com" not in stored.task_input
        assert "a@b.com" not in stored.turns[0].user_content[0].text
    finally:
        store.close()
