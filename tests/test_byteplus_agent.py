"""BytePlus support agent tests — KB chunking/retrieval, agent (thin vs rich),
outcome scorer. Offline with a fake KB + fake provider (no real docs/network)."""

import pytest

from aprntc.demos.byteplus.agent import ByteplusSupportAgent
from aprntc.demos.byteplus.gold import GOLD, GoldQA
from aprntc.demos.byteplus.kb import Chunk, KnowledgeBase, _tokens
from aprntc.demos.byteplus.outcome import byteplus_outcome
from aprntc.providers.base import CompletionResult
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, StepType, TrajectoryStore


def _kb() -> KnowledgeBase:
    def chunk(cid, doc, section, text):
        return Chunk(cid, doc, section, text, _tokens(section + " " + text))
    return KnowledgeBase([
        chunk("c1", "ModelArk Deepreasoning", "Enable",
              "Set the thinking parameter type to enabled to turn on deep reasoning."),
        chunk("c2", "VikingDB Overview", "What is VikingDB",
              "VikingDB is a cloud vector database for storing and searching vectors."),
        chunk("c3", "VikingDB Create Index", "Index types",
              "Supported index types are HNSW, HNSW_HYBRID, FLAT and DiskANN."),
    ])


@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


class CtxProvider:
    """Echoes a fixed answer; records the context it was given (to assert retrieval)."""
    def __init__(self, answer="see the docs"):
        self.answer = answer
        self.last_user = None
    def complete(self, *, model, messages, **kwargs):
        self.last_user = messages[-1]["content"]
        return CompletionResult(text=self.answer, usage={"total_tokens": 9})


# ─── KB ─────────────────────────────────────────────────────────────────────

def test_kb_search_ranks_relevant_chunk_first():
    kb = _kb()
    hits = kb.search("how do I enable deep reasoning thinking", k=2)
    assert hits and hits[0].doc == "ModelArk Deepreasoning"
    assert "thinking" in hits[0].text.lower()


def test_kb_search_index_types():
    hits = _kb().search("which index types does vikingdb support", k=1)
    assert hits and "HNSW" in hits[0].text


def test_kb_search_empty_query():
    assert _kb().search("", k=3) == []


def test_kb_docs_listing():
    assert len(_kb().docs()) == 3


def test_chunk_cite_format():
    c = list(_kb().chunks)[0]
    assert "›" in c.cite()


# ─── agent: thin vs rich ────────────────────────────────────────────────────

def test_agent_retrieves_and_records_step(store):
    provider = CtxProvider("Set thinking.type=enabled. [ModelArk Deepreasoning › Enable]")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = ByteplusSupportAgent(provider, tap, _kb(), model="ep", rich=True)
    res = agent.run("How do I enable deep reasoning?")

    assert res.cited  # citations captured
    ep = store.get_episode(res.episode_id)
    steps = ep.turns[0].steps
    assert any(s.tool_name == "search_docs" for s in steps)
    assert any(s.type is StepType.MODEL_CALL for s in steps)
    # retrieved doc text was injected into the model context
    assert "thinking" in provider.last_user.lower()


def test_thin_vs_rich_prompt_and_retrieval_differ():
    provider = CtxProvider()
    tap = AgentTap(lambda e: None, collector=Collector.SDK_WRAPPER)
    thin = ByteplusSupportAgent(provider, tap, _kb(), model="ep", rich=False, retrieve_k=1)
    rich = ByteplusSupportAgent(provider, tap, _kb(), model="ep", rich=True, retrieve_k=4)
    assert "cite" not in thin.system_prompt.lower()
    assert "cite" in rich.system_prompt.lower()
    assert thin._k < rich._k


def test_agent_no_hits_still_answers(store):
    provider = CtxProvider("I don't have that in the docs.")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = ByteplusSupportAgent(provider, tap, _kb(), model="ep")
    res = agent.run("zzz qqq unrelated nonsense")
    assert res.cited == []
    assert store.get_episode(res.episode_id).final_output


# ─── outcome scorer ─────────────────────────────────────────────────────────

def _ep(store, answer, grounded=True):
    from aprntc.trajectory import Episode, Step, Turn
    turn = Turn(turn_index=0)
    if grounded:
        turn.steps.append(Step(step_index=0, type=StepType.TOOL_CALL,
                               tool_name="search_docs", tool_result={"citations": ["X › Y"]}))
    ep = Episode(task_input="q", collector=Collector.SDK_WRAPPER, final_output=answer, turns=[turn])
    store.put_episode(ep, scrub=False)
    return ep


def test_outcome_perfect(store):
    gold = GoldQA("q", "thinking parameter type enabled", "Deepreasoning")
    ep = _ep(store, "Set the thinking parameter type to enabled. [Deepreasoning › Enable]")
    lbl = byteplus_outcome(ep, gold)
    assert lbl.score == pytest.approx(1.0)


def test_outcome_uncited_and_ungrounded_lower(store):
    gold = GoldQA("q", "thinking parameter type enabled", "Deepreasoning")
    # correct fact but NO citation and NO retrieval → thin parent's typical miss
    ep = _ep(store, "Set the thinking parameter type to enabled.", grounded=False)
    lbl = byteplus_outcome(ep, gold)
    assert lbl.score < 1.0  # penalized for missing grounding + citation


def test_outcome_wrong_answer_low(store):
    gold = GoldQA("q", "HNSW HNSW_HYBRID FLAT DiskANN", "Create Index")
    ep = _ep(store, "I'm not sure, maybe check the website.")
    lbl = byteplus_outcome(ep, gold)
    assert lbl.score < 0.5


# ─── gold set integrity ─────────────────────────────────────────────────────

def test_gold_set_well_formed():
    assert len(GOLD) >= 20
    for g in GOLD:
        assert g.question and g.reference and g.expect_doc
