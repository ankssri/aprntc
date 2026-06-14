"""A4 auto-promotion policy — default-off, hard-gated, falls back to human review."""

import pytest

from aprntc.distill.playbook import PlaybookDiff
from aprntc.promote import AutoPromotionPolicy, PromotionAction
from aprntc.promote.stats import GateReport


def _gate(**over) -> GateReport:
    base = dict(n=200, wins=140, losses=8, ties=0, win_rate=0.70, ci_low=0.63,
                ci_high=0.76, loss_rate=0.04, regression_failures=0, safety_failures=0,
                win_rate_ok=True, ci_ok=True, loss_ok=True, regression_ok=True, safety_ok=True)
    base.update(over)
    return GateReport(**base)


def _small_diff() -> PlaybookDiff:
    return PlaybookDiff(add_directives=["cite the doc section used"])


# ─── default-off ─────────────────────────────────────────────────────────────

def test_disabled_by_default_routes_to_human():
    # even a great gate + small diff + high trust → human review, because opt-in off
    d = AutoPromotionPolicy().decide(_gate(), _small_diff(), trust=0.95)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("disabled" in r for r in d.reasons)


# ─── the happy path (enabled + all guardrails clear) ─────────────────────────

def test_enabled_all_clear_auto_promotes():
    pol = AutoPromotionPolicy(enabled=True)
    d = pol.decide(_gate(), _small_diff(), trust=0.95)
    assert d.is_auto and d.action is PromotionAction.AUTO_PROMOTE
    assert d.reasons == []


# ─── reject when the gate itself fails (hard) ────────────────────────────────

def test_failed_gate_rejects_even_if_enabled():
    pol = AutoPromotionPolicy(enabled=True)
    bad = _gate(safety_ok=False, safety_failures=1)
    d = pol.decide(bad, _small_diff(), trust=0.95)
    assert d.action is PromotionAction.REJECT


def test_regression_failure_rejects():
    pol = AutoPromotionPolicy(enabled=True)
    d = pol.decide(_gate(regression_ok=False, regression_failures=2), _small_diff(), trust=0.95)
    assert d.action is PromotionAction.REJECT


# ─── margin guardrails (pass the bar but not by enough) ──────────────────────

def test_barely_passing_gate_needs_human():
    # passes the bar (win 0.56, ci 0.51, loss 0.09) but below the AUTO margins
    pol = AutoPromotionPolicy(enabled=True)
    marginal = _gate(win_rate=0.56, ci_low=0.51, loss_rate=0.09)
    d = pol.decide(marginal, _small_diff(), trust=0.95)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("win-rate" in r or "CI-low" in r or "loss-rate" in r for r in d.reasons)


# ─── low-risk diff guardrail ─────────────────────────────────────────────────

def test_large_diff_needs_human():
    pol = AutoPromotionPolicy(enabled=True, max_diff_items=3)
    big = PlaybookDiff(add_directives=["a", "b", "c", "d", "e"])
    d = pol.decide(_gate(), big, trust=0.95)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("too large" in r for r in d.reasons)


def test_empty_diff_needs_human():
    pol = AutoPromotionPolicy(enabled=True)
    d = pol.decide(_gate(), PlaybookDiff(), trust=0.95)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("empty diff" in r for r in d.reasons)


# ─── trust guardrail ─────────────────────────────────────────────────────────

def test_low_trust_needs_human():
    pol = AutoPromotionPolicy(enabled=True, min_trust=0.80)
    d = pol.decide(_gate(), _small_diff(), trust=0.5)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("trust" in r for r in d.reasons)


def test_missing_trust_signal_needs_human():
    pol = AutoPromotionPolicy(enabled=True, min_trust=0.80)
    d = pol.decide(_gate(), _small_diff(), trust=None)
    assert d.action is PromotionAction.HUMAN_REVIEW
    assert any("no trust signal" in r for r in d.reasons)


def test_multiple_blockers_all_reported():
    pol = AutoPromotionPolicy(enabled=True)
    d = pol.decide(_gate(win_rate=0.56, ci_low=0.51), PlaybookDiff(add_directives=["a"] * 9), trust=0.4)
    assert d.action is PromotionAction.HUMAN_REVIEW
    # audit trail lists every failed guardrail
    assert len(d.reasons) >= 3


def test_summary_strings():
    pol = AutoPromotionPolicy(enabled=True)
    assert "AUTO-PROMOTE" in pol.decide(_gate(), _small_diff(), trust=0.95).summary()
    assert "HUMAN REVIEW" in AutoPromotionPolicy().decide(_gate(), _small_diff(), trust=0.95).summary()
    assert "REJECT" in pol.decide(_gate(safety_ok=False, safety_failures=1), _small_diff()).summary()
