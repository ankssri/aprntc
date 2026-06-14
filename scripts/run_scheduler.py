"""Run aprntc's autonomous loop on a schedule (B3) — the 'nightly' cadence, live.

Registers a distillation job on the Scheduler and runs it forever. In production
this runs as a long-lived process (or call scheduler.run_due() from cron instead).
Needs real ModelArk keys for the live distill step.

  .venv/bin/python scripts/run_scheduler.py            # default: every 24h
  APRNTC_DISTILL_INTERVAL_S=60 .venv/bin/python scripts/run_scheduler.py   # demo: 60s
"""

from __future__ import annotations

import os
import sys
import time

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.distill import Distiller
from aprntc.ops import METRICS, Scheduler, with_retry
from aprntc.trajectory import TrajectoryStore


def main() -> int:
    s = Settings.from_env()
    try:
        s.modelark.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    store = TrajectoryStore("aprntc.db")
    client = ModelArkClient(s.modelark)
    distiller = Distiller(client, model=s.modelark.policy_model)
    interval = float(os.environ.get("APRNTC_DISTILL_INTERVAL_S", 24 * 3600))

    def nightly_distill() -> None:
        # retry the (network-bound) distill so a transient blip doesn't skip the run
        result = with_retry(lambda: distiller.distill(store, generation=1), attempts=3)
        METRICS.incr("distill.lessons", len(result.lessons))
        print(f"[distill] mined {len(result.lessons)} lessons "
              f"({result.n_directives} directives, {result.n_exemplars} exemplars, "
              f"{result.n_failure} failure-patterns)")

    sch = Scheduler()
    sch.add("nightly_distill", nightly_distill, interval_s=interval, run_immediately=True)
    print(f"Scheduler running: distill every {interval:.0f}s. Ctrl-C to stop.")
    sch.start(tick_s=1.0)
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        sch.stop()
        client.close(); store.close()
        print("\nstopped.", "metrics:", METRICS.snapshot()["counters"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
