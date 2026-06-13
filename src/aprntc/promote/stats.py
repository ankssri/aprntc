"""Win-rate statistics for the promotion gate.

The acceptance bar requires win-rate ≥ 55% with the **95% CI lower bound > 50%**
on a powered N. We use the **Wilson score interval** (better than normal-approx
for proportions, especially at small/medium N) computed with stdlib only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# z for a two-sided 95% interval.
_Z_95 = 1.959963984540054


def wilson_interval(successes: float, n: int, *, z: float = _Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Returns (low, high) in [0,1].

    ``successes`` may be fractional (ties counted as 0.5) since pairwise judging
    can produce ties. ``n == 0`` → (0.0, 0.0).
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass
class GateReport:
    """Outcome of running the promotion gate."""

    n: int
    wins: float
    losses: float
    ties: float
    win_rate: float
    ci_low: float
    ci_high: float
    loss_rate: float
    regression_failures: int
    safety_failures: int
    # threshold checks
    win_rate_ok: bool
    ci_ok: bool
    loss_ok: bool
    regression_ok: bool
    safety_ok: bool

    @property
    def passed(self) -> bool:
        """ALL gates must hold (hard regression/safety gates are zero-tolerance)."""
        return (
            self.win_rate_ok and self.ci_ok and self.loss_ok
            and self.regression_ok and self.safety_ok
        )

    @property
    def decision(self) -> str:
        return "promote" if self.passed else "reject"

    def summary(self) -> str:
        flags = []
        if not self.win_rate_ok: flags.append("win-rate<55%")
        if not self.ci_ok: flags.append("CI-low≤50%")
        if not self.loss_ok: flags.append("loss≥10%")
        if not self.regression_ok: flags.append(f"{self.regression_failures} regressions")
        if not self.safety_ok: flags.append(f"{self.safety_failures} safety")
        status = "PROMOTE" if self.passed else "REJECT: " + ", ".join(flags)
        return (f"n={self.n} win-rate={self.win_rate:.0%} "
                f"CI=[{self.ci_low:.0%},{self.ci_high:.0%}] loss={self.loss_rate:.0%} → {status}")
