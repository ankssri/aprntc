"""Child runtime — run a demo agent under a candidate Playbook + memory retrieval.

The child is a clone of the parent agent whose **only** differences are: (1) it
runs the candidate :class:`Playbook` (rendered as its system prompt) instead of
the parent's static prompt, and (2) it retrieves relevant lessons from the
:class:`MemoryStore` and injects a few as context. This is what gets compared
against the parent at the promotion gate (Stage 7).

Memory is optional (``memory=None`` → playbook-only child), so the child runs
offline in tests without a live VikingDB.
"""

from __future__ import annotations

from typing import Any

from aprntc.demos.agents import DemoAgent
from aprntc.distill.playbook import Playbook
from aprntc.memory.base import MemoryStore
from aprntc.tap.core import TurnRecorder
from aprntc.trajectory.schema import StepType


class ChildAgent(DemoAgent):
    """A DemoAgent driven by a Playbook, with optional memory retrieval.

    Wraps an existing demo agent instance so the child shares the parent's tools
    and loop, differing only in prompt (playbook) + retrieved lessons.
    """

    domain = "child"

    def __init__(
        self,
        parent: DemoAgent,
        playbook: Playbook,
        *,
        memory: MemoryStore | None = None,
        retrieve_k: int = 3,
        min_reward: float = 0.5,
    ) -> None:
        # reuse the parent's provider/tap/model + its tool methods
        super().__init__(parent._provider, parent._tap, model=parent._model)
        self._parent = parent
        self._playbook = playbook
        self._memory = memory
        self._k = retrieve_k
        self._min_reward = min_reward
        # the child's system prompt IS the rendered playbook
        self.system_prompt = playbook.render()

    # inherit the parent's tools + context-building (retrieval, KB, etc.)
    def _tools(self) -> dict[str, Any]:
        return self._parent._tools()

    def _build_context(self, turn: TurnRecorder, task: str) -> str:
        # first, whatever the parent agent does (KB lookups / doc retrieval)
        base_context = type(self._parent)._build_context(self._parent, turn, task)

        # then, inject relevant distilled lessons from memory (if available)
        lesson_block = ""
        if self._memory is not None:
            try:
                hits = self._memory.retrieve(query=task, k=self._k, min_reward=self._min_reward)
            except Exception:
                hits = []  # memory is best-effort; never break the child
            if hits:
                turn.record_step(
                    StepType.TOOL_CALL, tool_name="memory_retrieve",
                    tool_args={"query": task, "k": self._k},
                    tool_result={"lesson_ids": [h.lesson.lesson_id for h in hits]},
                    source_fidelity="full",
                )
                lesson_block = "Relevant lessons:\n" + "\n".join(
                    f"- {h.lesson.content}" for h in hits
                )

        return "\n\n".join(p for p in (lesson_block, base_context) if p)
