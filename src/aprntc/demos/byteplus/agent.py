"""BytePlus product-support agent — a real, doc-grounded demo parent.

Answers questions about the BytePlus AI stack by retrieving from the doc knowledge
base and citing sources. Has two configs for honest apprentice headroom:

* **parent (thin):** retrieves few chunks, a terse system prompt, no citation
  discipline → sometimes shallow / uncited / incomplete answers (real mistakes).
* **rich (what a distilled child approximates):** more chunks + a disciplined
  prompt that demands grounding + citations.

The apprentice's job is to close the gap from thin → rich by distilling lessons
from where the thin parent underperforms.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from aprntc.demos.byteplus.kb import KnowledgeBase
from aprntc.providers.base import LLMProvider
from aprntc.tap import AgentTap, wrap
from aprntc.tap.core import TurnRecorder
from aprntc.trajectory.schema import StepType

_THIN_PROMPT = (
    "You are a BytePlus support assistant. Answer the user's question briefly."
)
_RICH_PROMPT = (
    "You are a BytePlus product-support expert. Answer ONLY from the provided "
    "documentation context. Be specific and accurate. ALWAYS cite the doc section(s) "
    "you used in the form [doc › section]. If the context doesn't cover it, say so "
    "rather than guessing."
)


@dataclass
class AgentResult:
    answer: str
    episode_id: str
    cited: list[str]


class ByteplusSupportAgent:
    """Doc-grounded BytePlus support agent (provider-agnostic)."""

    domain = "byteplus_support"

    def __init__(
        self,
        provider: LLMProvider,
        tap: AgentTap,
        kb: KnowledgeBase,
        *,
        model: str,
        retrieve_k: int = 4,
        rich: bool = False,
        playbook=None,  # optional distilled Playbook → makes this a CHILD
    ) -> None:
        self._provider = provider
        self._tap = tap
        self._kb = kb
        self._model = model
        self._k = retrieve_k
        self._rich = rich
        self._playbook = playbook
        base_prompt = _RICH_PROMPT if rich else _THIN_PROMPT
        # A child renders the candidate playbook (distilled lessons) on top of the base prompt.
        self.system_prompt = playbook.render() if playbook is not None else base_prompt
        self.last_cited: list[str] = []

    def as_child(self, playbook, *, retrieve_k: int | None = None) -> "ByteplusSupportAgent":
        """Return a child clone of this agent driven by a candidate playbook."""
        return ByteplusSupportAgent(
            self._provider, self._tap, self._kb, model=self._model,
            retrieve_k=retrieve_k if retrieve_k is not None else self._k,
            rich=True, playbook=playbook,
        )

    def run(self, task: str, *, generation_id: str | None = None,
            trace_id: str | None = None) -> AgentResult:
        rec = self._tap.start_episode(task, trace_id=trace_id,
                                      generation_id=generation_id, model_id=self._model)
        turn = rec.turn(user_text=task)
        tapped = wrap(self._provider, turn_provider=lambda: turn)
        try:
            context = self._retrieve(turn, task)
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{context}\n\nQuestion: {task}".strip()},
            ]
            result = tapped.complete(model=self._model, messages=messages)
            turn.add_agent_text(result.text)
            ep = rec.finish(final_output=result.text)
            return AgentResult(answer=result.text, episode_id=ep.episode_id,
                              cited=list(self.last_cited))
        except Exception:
            rec.finish(partial=True)
            raise

    def _retrieve(self, turn: TurnRecorder, task: str) -> str:
        start = time.perf_counter()
        hits = self._kb.search(task, k=self._k)
        self.last_cited = [h.cite() for h in hits]
        turn.record_step(
            StepType.TOOL_CALL, tool_name="search_docs",
            tool_args={"query": task, "k": self._k},
            tool_result={"citations": self.last_cited},
            duration_ms=(time.perf_counter() - start) * 1000,
        )
        if not hits:
            return "Context: (no relevant documentation found)"
        return "Documentation context:\n" + "\n\n".join(
            f"[{h.cite()}]\n{h.text}" for h in hits
        )
