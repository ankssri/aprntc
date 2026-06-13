"""Trajectory Store tests — persistence, scrub-at-ingest, append-only labels/
outcomes, fused reward, and privacy ops (delete_by_subject, TTL purge)."""

from datetime import datetime, timedelta, timezone

import pytest

from aprntc.trajectory import (
    Collector,
    Episode,
    Label,
    LabelSource,
    Outcome,
    PiiStatus,
    TrajectoryStore,
    Turn,
)


@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


def _ep(**kw) -> Episode:
    kw.setdefault("task_input", "do a thing")
    kw.setdefault("collector", Collector.SDK_WRAPPER)
    return Episode(**kw)


def test_put_and_get_roundtrip(store):
    e = _ep(trace_id="t1", turns=[Turn(turn_index=0)])
    eid = store.put_episode(e, scrub=False)
    got = store.get_episode(eid)
    assert got.episode_id == eid
    assert got.trace_id == "t1"
    assert store.count() == 1


def test_get_missing_raises(store):
    with pytest.raises(KeyError):
        store.get_episode("ep_nope")


def test_put_scrubs_pii_at_ingest_by_default(store):
    e = _ep(task_input="reach me at a@b.com", final_output="or c@d.com")
    eid = store.put_episode(e)  # scrub=True default
    got = store.get_episode(eid)
    assert got.pii_status is PiiStatus.SCRUBBED
    assert "a@b.com" not in got.task_input
    assert "c@d.com" not in (got.final_output or "")


def test_scrub_can_be_disabled(store):
    e = _ep(task_input="raw a@b.com")
    got = store.get_episode(store.put_episode(e, scrub=False))
    assert got.pii_status is PiiStatus.RAW
    assert "a@b.com" in got.task_input


def test_attach_label_append_only(store):
    eid = store.put_episode(_ep(), scrub=False)
    store.attach_label(eid, Label(source=LabelSource.JUDGE, score=0.6, judge_model="dsv4"))
    store.attach_label(eid, Label(source=LabelSource.HUMAN, score=0.9))
    labels = store.labels_for(eid)
    assert [l.source for l in labels] == [LabelSource.JUDGE, LabelSource.HUMAN]


def test_attach_label_unknown_episode_raises(store):
    with pytest.raises(KeyError):
        store.attach_label("ep_nope", Label(source=LabelSource.JUDGE, score=0.5))


def test_attach_label_scrubs_rationale(store):
    eid = store.put_episode(_ep(), scrub=False)
    store.attach_label(eid, Label(source=LabelSource.HUMAN, score=0.5,
                                  rationale="leaked x@y.com"))
    assert "x@y.com" not in (store.labels_for(eid)[0].rationale or "")


def test_outcome_join_by_trace(store):
    store.put_episode(_ep(trace_id="t9"), scrub=False)
    store.attach_outcome(Outcome(trace_id="t9", resolved=True, correct=True))
    outs = store.outcomes_for("t9")
    assert len(outs := outs) == 1 and outs[0].resolved is True


def test_labels_carried_on_episode_are_persisted(store):
    e = _ep(labels=[Label(source=LabelSource.JUDGE, score=0.7)],
            outcome=Outcome(trace_id="tc", resolved=True), trace_id="tc")
    eid = store.put_episode(e, scrub=False)
    assert len(store.labels_for(eid)) == 1
    assert len(store.outcomes_for("tc")) == 1


def test_fused_reward_none_without_labels(store):
    eid = store.put_episode(_ep(), scrub=False)
    assert store.fused_reward(eid) is None


def test_fused_reward_outcome_outweighs_judge(store):
    eid = store.put_episode(_ep(), scrub=False)
    store.attach_label(eid, Label(source=LabelSource.JUDGE, score=0.0))
    store.attach_label(eid, Label(source=LabelSource.OUTCOME, score=1.0))
    reward, conf = store.fused_reward(eid)
    # outcome (weight 1.0) should pull the fused reward well above the midpoint
    assert reward > 0.6
    assert conf == 1.0  # anchored by the outcome source


def test_query_filters(store):
    store.put_episode(_ep(generation_id="G1"), scrub=False)
    store.put_episode(_ep(generation_id="G2", collector=Collector.OTEL), scrub=False)
    assert len(store.query(generation_id="G1")) == 1
    assert len(store.query(collector="otel")) == 1
    assert len(store.query()) == 2


def test_delete_by_subject(store):
    e1 = _ep()
    e2 = _ep()
    store.put_episode(e1, scrub=False, subject_ids=["user-42"])
    store.put_episode(e2, scrub=False, subject_ids=["user-99"])
    deleted = store.delete_by_subject("user-42")
    assert deleted == 1
    assert store.count() == 1
    with pytest.raises(KeyError):
        store.get_episode(e1.episode_id)


def test_delete_by_subject_cascades_labels(store):
    e = _ep()
    store.put_episode(e, scrub=False, subject_ids=["s1"])
    store.attach_label(e.episode_id, Label(source=LabelSource.JUDGE, score=0.5))
    store.delete_by_subject("s1")
    assert store.labels_for(e.episode_id) == []


def test_purge_expired_ttl(store):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    store.put_episode(_ep(retention_until=past), scrub=False)
    keep = _ep(retention_until=future)
    store.put_episode(keep, scrub=False)
    store.put_episode(_ep(), scrub=False)  # no TTL → kept
    purged = store.purge_expired()
    assert purged == 1
    assert store.count() == 2
