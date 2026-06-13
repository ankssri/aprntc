"""Promotion gate + Lineage — turn "a better child" into "a human can ship & undo it".

- :mod:`aprntc.promote.stats` — Wilson CI for win-rate (the powered acceptance test).
- :class:`PromotionGate` — run parent vs child on a held-out set, score with a recused
  judge, enforce the acceptance bar + hard gates, emit a decision.
- :class:`LineageRegistry` — generation DAG + rollback pointer (promote/rollback).
"""

from aprntc.promote.stats import wilson_interval, GateReport
from aprntc.promote.gate import PromotionGate, EvalCase
from aprntc.promote.lineage import Generation, LineageRegistry

__all__ = [
    "wilson_interval",
    "GateReport",
    "PromotionGate",
    "EvalCase",
    "Generation",
    "LineageRegistry",
]
