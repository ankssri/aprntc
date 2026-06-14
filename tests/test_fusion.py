"""A3 learned fusion weights — calibrate sources by agreement with the anchor."""

import pytest

from aprntc.eval.fusion import FusionWeights, learn_weights
from aprntc.trajectory import (
    Collector,
    Episode,
    Label,
    LabelSource,
    TrajectoryStore,
)


def _labels(*pairs) -> list[Label]:
    return [Label(source=s, score=v, confidence=0.9) for s, v in pairs]


# ─── learn_weights ───────────────────────────────────────────────────────────

def test_cold_start_falls_back_to_priors():
    # too few samples → priors unchanged
    fw = learn_weights([_labels((LabelSource.OUTCOME, 1.0), (LabelSource.JUDGE, 0.0))], min_n=5)
    assert fw.weights[LabelSource.JUDGE] == pytest.approx(0.4)  # prior, not down-weighted yet


def test_judge_agreeing_with_outcome_keeps_trust():
    # judge tracks the outcome anchor across many episodes → weight stays ~prior
    eps = [_labels((LabelSource.OUTCOME, 1.0), (LabelSource.JUDGE, 1.0)) for _ in range(10)]
    fw = learn_weights(eps, min_n=5, blend=1.0)  # blend=1 → fully data-driven
    # agreement ~1.0 → learned ~ prior*1.0
    assert fw.weights[LabelSource.JUDGE] == pytest.approx(0.4, abs=0.05)
    assert fw.report[LabelSource.JUDGE].agreement == pytest.approx(1.0)


def test_judge_disagreeing_with_outcome_is_downweighted():
    # judge says 1.0 but the outcome anchor says 0.0 every time → heavy down-weight
    eps = [_labels((LabelSource.OUTCOME, 0.0), (LabelSource.JUDGE, 1.0)) for _ in range(10)]
    fw = learn_weights(eps, min_n=5, blend=1.0)
    assert fw.weights[LabelSource.JUDGE] < 0.1   # agreement ~0 → near-zero weight
    assert fw.report[LabelSource.JUDGE].agreement == pytest.approx(0.0)


def test_blend_moderates_the_adjustment():
    eps = [_labels((LabelSource.OUTCOME, 0.0), (LabelSource.JUDGE, 1.0)) for _ in range(10)]
    full = learn_weights(eps, min_n=5, blend=1.0).weights[LabelSource.JUDGE]
    half = learn_weights(eps, min_n=5, blend=0.5).weights[LabelSource.JUDGE]
    # blend=0.5 stays closer to the prior than blend=1.0
    assert full < half < 0.4


def test_anchor_sources_keep_priors():
    eps = [_labels((LabelSource.OUTCOME, 1.0), (LabelSource.USER_EXPLICIT, 0.0)) for _ in range(10)]
    fw = learn_weights(eps, min_n=5, blend=1.0)
    # outcome is an anchor → never re-weighted against itself
    assert fw.weights[LabelSource.OUTCOME] == pytest.approx(1.0)


def test_explicit_feedback_used_as_anchor_when_no_outcome():
    # no outcome present → user_explicit becomes the anchor; judge calibrated to it
    eps = [_labels((LabelSource.USER_EXPLICIT, 0.0), (LabelSource.JUDGE, 1.0)) for _ in range(8)]
    fw = learn_weights(eps, min_n=5, blend=1.0)
    assert fw.weights[LabelSource.JUDGE] < 0.1


def test_summary_renders():
    fw = learn_weights([_labels((LabelSource.OUTCOME, 1.0), (LabelSource.JUDGE, 1.0))] * 6)
    assert "judge" in fw.summary() and "w=" in fw.summary()


# ─── integration with the store ──────────────────────────────────────────────

@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


def _ep(store, *label_pairs) -> str:
    ep = Episode(task_input="q", collector=Collector.SDK_WRAPPER, final_output="a")
    eid = store.put_episode(ep, scrub=False)
    for src, val in label_pairs:
        store.attach_label(eid, Label(source=src, score=val, confidence=0.9))
    return eid


def test_store_learn_and_apply_weights_changes_fusion(store):
    # history: judge consistently contradicts the outcome anchor
    for _ in range(8):
        _ep(store, (LabelSource.OUTCOME, 0.0), (LabelSource.JUDGE, 1.0))
    # a NEW episode with only a (bad) judge label + a strong explicit downvote-ish signal
    target = _ep(store, (LabelSource.JUDGE, 1.0), (LabelSource.USER_EXPLICIT, 0.0))

    default = store.fused_reward(target)[0]
    learned = store.learn_fusion_weights(min_n=5, blend=1.0)
    adjusted = store.fused_reward(target, weights=learned.as_map())[0]

    # with the judge down-weighted, the explicit-downvote dominates → lower reward
    assert adjusted < default
    assert learned.weights[LabelSource.JUDGE] < 0.4


def test_store_fused_reward_default_unchanged_without_weights(store):
    eid = _ep(store, (LabelSource.OUTCOME, 1.0), (LabelSource.JUDGE, 0.0))
    # default path still works (no weights arg)
    r, c = store.fused_reward(eid)
    assert 0.0 <= r <= 1.0 and c == pytest.approx(1.0)
