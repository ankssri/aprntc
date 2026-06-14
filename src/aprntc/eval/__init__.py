"""Evaluation / Labeling — turn trajectories into quality signals (Stage 4).

Three signal sources feed the store's confidence-weighted fusion (ADR 0006,
reliability: outcome > explicit > implicit > judge):

- :class:`PairwiseJudge` — a recused LLM judge (judge ≠ policy) → ``judge`` labels.
- Outcome scorers (:mod:`aprntc.eval.outcomes`) — domain ground-truth → ``outcome`` labels.
- :mod:`aprntc.eval.health` — judge↔reference agreement + a reward-hacking guard.
"""

from aprntc.eval.judge import JudgeVerdict, PairwiseJudge
from aprntc.eval.outcomes import rag_outcome, support_outcome
from aprntc.eval.health import judge_reference_agreement, reward_hacking_alarm
from aprntc.eval.fusion import FusionWeights, SourceAgreement, learn_weights

__all__ = [
    "JudgeVerdict",
    "PairwiseJudge",
    "rag_outcome",
    "support_outcome",
    "judge_reference_agreement",
    "reward_hacking_alarm",
    "FusionWeights",
    "SourceAgreement",
    "learn_weights",
]
