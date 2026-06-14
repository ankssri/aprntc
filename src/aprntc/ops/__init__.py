"""Operations / robustness (B3) — make the autonomous loop actually RUN in prod.

The design's "nightly distillation" never fires by itself in the MVP (it's manual).
This package adds the runtime plumbing to operate aprntc as a service:

- :class:`Scheduler` — run jobs on an interval (the nightly distill/eval cadence),
  off the request path, fail-isolated (one job's error never kills the loop).
- :func:`with_retry` — bounded retry+backoff for flaky external calls (ModelArk /
  VikingDB), so transient blips don't drop episodes.
- :class:`OpsMetrics` — lightweight in-process counters/timers + a health snapshot
  so aprntc can observe itself (surfaced via the web API).
"""

from aprntc.ops.scheduler import Job, Scheduler
from aprntc.ops.retry import RetryError, with_retry
from aprntc.ops.metrics import OpsMetrics, METRICS

__all__ = ["Job", "Scheduler", "RetryError", "with_retry", "OpsMetrics", "METRICS"]
