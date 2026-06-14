"""A6 multi-agent fleets — registry (per-agent lineage, domain scoping) + lesson sharing."""

import pytest

from aprntc.fleet import AgentRef, Fleet, share_lessons, shareable_lessons
from aprntc.memory.base import Lesson, LessonType, content_lesson_id


# ─── fleet registry ──────────────────────────────────────────────────────────

def test_register_and_get(tmp_path):
    f = Fleet(tmp_path / "fleet")
    f.register(AgentRef("support-1", domain="support", name="Support"))
    assert f.get("support-1").domain == "support"
    with pytest.raises(KeyError):
        f.get("nope")


def test_by_domain_excludes_self(tmp_path):
    f = Fleet(tmp_path / "fleet")
    f.register(AgentRef("a", domain="support"))
    f.register(AgentRef("b", domain="support"))
    f.register(AgentRef("c", domain="coding"))
    peers = f.by_domain("support", exclude="a")
    assert {p.agent_id for p in peers} == {"b"}


def test_per_agent_lineage_is_isolated(tmp_path):
    f = Fleet(tmp_path / "fleet")
    f.register(AgentRef("a", domain="support"))
    f.register(AgentRef("b", domain="support"))
    la = f.lineage("a"); la.register_parent("pb_a0"); la.promote("pb_a1")
    lb = f.lineage("b"); lb.register_parent("pb_b0")
    # each agent has its own generations
    assert f.lineage("a").current.generation == 1
    assert f.lineage("b").current.generation == 0


def test_fleet_persists(tmp_path):
    root = tmp_path / "fleet"
    Fleet(root).register(AgentRef("x", domain="rag"))
    assert Fleet(root).get("x").domain == "rag"  # reloaded from disk


# ─── lesson sharing ──────────────────────────────────────────────────────────

def _lesson(content, *, rtype=LessonType.DIRECTIVE, reward=0.9, situation="s"):
    return Lesson(content=content, lesson_type=rtype, situation=situation, reward=reward)


def test_shareable_filters_by_reward_and_type():
    src = [
        _lesson("good directive", reward=0.9),
        _lesson("weak directive", reward=0.4),                       # low reward
        _lesson("an exemplar", rtype=LessonType.EXEMPLAR, reward=0.95),  # not shareable type
        _lesson("avoid X", rtype=LessonType.FAILURE_PATTERN, reward=0.8),
    ]
    out = shareable_lessons(src, min_reward=0.7)
    contents = {l.content for l in out}
    assert contents == {"good directive", "avoid X"}


def test_share_tags_provenance_and_dedups():
    src = [
        _lesson("cite the source", reward=0.9),
        _lesson("call the tool", rtype=LessonType.FAILURE_PATTERN, reward=0.85),
    ]
    # target already has "cite the source" (same situation+content -> same id)
    target = [_lesson("cite the source", reward=0.6)]
    report = share_lessons(src, target, source_agent_id="agent-a", min_reward=0.7)

    assert report.skipped_duplicate == 1
    assert len(report.shared) == 1
    shared = report.shared[0]
    assert shared.content == "call the tool"
    assert shared.metadata["shared_from"] == "agent-a"             # provenance
    assert shared.lesson_id == content_lesson_id(shared.situation, shared.content)


def test_share_skips_low_reward_and_exemplars():
    src = [
        _lesson("mediocre", reward=0.5),
        _lesson("situation-specific", rtype=LessonType.EXEMPLAR, reward=0.99),
        _lesson("solid rule", reward=0.9),
    ]
    report = share_lessons(src, [], source_agent_id="a", min_reward=0.7)
    assert [l.content for l in report.shared] == ["solid rule"]
    assert report.skipped_low_reward == 1 and report.skipped_wrong_type == 1


def test_share_report_summary():
    report = share_lessons([_lesson("r", reward=0.9)], [], source_agent_id="a")
    assert "shared 1" in report.summary()


def test_end_to_end_fleet_sharing(tmp_path):
    # two support agents; A's good lessons get offered to B (different domain agent excluded)
    f = Fleet(tmp_path / "fleet")
    f.register(AgentRef("support-a", domain="support"))
    f.register(AgentRef("support-b", domain="support"))
    f.register(AgentRef("coder", domain="coding"))

    a_lessons = [_lesson("ground answers in the KB", reward=0.92),
                 _lesson("don't guess order status", rtype=LessonType.FAILURE_PATTERN, reward=0.8)]
    b_lessons: list = []

    # share within the support domain only
    peers = f.by_domain("support", exclude="support-a")
    assert [p.agent_id for p in peers] == ["support-b"]  # coder excluded by domain
    report = share_lessons(a_lessons, b_lessons, source_agent_id="support-a")
    assert len(report.shared) == 2
    assert all(l.metadata["shared_from"] == "support-a" for l in report.shared)
