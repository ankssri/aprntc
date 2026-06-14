"""Auto-promotion policy (A4) — promote low-risk diffs without a human, gated hard.

User decision (ADR-tracked): "human now, auto later." So this is **opt-in and
default-OFF** (``enabled=False``). When enabled, a promotion is auto-approved ONLY
if EVERY guardrail clears; otherwise it falls back to **human review** (never to a
silent reject — a human still sees it). Zero-tolerance gates (regression/safety)
can never be auto-bypassed.

Guardrails for an auto-promote:
  1. enabled (opt-in)                          — off by default
  2. gate passed                               — the full acceptance bar held
  3. MARGIN above the bar                      — not a barely-passing fluke
  4. zero regression + zero safety failures    — hard, always
  5. low-risk diff                             — small, additive (no big rewrites)
  6. established trust                          — judge↔outcome agreement is high
                                                 (ties to A3 / health metrics)
A clean decision object explains exactly which guardrail blocked auto, for audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from aprntc.distill.playbook import PlaybookDiff
from aprntc.promote.stats import GateReport


class PromotionAction(str, Enum):
    AUTO_PROMOTE = "auto_promote"     # all guardrails clear → promote without a human
    HUMAN_REVIEW = "human_review"     # eligible to ship, but needs human approval
    REJECT = "reject"                 # gate failed → not promotable at all


@dataclass
class AutoDecision:
    action: PromotionAction
    reasons: list[str] = field(default_factory=list)  # why NOT auto (audit trail)

    @property
    def is_auto(self) -> bool:
        return self.action is PromotionAction.AUTO_PROMOTE

    def summary(self) -> str:
        if self.action is PromotionAction.REJECT:
            return "REJECT (gate failed)"
        if self.is_auto:
            return "AUTO-PROMOTE (all guardrails clear)"
        return "HUMAN REVIEW — " + "; ".join(self.reasons)


@dataclass
class AutoPromotionPolicy:
    """Decides auto-promote vs human-review vs reject. Default-OFF, conservative."""

    enabled: bool = False
    # margin guardrails (must clear the bar by THIS much, not just barely)
    win_rate_min: float = 0.60        # bar is 0.55; require 0.60 for auto
    ci_low_min: float = 0.55          # bar is 0.50; require 0.55 for auto
    loss_rate_max: float = 0.05       # bar is 0.10; require <0.05 for auto
    # low-risk diff: small + additive only
    max_diff_items: int = 3           # at most N added items total
    allow_watch_out: bool = True      # adding "avoid X" warnings is low-risk
    # established trust (e.g. A3 judge↔outcome agreement, or health metric)
    min_trust: float = 0.80

    def decide(
        self,
        gate: GateReport,
        diff: PlaybookDiff,
        *,
        trust: float | None = None,
    ) -> AutoDecision:
        # 0) gate must pass at all — hard gates (regression/safety) live here
        if not gate.passed:
            return AutoDecision(PromotionAction.REJECT, [gate.summary()])

        reasons: list[str] = []

        # 1) opt-in
        if not self.enabled:
            reasons.append("auto-promotion disabled (opt-in)")

        # 2) margin above the bar
        if gate.win_rate < self.win_rate_min:
            reasons.append(f"win-rate {gate.win_rate:.0%} < auto-min {self.win_rate_min:.0%}")
        if gate.ci_low < self.ci_low_min:
            reasons.append(f"CI-low {gate.ci_low:.0%} < auto-min {self.ci_low_min:.0%}")
        if gate.loss_rate > self.loss_rate_max:
            reasons.append(f"loss-rate {gate.loss_rate:.0%} > auto-max {self.loss_rate_max:.0%}")

        # 3) hard gates clear with literal zero (defensive; gate.passed already implies it)
        if gate.regression_failures or gate.safety_failures:
            reasons.append("regression/safety failures present")

        # 4) low-risk diff: small + additive
        n_items = len(diff.add_directives) + len(diff.add_exemplars) + len(diff.add_watch_out)
        if n_items == 0:
            reasons.append("empty diff (nothing to promote)")
        if n_items > self.max_diff_items:
            reasons.append(f"diff too large ({n_items} items > {self.max_diff_items})")
        if diff.add_exemplars and len(diff.add_exemplars) + len(diff.add_directives) > self.max_diff_items:
            reasons.append("diff changes too much policy at once")

        # 5) established trust
        if self.min_trust > 0:
            if trust is None:
                reasons.append("no trust signal available")
            elif trust < self.min_trust:
                reasons.append(f"trust {trust:.0%} < min {self.min_trust:.0%}")

        if reasons:
            return AutoDecision(PromotionAction.HUMAN_REVIEW, reasons)
        return AutoDecision(PromotionAction.AUTO_PROMOTE, [])
