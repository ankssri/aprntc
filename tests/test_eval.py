"""Stage 4 tests — judge (recusal, order de-bias, JSON parse), outcome scorers,
health metrics, and fusion through the store."""

import pytest

from aprntc.demos.corpus import GOLD
from aprntc.eval import (
    PairwiseJudge,
    judge_reference_agreement,
    rag_outcome,
    reward_hacking_alarm,
    support_outcome,
)
from aprntc.eval.health import AgreementReport
from aprntc.providers.base import CompletionResult
from aprntc.trajectory import (
    Collector,
    ContentPart,
    Episode,
    Label,
    LabelSource,
    Step,
    StepType,
    TrajectoryStore,
    Turn,
)


class JudgeProvider:
    """Returns a scripted JSON verdict; records the model it was called with."""

    def __init__(self, payload: str):
        self._payload = payload
        self.model_used = None

    def complete(self, *, model, messages, **kwargs) -> CompletionResult:
        self.model_used = model
        return CompletionResult(text=self._payload)


# ─── judge: recusal + order de-bias + parsing ───────────────────────────────

def test_judge_requires_recusal():
    with pytest.raises(ValueError):
        PairwiseJudge(JudgeProvider("{}"), judge_model="m", policy_model="m")


def test_judge_uses_judge_model_not_policy():
    p = JudgeProvider('{"winner":"A","child_score":0.8,"rationale":"good"}')
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    j.compare(task="q", child_answer="c", parent_answer="p", child_is_a=True)
    assert p.model_used == "ep-judge"


def test_judge_winner_demap_child_as_a():
    p = JudgeProvider('{"winner":"A","child_score":0.9,"rationale":"x"}')
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    v = j.compare(task="q", child_answer="c", parent_answer="p", child_is_a=True)
    assert v.winner == "child" and v.child_score == 0.9


def test_judge_winner_demap_child_as_b():
    # winner "A" but child was in slot B → parent wins (position de-biased)
    p = JudgeProvider('{"winner":"A","child_score":0.2,"rationale":"x"}')
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    v = j.compare(task="q", child_answer="c", parent_answer="p", child_is_a=False)
    assert v.winner == "parent"


def test_judge_tie_and_messy_json():
    p = JudgeProvider('thinking... {"winner":"tie","child_score":0.5,"rationale":"eq"} done')
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    v = j.compare(task="q", child_answer="c", parent_answer="p")
    assert v.winner == "tie" and v.child_score == 0.5


def test_judge_score_clamped_on_garbage():
    p = JudgeProvider("not json at all")
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    v = j.compare(task="q", child_answer="c", parent_answer="p")
    assert 0.0 <= v.child_score <= 1.0  # defaults safely


def test_judge_label_is_judge_source():
    p = JudgeProvider('{"winner":"A","child_score":0.7,"rationale":"r"}')
    j = PairwiseJudge(p, judge_model="ep-judge", policy_model="ep-policy")
    v = j.compare(task="q", child_answer="c", parent_answer="p")
    lbl = j.label(v, confidence=0.4)
    assert lbl.source is LabelSource.JUDGE and lbl.judge_model == "ep-judge"
    assert lbl.score == 0.7


# ─── outcome scorers (the anchor) ───────────────────────────────────────────

def _support_ep(answer: str, *, grounded: bool) -> Episode:
    turn = Turn(turn_index=0)
    if grounded:
        turn.steps.append(Step(step_index=0, type=StepType.TOOL_CALL,
                               tool_name="kb_lookup", tool_result="some policy"))
    return Episode(task_input="q", collector=Collector.SDK_WRAPPER,
                   final_output=answer, turns=[turn])


def test_support_outcome_resolved():
    lbl = support_outcome(_support_ep("Refunds within 30 days.", grounded=True))
    assert lbl.source is LabelSource.OUTCOME and lbl.score == 1.0


def test_support_outcome_punt_is_zero():
    lbl = support_outcome(_support_ep("I don't know.", grounded=True))
    assert lbl.score == 0.0


def test_support_outcome_ungrounded_is_zero():
    lbl = support_outcome(_support_ep("Refunds within 30 days.", grounded=False))
    assert lbl.score == 0.0


def _rag_ep(answer: str, retrieved: list[str]) -> Episode:
    turn = Turn(turn_index=0, steps=[
        Step(step_index=0, type=StepType.TOOL_CALL, tool_name="search_docs",
             tool_result={"doc_ids": retrieved})
    ])
    return Episode(task_input="q", collector=Collector.SDK_WRAPPER,
                   final_output=answer, turns=[turn])


def test_rag_outcome_perfect():
    gold = GOLD[0]  # "How old is the Sun?" -> doc_solar, "About 4.6 billion years old."
    ep = _rag_ep("The Sun is about 4.6 billion years old. [doc_solar]", ["doc_solar"])
    lbl = rag_outcome(ep, gold)
    assert lbl.source is LabelSource.OUTCOME and lbl.score == pytest.approx(1.0)


def test_rag_outcome_hallucinated_no_citation_low():
    gold = GOLD[0]
    ep = _rag_ep("It is very very old indeed.", [])
    lbl = rag_outcome(ep, gold)
    assert lbl.score < 0.5  # no citation, no retrieval, weak match


# ─── health metrics ─────────────────────────────────────────────────────────

def test_agreement_high_passes():
    rep = judge_reference_agreement([0.9, 0.1, 0.8], [1.0, 0.0, 0.7])
    assert isinstance(rep, AgreementReport)
    assert rep.agreement == pytest.approx(1.0) and rep.pass_threshold


def test_agreement_low_fails_threshold():
    rep = judge_reference_agreement([0.9, 0.9, 0.9, 0.9], [0.0, 0.0, 0.0, 1.0])
    assert rep.agreement == pytest.approx(0.25) and not rep.pass_threshold


def test_agreement_length_mismatch_raises():
    with pytest.raises(ValueError):
        judge_reference_agreement([0.5], [0.5, 0.6])


def test_reward_hacking_alarm_fires_and_clears():
    assert reward_hacking_alarm(judge_delta=0.2, outcome_delta=0.0) is True   # judge↑ outcome flat
    assert reward_hacking_alarm(judge_delta=0.2, outcome_delta=0.2) is False  # both up = healthy
    assert reward_hacking_alarm(judge_delta=0.01, outcome_delta=0.0) is False # judge barely moved


# ─── fusion through the store (anchor outranks judge) ────────────────────────

def test_fused_reward_anchored_by_outcome(tmp_path):
    store = TrajectoryStore(":memory:")
    try:
        ep = Episode(task_input="q", collector=Collector.SDK_WRAPPER)
        eid = store.put_episode(ep, scrub=False)
        # judge loves it, outcome says it failed → fused reward stays low-ish, anchored
        store.attach_label(eid, Label(source=LabelSource.JUDGE, score=1.0, confidence=0.5))
        store.attach_label(eid, Label(source=LabelSource.OUTCOME, score=0.0, confidence=0.9))
        reward, conf = store.fused_reward(eid)
        assert reward < 0.5            # outcome (higher weight) pulls it down
        assert conf == 1.0             # confidence anchored by outcome source
    finally:
        store.close()
