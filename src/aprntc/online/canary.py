"""Canary controller — gradual post-promotion rollout with auto-rollback.

After a child is promoted, don't send it 100% of traffic immediately. Route a
small fraction, watch a live quality metric vs the parent's baseline, and:
  - **advance** the fraction through stages when the canary holds up, or
  - **auto-rollback** to the parent the moment the metric degrades past a margin.

Routing is deterministic + injectable (no ``random``): ``route(request_key)`` hashes
the key to a stable [0,1) so the same user lands in the same arm. Metric feeding is
push-based (``record``) so the host wires whatever signal it has (thumbs, outcomes).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class CanaryStatus(str, Enum):
    RUNNING = "running"       # canary live, within a stage
    PROMOTED = "promoted"     # reached 100% — fully rolled out
    ROLLED_BACK = "rolled_back"  # auto-reverted to parent on degradation


@dataclass
class _Arm:
    n: int = 0
    reward_sum: float = 0.0

    @property
    def mean(self) -> float:
        return self.reward_sum / self.n if self.n else 0.0


@dataclass
class CanaryController:
    """Stage-based canary with auto-rollback.

    ``stages`` = traffic fractions to the child, advanced when ``min_per_stage``
    samples accumulate and the child isn't degrading. ``degrade_margin``: if the
    child's mean reward falls below the parent's by more than this, roll back.
    """

    stages: tuple[float, ...] = (0.05, 0.25, 0.50, 1.0)
    min_per_stage: int = 20
    degrade_margin: float = 0.05
    grace_n: int = 5  # don't judge degradation before this many child samples

    _stage_idx: int = 0
    status: CanaryStatus = CanaryStatus.RUNNING
    _child: _Arm = field(default_factory=_Arm)
    _parent: _Arm = field(default_factory=_Arm)
    _stage_count: int = 0

    @property
    def fraction(self) -> float:
        """Current fraction of traffic routed to the child (0 once rolled back)."""
        if self.status is CanaryStatus.ROLLED_BACK:
            return 0.0
        if self.status is CanaryStatus.PROMOTED:
            return 1.0
        return self.stages[self._stage_idx]

    def route(self, request_key: str) -> str:
        """Return 'child' or 'parent' for a request — stable per key."""
        if self.status is CanaryStatus.ROLLED_BACK:
            return "parent"
        if self.status is CanaryStatus.PROMOTED:
            return "child"
        h = hashlib.sha256(request_key.encode("utf-8")).digest()
        frac = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
        return "child" if frac < self.fraction else "parent"

    def record(self, arm: str, reward: float) -> CanaryStatus:
        """Feed a quality signal for the arm that served a request. Returns status.

        Triggers auto-rollback on degradation, or advances the stage when the
        current stage has enough samples and the child is holding up.
        """
        if self.status is not CanaryStatus.RUNNING:
            return self.status

        if arm == "child":
            self._child.n += 1
            self._child.reward_sum += reward
            self._stage_count += 1
        else:
            self._parent.n += 1
            self._parent.reward_sum += reward

        # auto-rollback: child clearly worse than the parent baseline
        if (self._child.n >= self.grace_n and self._parent.n >= self.grace_n
                and self._child.mean < self._parent.mean - self.degrade_margin):
            self.status = CanaryStatus.ROLLED_BACK
            return self.status

        # advance the stage when it has enough child samples and isn't degrading
        if self._stage_count >= self.min_per_stage:
            self._stage_count = 0
            if self._stage_idx + 1 < len(self.stages):
                self._stage_idx += 1
            else:
                self.status = CanaryStatus.PROMOTED
        return self.status

    def summary(self) -> str:
        return (f"canary {self.status.value} frac={self.fraction:.0%} "
                f"child={self._child.mean:.0%}(n={self._child.n}) "
                f"parent={self._parent.mean:.0%}(n={self._parent.n})")
