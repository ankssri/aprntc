"""Scheduler — run the autonomous loop's jobs on a cadence, off the request path.

The "nightly distillation / eval" cadence the design calls for needs something to
actually fire it. :class:`Scheduler` runs registered :class:`Job`s on their interval
in a background thread, **fail-isolated** (a job raising never kills the scheduler or
other jobs — the error is recorded to metrics), and records each run.

Time is injectable (``clock`` / ``sleep``) so tests drive it deterministically with
NO real waiting and without ``time``-based flakiness. In production, start it once at
app startup; for cron-style external scheduling, call :meth:`run_due` from a cron job
instead of running the thread.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from aprntc.ops.metrics import OpsMetrics, METRICS


@dataclass
class Job:
    name: str
    fn: Callable[[], None]
    interval_s: float
    _next_at: float = 0.0          # epoch seconds when it's next due
    runs: int = 0
    failures: int = 0


class Scheduler:
    """Interval scheduler with fail-isolated jobs + metrics, injectable clock."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        metrics: OpsMetrics | None = None,
    ) -> None:
        import time
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._metrics = metrics or METRICS
        self._jobs: dict[str, Job] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, name: str, fn: Callable[[], None], *, interval_s: float,
            run_immediately: bool = False) -> Job:
        now = self._clock()
        job = Job(name=name, fn=fn, interval_s=interval_s,
                  _next_at=now if run_immediately else now + interval_s)
        self._jobs[name] = job
        return job

    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def run_due(self, *, now: float | None = None) -> int:
        """Run every job whose time has come. Returns how many ran. Fail-isolated.

        Call this from a loop (the background thread) OR directly from an external
        cron — both work, which is why scheduling is testable without real time.
        """
        t = self._clock() if now is None else now
        ran = 0
        for job in self._jobs.values():
            if t >= job._next_at:
                self._run_one(job)
                job._next_at = t + job.interval_s
                ran += 1
        return ran

    def _run_one(self, job: Job) -> None:
        job.runs += 1
        self._metrics.incr(f"job.{job.name}.runs")
        try:
            job.fn()
            self._metrics.mark(f"job.{job.name}.last_success")
        except BaseException as exc:  # noqa: BLE001 - one job must not kill the loop
            job.failures += 1
            self._metrics.record_error(f"job.{job.name}", f"{type(exc).__name__}: {exc}")

    # -- background thread (optional; production startup) ----------------
    def start(self, *, tick_s: float = 1.0) -> None:
        if self._thread is not None:
            raise RuntimeError("scheduler already started")
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                self.run_due()
                self._sleep(tick_s)

        self._thread = threading.Thread(target=_loop, name="aprntc-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
