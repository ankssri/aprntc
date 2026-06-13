"""Distillation + Child runtime — where the loop closes (Stage 6).

- :class:`Playbook` — the child's mutable artifact (system prompt + exemplars +
  directives). Edited via an **attributable diff**, never regenerated (ADR 0006).
- :class:`Distiller` — buckets scored episodes, mines :class:`~aprntc.memory.Lesson`
  objects, and proposes a :class:`PlaybookDiff`.
- :class:`ChildRuntime` — runs a demo agent under a candidate playbook + memory
  retrieval, so it can be compared against the parent at the promotion gate.
"""

from aprntc.distill.playbook import Playbook, PlaybookDiff
from aprntc.distill.distiller import Distiller, DistillationResult
from aprntc.distill.child import ChildAgent

__all__ = ["Playbook", "PlaybookDiff", "Distiller", "DistillationResult", "ChildAgent"]
