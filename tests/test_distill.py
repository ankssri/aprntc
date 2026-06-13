"""Stage 6 tests — Playbook + attributable diff, Distiller, Child runtime."""

import pytest

from aprntc.distill import ChildAgent, Distiller, Playbook, PlaybookDiff
from aprntc.distill.distiller import DistillationResult
from aprntc.demos.agents import RagAgent, SupportAgent
from aprntc.memory.base import Lesson, LessonType, RetrievedLesson
from aprntc.providers.base import CompletionResult
from aprntc.tap import AgentTap
from aprntc.trajectory import (
    Collector,
    Episode,
    Label,
    LabelSource,
    StepType,
    TrajectoryStore,
    Turn,
)


# ─── Playbook + diff ────────────────────────────────────────────────────────

def test_playbook_render_includes_sections():
    pb = Playbook(system_prompt="You help.", directives=["cite docs"],
                  exemplars=["Q->A"], watch_out=["don't guess"])
    text = pb.render()
    assert "You help." in text
    assert "cite docs" in text and "Q->A" in text and "don't guess" in text


def test_playbook_hash_is_stable_and_content_addressed():
    a = Playbook(system_prompt="x", directives=["d"])
    b = Playbook(system_prompt="x", directives=["d"])
    c = Playbook(system_prompt="x", directives=["d", "e"])
    assert a.hash == b.hash and a.hash != c.hash
    assert a.hash.startswith("pb_")


def test_diff_apply_increments_generation_and_dedupes():
    base = Playbook(system_prompt="s", directives=["existing"])
    diff = PlaybookDiff(add_directives=["existing", "new rule"],
                        add_watch_out=["avoid X"])
    out = diff.apply(base)
    assert out.generation == 1
    assert out.directives == ["existing", "new rule"]   # dedup against existing
    assert out.watch_out == ["avoid X"]
    assert base.generation == 0                          # base unchanged


def test_diff_caps_change_per_generation():
    base = Playbook(system_prompt="s")
    diff = PlaybookDiff(add_directives=[f"d{i}" for i in range(10)])
    out = diff.apply(base, cap_per_kind=5)
    assert len(out.directives) == 5  # bounded change (forgetting guard)


def test_diff_revert_removes_attributed_items():
    base = Playbook(system_prompt="s")
    diff = PlaybookDiff(add_directives=["from L1", "from L2"],
                        provenance={"from L1": ["les_1"], "from L2": ["les_2"]})
    applied = diff.apply(base)
    reverted = diff.revert(applied, "les_1")
    assert "from L1" not in reverted.directives
    assert "from L2" in reverted.directives  # single-lesson rollback


def test_diff_is_empty():
    assert PlaybookDiff().is_empty()
    assert not PlaybookDiff(add_directives=["x"]).is_empty()


# ─── Distiller ──────────────────────────────────────────────────────────────

class MiningProvider:
    """Returns scripted lessons JSON regardless of bucket."""

    def __init__(self, success_lessons, failure_lessons):
        self._s = success_lessons
        self._f = failure_lessons
        self.calls = 0

    def complete(self, *, model, messages, **kwargs):
        self.calls += 1
        sys = messages[0]["content"]
        items = self._f if "failed" in sys else self._s
        import json
        return CompletionResult(text=json.dumps({"lessons": items}))


@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


def _scored_ep(store, task, answer, reward):
    ep = Episode(task_input=task, collector=Collector.SDK_WRAPPER, final_output=answer)
    eid = store.put_episode(ep, scrub=False)
    store.attach_label(eid, Label(source=LabelSource.OUTCOME, score=reward, confidence=0.9))
    return eid


def test_distiller_buckets_mines_and_exemplifies(store):
    _scored_ep(store, "refund?", "Refunds within 30 days with a receipt.", 0.9)   # success
    _scored_ep(store, "where order?", "no idea", 0.1)  # failure
    provider = MiningProvider(
        success_lessons=[{"situation": "refund q", "lesson": "ground refund answers in the KB refund_policy entry"}],
        failure_lessons=[{"situation": "order q", "lesson": "call order_status, don't guess"}],
    )
    distiller = Distiller(provider, model="ep-policy")
    res = distiller.distill(store, generation=1)

    assert isinstance(res, DistillationResult)
    # success → a directive AND a concrete exemplar; failure → a watch-out
    assert res.n_directives == 1 and res.n_exemplars == 1 and res.n_failure == 1
    assert res.n_success == 2  # back-compat: directives + exemplars
    assert "ground refund answers in the KB refund_policy entry" in res.diff.add_directives
    assert any("Refunds within 30 days" in e for e in res.diff.add_exemplars)  # the real answer, imitable
    assert "call order_status, don't guess" in res.diff.add_watch_out
    assert res.diff.provenance
    assert all(l.generation == 1 for l in res.lessons)


def test_distiller_drops_generic_platitudes(store):
    _scored_ep(store, "refund?", "Refunds within 30 days.", 0.9)
    provider = MiningProvider(
        success_lessons=[
            {"situation": "x", "lesson": "Be concise"},           # generic → dropped
            {"situation": "y", "lesson": "always be helpful"},    # generic → dropped
            {"situation": "refund", "lesson": "quote the exact 30-day refund window from the KB"},  # kept
        ],
        failure_lessons=[],
    )
    res = Distiller(provider, model="m", make_exemplars=False).distill(store)
    directives = res.diff.add_directives
    assert "quote the exact 30-day refund window from the KB" in directives
    assert not any(d.lower() in ("be concise", "always be helpful") for d in directives)


def test_distiller_exemplars_ranked_and_capped(store):
    for i, r in enumerate([0.95, 0.9, 0.85, 0.8, 0.75]):
        _scored_ep(store, f"q{i}", f"answer {i}", r)
    provider = MiningProvider(success_lessons=[], failure_lessons=[])
    res = Distiller(provider, model="m", max_exemplars=3).distill(store)
    assert res.n_exemplars == 3  # capped
    # the highest-reward answers were chosen (q0=0.95, q1=0.9, q2=0.85)
    joined = " ".join(res.diff.add_exemplars)
    assert "answer 0" in joined and "answer 1" in joined and "answer 4" not in joined


def test_distiller_skips_unlabeled_and_midrange(store):
    # unlabeled -> skipped; midrange (between thresholds) -> neither bucket
    store.put_episode(Episode(task_input="x", collector=Collector.SDK_WRAPPER), scrub=False)
    _scored_ep(store, "mid", "meh", 0.55)
    provider = MiningProvider(success_lessons=[], failure_lessons=[])
    res = Distiller(provider, model="m").distill(store)
    assert res.lessons == [] and res.diff.is_empty()


# ─── Child runtime ──────────────────────────────────────────────────────────

class FakeMemory:
    def __init__(self, lessons):
        self._lessons = lessons
        self.queried = None

    def upsert_lessons(self, lessons):  # pragma: no cover - not used here
        return len(lessons)

    def retrieve(self, *, query, k=4, min_reward=0.0, generation=None,
                 lesson_type=None, diversify=True):
        self.queried = query
        return [RetrievedLesson(lesson=l, score=0.9) for l in self._lessons[:k]]


def _provider_capturing():
    class P:
        last_messages = None
        def complete(self, *, model, messages, **kwargs):
            P.last_messages = messages
            return CompletionResult(text="child answer", usage={"total_tokens": 5})
    return P()


def test_child_uses_playbook_as_system_prompt(store):
    provider = _provider_capturing()
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    parent = SupportAgent(provider, tap, model="ep-policy")
    pb = Playbook(system_prompt="CHILD PROMPT", directives=["always cite"])
    child = ChildAgent(parent, pb)
    child.run("what is your refund policy?")
    sys_msg = provider.last_messages[0]["content"]
    assert "CHILD PROMPT" in sys_msg and "always cite" in sys_msg


def test_child_injects_retrieved_lessons_and_records_step(store):
    provider = _provider_capturing()
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    parent = RagAgent(provider, tap, model="ep-policy")
    mem = FakeMemory([Lesson(content="cite the doc id", lesson_type=LessonType.DIRECTIVE,
                             situation="factual q", reward=0.9)])
    child = ChildAgent(parent, Playbook(system_prompt="P"), memory=mem)
    res = child.run("How old is the Sun?")

    assert mem.queried == "How old is the Sun?"
    # lesson text injected into the model context
    assert "cite the doc id" in str(provider.last_messages)
    # a memory_retrieve step was recorded in the trajectory
    ep = store.get_episode(res.episode_id)
    assert any(s.tool_name == "memory_retrieve" for s in ep.turns[0].steps)


def test_child_without_memory_is_playbook_only(store):
    provider = _provider_capturing()
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    parent = SupportAgent(provider, tap, model="ep-policy")
    child = ChildAgent(parent, Playbook(system_prompt="P"), memory=None)
    res = child.run("refund policy?")  # must not error without memory
    ep = store.get_episode(res.episode_id)
    assert not any(s.tool_name == "memory_retrieve" for s in ep.turns[0].steps)


def test_child_memory_failure_does_not_break_run(store):
    class BoomMemory:
        def upsert_lessons(self, lessons): return 0
        def retrieve(self, **kwargs): raise RuntimeError("vikingdb down")
    provider = _provider_capturing()
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    parent = SupportAgent(provider, tap, model="ep-policy")
    child = ChildAgent(parent, Playbook(system_prompt="P"), memory=BoomMemory())
    res = child.run("refund policy?")  # memory throws -> child still answers
    assert res.answer == "child answer"
