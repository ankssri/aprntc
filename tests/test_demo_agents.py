"""Demo agent tests — offline with a fake provider; assert complete tapped trajectories."""

import pytest

from aprntc.demos import corpus
from aprntc.demos.agents import RagAgent, SupportAgent
from aprntc.providers.base import CompletionResult
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, Episode, StepType, TrajectoryStore


class ScriptedProvider:
    """Returns a fixed answer; records the messages it last saw (to assert context)."""

    def __init__(self, answer: str = "the answer"):
        self._answer = answer
        self.last_messages = None

    def complete(self, *, model, messages, **kwargs) -> CompletionResult:
        self.last_messages = messages
        return CompletionResult(text=self._answer, reasoning_content="reasoning…",
                                usage={"total_tokens": 11})


@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


# ─── support agent ──────────────────────────────────────────────────────────

def test_support_agent_uses_kb_and_records_trajectory(store):
    provider = ScriptedProvider("Refunds within 30 days.")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = SupportAgent(provider, tap, model="ep-policy")

    res = agent.run("what is your refund policy?")
    assert res.answer == "Refunds within 30 days."

    ep = store.get_episode(res.episode_id)
    tools = [s for s in ep.turns[0].steps if s.type is StepType.TOOL_CALL]
    model_calls = [s for s in ep.turns[0].steps if s.type is StepType.MODEL_CALL]
    assert any(s.tool_name == "kb_lookup" for s in tools)          # retrieval recorded
    assert len(model_calls) == 1                                    # model call captured
    assert ep.turns[0].reasoning_content == "reasoning…"           # reasoning surfaced
    # the KB content made it into the model context
    assert "refund" in str(provider.last_messages).lower()


def test_support_agent_order_status_tool(store):
    provider = ScriptedProvider("Your order A1001 has shipped.")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = SupportAgent(provider, tap, model="ep-policy")
    res = agent.run("where is order A1001?")
    ep = store.get_episode(res.episode_id)
    assert any(s.tool_name == "order_status" and s.tool_args["order_id"] == "A1001"
               for s in ep.turns[0].steps)


# ─── rag agent ──────────────────────────────────────────────────────────────

def test_rag_agent_retrieves_and_cites_context(store):
    provider = ScriptedProvider("About 4.6 billion years old. [doc_solar]")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = RagAgent(provider, tap, model="ep-policy")

    res = agent.run("How old is the Sun?")
    assert "doc_solar" in agent.last_retrieved
    ep = store.get_episode(res.episode_id)
    search_steps = [s for s in ep.turns[0].steps if s.tool_name == "search_docs"]
    assert len(search_steps) == 1
    assert "doc_solar" in search_steps[0].tool_result["doc_ids"]
    # retrieved doc text was injected into the model context
    assert "4.6 billion" in str(provider.last_messages)


def test_rag_agent_no_hits_still_produces_episode(store):
    provider = ScriptedProvider("I don't know.")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = RagAgent(provider, tap, model="ep-policy")
    res = agent.run("zzzz qqqq xxxx")  # no lexical overlap
    assert agent.last_retrieved == []
    ep = store.get_episode(res.episode_id)
    assert ep.final_output == "I don't know."


def test_gold_set_is_frozen_and_well_formed():
    # the gold set is the ruler — sanity-check its integrity (cited docs exist)
    assert len(corpus.GOLD) >= 5
    for item in corpus.GOLD:
        assert item.question and item.reference_answer
        for doc_id in item.cited_docs:
            assert doc_id in corpus.DOCS


# ─── failure path ───────────────────────────────────────────────────────────

def test_agent_records_partial_on_provider_error(store):
    class Boom:
        def complete(self, *, model, messages, **kwargs):
            raise RuntimeError("api down")

    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    agent = SupportAgent(Boom(), tap, model="ep-policy")
    with pytest.raises(RuntimeError):
        agent.run("refund policy?")
    # a partial episode was still persisted (the model_call error is captured)
    eps = store.query()
    assert len(eps) == 1 and eps[0].partial is True
    assert any(s.error and "api down" in s.error for s in eps[0].turns[0].steps)
