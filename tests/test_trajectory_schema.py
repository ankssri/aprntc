"""Trajectory schema tests (ADR 0007): round-trip + every edge case it must absorb."""

import pytest

from aprntc.trajectory import (
    SCHEMA_VERSION,
    Collector,
    ContentPart,
    ContentType,
    Episode,
    Label,
    LabelSource,
    Outcome,
    PiiStatus,
    SourceFidelity,
    Step,
    StepType,
    Turn,
)


# ─── ContentPart ────────────────────────────────────────────────────────────

def test_text_part_requires_text():
    with pytest.raises(ValueError):
        ContentPart(type=ContentType.TEXT)


def test_media_part_requires_ref_not_inline():
    # media must be by reference (ADR 0007 privacy-by-shape)
    with pytest.raises(ValueError):
        ContentPart(type=ContentType.IMAGE)
    ok = ContentPart(type=ContentType.IMAGE, ref="https://x/y.png", mime="image/png")
    assert ok.ref and ok.text is None


def test_content_part_roundtrip():
    for part in (
        ContentPart.text_part("hello"),
        ContentPart(type=ContentType.VIDEO, ref="hash:abc", mime="video/mp4"),
        ContentPart(type=ContentType.FILE, ref="https://x/doc.pdf"),
    ):
        assert ContentPart.from_dict(part.to_dict()) == part


# ─── Step (fidelity / missing-per-source) ───────────────────────────────────

def test_step_defaults_to_full_fidelity():
    s = Step(step_index=0, type=StepType.MODEL_CALL)
    assert s.source_fidelity is SourceFidelity.FULL


def test_step_inferred_with_missing_fields_is_valid():
    # proxy collector: knows tool name+args from the call loop, not timing/result
    s = Step(step_index=1, type=StepType.TOOL_CALL, tool_name="search",
             tool_args={"q": "x"}, source_fidelity="inferred")
    assert s.duration_ms is None and s.tool_result is None
    assert s.source_fidelity is SourceFidelity.INFERRED
    assert Step.from_dict(s.to_dict()) == s


def test_step_roundtrip_full():
    s = Step(step_index=2, type=StepType.TOOL_RESULT, tool_name="db",
             tool_result={"rows": 3}, duration_ms=12.5, tokens=8, error=None)
    assert Step.from_dict(s.to_dict()) == s


# ─── Turn (reasoning, multimodal, partial) ──────────────────────────────────

def test_turn_with_reasoning_and_multimodal():
    t = Turn(
        turn_index=0,
        user_content=[ContentPart.text_part("describe"),
                      ContentPart(type=ContentType.IMAGE, ref="hash:img1")],
        agent_content=[ContentPart.text_part("a planet")],
        reasoning_content="the user wants a description...",
        steps=[Step(step_index=0, type=StepType.MODEL_CALL)],
    )
    restored = Turn.from_dict(t.to_dict())
    assert restored == t
    assert restored.reasoning_content == "the user wants a description..."
    assert restored.user_content[1].type is ContentType.IMAGE


def test_partial_turn_flag_roundtrips():
    t = Turn(turn_index=0, partial=True)
    assert Turn.from_dict(t.to_dict()).partial is True


# ─── Label & Outcome ────────────────────────────────────────────────────────

@pytest.mark.parametrize("score", [-0.1, 1.1])
def test_label_score_out_of_range_rejected(score):
    with pytest.raises(ValueError):
        Label(source=LabelSource.JUDGE, score=score)


def test_label_roundtrip_and_coercion():
    lbl = Label(source="judge", score=0.8, rubric_dim="helpfulness",
                confidence=0.6, judge_model="deepseek-v4-pro")
    assert lbl.source is LabelSource.JUDGE
    assert Label.from_dict(lbl.to_dict()) == lbl


def test_outcome_roundtrip():
    o = Outcome(trace_id="t1", resolved=True, correct=True, downstream_metric=0.9)
    assert Outcome.from_dict(o.to_dict()) == o


# ─── Episode (the unit of learning) ─────────────────────────────────────────

def test_episode_requires_task_input():
    with pytest.raises(ValueError):
        Episode(task_input="  ", collector=Collector.SDK_WRAPPER)


def test_episode_defaults():
    e = Episode(task_input="do a thing", collector="sdk_wrapper")
    assert e.episode_id.startswith("ep_")
    assert e.schema_version == SCHEMA_VERSION
    assert e.collector is Collector.SDK_WRAPPER
    assert e.pii_status is PiiStatus.RAW
    assert e.partial is False
    assert e.turns == [] and e.labels == [] and e.outcome is None


def test_episode_full_roundtrip_all_edge_cases():
    e = Episode(
        task_input="multi-turn multimodal reasoning task",
        collector=Collector.OTEL,
        trace_id="trace-123",
        generation_id="G1",
        agent_artifact_hash="sha:deadbeef",
        input_context=["exp_1", "exp_2"],
        model_id="ep-seed-2-0-pro",
        pii_status="scrubbed",
        partial=True,
        turns=[
            Turn(
                turn_index=0,
                user_content=[ContentPart.text_part("q1"),
                              ContentPart(type=ContentType.FILE, ref="hash:doc", mime="application/pdf")],
                agent_content=[ContentPart.text_part("a1")],
                reasoning_content="thinking…",
                steps=[
                    Step(step_index=0, type=StepType.TOOL_CALL, tool_name="search",
                         tool_args={"q": "x"}, source_fidelity="inferred"),
                    Step(step_index=1, type=StepType.TOOL_RESULT, tool_result={"hits": 2},
                         duration_ms=33.0),
                ],
            ),
            Turn(turn_index=1, partial=True),
        ],
        final_output="done",
        latency_ms=1200.0, ttft_ms=210.0, tokens_in=500, tokens_out=120, cost_usd=0.003,
        labels=[
            Label(source=LabelSource.JUDGE, score=0.7, judge_model="deepseek-v4-pro"),
            Label(source=LabelSource.OUTCOME, score=1.0, confidence=0.9),
        ],
        outcome=Outcome(trace_id="trace-123", resolved=True, correct=True),
    )
    restored = Episode.from_dict(e.to_dict())
    assert restored.to_dict() == e.to_dict()
    # spot-check nested integrity
    assert restored.collector is Collector.OTEL
    assert restored.pii_status is PiiStatus.SCRUBBED
    assert restored.partial is True
    assert len(restored.turns) == 2
    assert restored.turns[0].steps[0].source_fidelity is SourceFidelity.INFERRED
    assert restored.turns[1].partial is True
    assert len(restored.labels) == 2
    assert restored.outcome.resolved is True


def test_episode_minimal_roundtrip():
    # leanest possible (e.g. a partial proxy capture) still round-trips
    e = Episode(task_input="q", collector=Collector.EGRESS_PROXY)
    assert Episode.from_dict(e.to_dict()).to_dict() == e.to_dict()


def test_to_dict_omits_none_fields():
    e = Episode(task_input="q", collector=Collector.MCP)
    d = e.to_dict()
    # optional unset fields are omitted, not serialized as null
    assert "final_output" not in d and "trace_id" not in d and "outcome" not in d


def test_invalid_enum_values_rejected():
    with pytest.raises(ValueError):
        Episode(task_input="q", collector="not_a_collector")
    with pytest.raises(ValueError):
        Step(step_index=0, type="not_a_step")


def test_add_turn_and_label_helpers():
    e = Episode(task_input="q", collector=Collector.SDK_WRAPPER)
    e.add_turn(Turn(turn_index=0))
    e.add_label(Label(source=LabelSource.HUMAN, score=0.5))
    assert len(e.turns) == 1 and len(e.labels) == 1
