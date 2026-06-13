"""Eval health metrics — keep the judge honest (anti reward-hacking).

* **judge_reference_agreement** — how often the judge agrees with a trusted
  reference (human/outcome). Drift here is the kill-switch signal to pause
  distillation (tracked as a first-class metric per the design).
* **reward_hacking_alarm** — fires when the judge score climbs while the
  outcome/anchor stays flat or drops (judge↑ outcome-flat = gaming the judge).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgreementReport:
    n: int
    agreement: float       # [0,1]; fraction where judge and reference agree
    pass_threshold: bool


def judge_reference_agreement(
    judge_scores: list[float],
    reference_scores: list[float],
    *,
    decision: float = 0.5,
    min_agreement: float = 0.7,
) -> AgreementReport:
    """Binarize both at ``decision`` and measure agreement. Below ``min_agreement``
    → pause distillation (judge drift)."""
    if len(judge_scores) != len(reference_scores):
        raise ValueError("judge_scores and reference_scores must be the same length")
    n = len(judge_scores)
    if n == 0:
        return AgreementReport(n=0, agreement=0.0, pass_threshold=False)
    agree = sum(
        1 for j, r in zip(judge_scores, reference_scores)
        if (j >= decision) == (r >= decision)
    )
    rate = agree / n
    return AgreementReport(n=n, agreement=rate, pass_threshold=rate >= min_agreement)


def reward_hacking_alarm(
    judge_delta: float,
    outcome_delta: float,
    *,
    judge_up: float = 0.05,
    outcome_floor: float = 0.0,
) -> bool:
    """True when the judge improves meaningfully (``>= judge_up``) but the outcome
    anchor does not (``<= outcome_floor``) — the classic reward-hacking signature."""
    return judge_delta >= judge_up and outcome_delta <= outcome_floor
