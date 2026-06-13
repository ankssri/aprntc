"""Demo agents: a tapped model→tool loop, plus support-chat and RAG-Q&A.

Each agent owns its tools and runs a small loop; the SDK-wrapper tap captures
model calls (full fidelity) and the agent records tool steps. ``run()`` returns
the final answer; the trajectory is emitted to the tap's sink (e.g. the store).

Provider-agnostic: any ``LLMProvider`` works (fake in tests, ModelArk live).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from aprntc.demos import corpus
from aprntc.providers.base import LLMProvider
from aprntc.tap import AgentTap, wrap
from aprntc.tap.core import TurnRecorder
from aprntc.trajectory.schema import StepType

Tool = Callable[..., Any]


@dataclass
class AgentResult:
    answer: str
    episode_id: str


class DemoAgent:
    """Base: one tapped turn = system+context prompt → model → optional tool → answer."""

    domain = "generic"
    system_prompt = "You are a helpful assistant. Answer concisely."

    def __init__(self, provider: LLMProvider, tap: AgentTap, *, model: str) -> None:
        self._provider = provider
        self._tap = tap
        self._model = model

    # subclasses override these two
    def _tools(self) -> dict[str, Tool]:
        return {}

    def _build_context(self, turn: TurnRecorder, task: str) -> str:
        """Run any pre-model tools (e.g. retrieval), record them, return extra context."""
        return ""

    def run(self, task: str, *, trace_id: str | None = None,
            generation_id: str | None = None) -> AgentResult:
        rec = self._tap.start_episode(
            task, trace_id=trace_id, generation_id=generation_id, model_id=self._model
        )
        turn = rec.turn(user_text=task)
        # Tap model calls into THIS turn (full fidelity).
        tapped = wrap(self._provider, turn_provider=lambda: turn)

        try:
            extra_context = self._build_context(turn, task)
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{extra_context}\n\n{task}".strip()},
            ]
            result = tapped.complete(model=self._model, messages=messages)
            turn.add_agent_text(result.text)
            ep = rec.finish(final_output=result.text)
            return AgentResult(answer=result.text, episode_id=ep.episode_id)
        except Exception:
            rec.finish(partial=True)
            raise


class SupportAgent(DemoAgent):
    """Customer-support chat. Tools: KB lookup + order status."""

    domain = "support"
    system_prompt = (
        "You are a customer-support agent. Use the provided knowledge base and order "
        "info to answer accurately and concisely. If unknown, say so."
    )

    def _tools(self) -> dict[str, Tool]:
        return {"kb_lookup": self._kb_lookup, "order_status": self._order_status}

    def _kb_lookup(self, topic: str) -> str:
        return corpus.KB.get(topic, "")

    def _order_status(self, order_id: str) -> dict[str, str] | None:
        return corpus.ORDERS.get(order_id)

    def _build_context(self, turn: TurnRecorder, task: str) -> str:
        """Heuristically pull KB entries + any order id mentioned, recording each tool call."""
        ctx_parts: list[str] = []
        low = task.lower()
        for topic in corpus.KB:
            if any(w in low for w in topic.split("_")):
                start = time.perf_counter()
                val = self._kb_lookup(topic)
                turn.record_step(StepType.TOOL_CALL, tool_name="kb_lookup",
                                 tool_args={"topic": topic}, tool_result=val,
                                 duration_ms=(time.perf_counter() - start) * 1000)
                if val:
                    ctx_parts.append(f"KB[{topic}]: {val}")
        for token in task.replace("?", " ").split():
            if token in corpus.ORDERS:
                start = time.perf_counter()
                info = self._order_status(token)
                turn.record_step(StepType.TOOL_CALL, tool_name="order_status",
                                 tool_args={"order_id": token}, tool_result=info,
                                 duration_ms=(time.perf_counter() - start) * 1000)
                if info:
                    ctx_parts.append(f"Order {token}: {info}")
        return "\n".join(ctx_parts)


class RagAgent(DemoAgent):
    """RAG-Q&A over the synthetic doc corpus. Tool: doc retrieval."""

    domain = "rag"
    system_prompt = (
        "You answer questions using ONLY the provided context documents. "
        "Cite the doc ids you used. If the answer isn't in the context, say you don't know."
    )

    def __init__(self, *args: Any, k: int = 2, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._k = k
        self.last_retrieved: list[str] = []

    def _build_context(self, turn: TurnRecorder, task: str) -> str:
        start = time.perf_counter()
        hits = corpus.search_docs(task, k=self._k)
        self.last_retrieved = [doc_id for doc_id, _ in hits]
        turn.record_step(
            StepType.TOOL_CALL, tool_name="search_docs",
            tool_args={"query": task, "k": self._k},
            tool_result={"doc_ids": self.last_retrieved},
            duration_ms=(time.perf_counter() - start) * 1000,
        )
        if not hits:
            return "Context: (no relevant documents found)"
        return "Context:\n" + "\n".join(f"[{doc_id}] {text}" for doc_id, text in hits)
