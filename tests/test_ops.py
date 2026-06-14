"""B3 ops — retry/backoff, scheduler (fail-isolated, injectable clock), metrics, /api/ops."""

import pytest

from aprntc.ops import OpsMetrics, RetryError, Scheduler, with_retry


# ─── retry ───────────────────────────────────────────────────────────────────

def test_retry_succeeds_first_try():
    calls = []
    out = with_retry(lambda: calls.append(1) or "ok", sleep=lambda _s: None)
    assert out == "ok" and len(calls) == 1


def test_retry_recovers_after_failures():
    state = {"n": 0}
    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise TimeoutError("blip")
        return "recovered"
    slept = []
    out = with_retry(flaky, attempts=3, sleep=slept.append)
    assert out == "recovered" and state["n"] == 3
    assert len(slept) == 2  # backoff slept between the 2 failures


def test_retry_exhausts_and_raises_retryerror():
    def always_fail():
        raise ConnectionError("down")
    with pytest.raises(RetryError) as ei:
        with_retry(always_fail, attempts=3, sleep=lambda _s: None)
    assert ei.value.attempts == 3 and isinstance(ei.value.last, ConnectionError)


def test_retry_does_not_retry_unlisted_exceptions():
    calls = []
    def bad_request():
        calls.append(1)
        raise ValueError("400 — don't retry me")
    with pytest.raises(ValueError):
        with_retry(bad_request, attempts=5, retry_on=(TimeoutError,), sleep=lambda _s: None)
    assert len(calls) == 1  # propagated immediately, no retries


def test_retry_backoff_is_capped():
    delays = []
    def fail():
        raise TimeoutError()
    with pytest.raises(RetryError):
        with_retry(fail, attempts=6, base_delay=1.0, max_delay=4.0, sleep=delays.append)
    assert max(delays) <= 4.0  # exponential but capped


# ─── scheduler (injectable clock — no real waiting) ──────────────────────────

class FakeClock:
    def __init__(self):
        self.t = 0.0
    def __call__(self):
        return self.t
    def advance(self, dt):
        self.t += dt


def test_scheduler_runs_job_when_due():
    clk = FakeClock()
    sch = Scheduler(clock=clk, metrics=OpsMetrics())
    runs = []
    sch.add("distill", lambda: runs.append(clk.t), interval_s=10)
    assert sch.run_due() == 0          # not due yet (next at t=10)
    clk.advance(10)
    assert sch.run_due() == 1 and runs == [10]
    clk.advance(9); assert sch.run_due() == 0   # not yet
    clk.advance(1); assert sch.run_due() == 1   # due again at t=20


def test_scheduler_run_immediately():
    clk = FakeClock()
    sch = Scheduler(clock=clk, metrics=OpsMetrics())
    runs = []
    sch.add("now", lambda: runs.append(1), interval_s=100, run_immediately=True)
    assert sch.run_due() == 1 and runs == [1]


def test_scheduler_is_fail_isolated():
    clk = FakeClock()
    m = OpsMetrics()
    sch = Scheduler(clock=clk, metrics=m)
    good_runs = []
    sch.add("boom", lambda: (_ for _ in ()).throw(RuntimeError("job crashed")),
            interval_s=5, run_immediately=True)
    sch.add("good", lambda: good_runs.append(1), interval_s=5, run_immediately=True)
    sch.run_due()
    # the crashing job didn't stop the good one
    assert good_runs == [1]
    snap = m.snapshot()
    assert snap["counters"].get("job.boom.errors", 0) == 1
    assert "job.boom" in snap["last_error"]
    # job objects track their own counts
    boom = next(j for j in sch.jobs() if j.name == "boom")
    assert boom.runs == 1 and boom.failures == 1


def test_scheduler_background_thread_runs(monkeypatch):
    # real thread but fast tick; verify it fires at least once then stops cleanly
    import time
    sch = Scheduler(metrics=OpsMetrics())
    fired = []
    sch.add("tick", lambda: fired.append(1), interval_s=0.0, run_immediately=True)
    sch.start(tick_s=0.01)
    time.sleep(0.05)
    sch.stop()
    assert len(fired) >= 1


# ─── metrics ─────────────────────────────────────────────────────────────────

def test_metrics_counters_and_snapshot():
    m = OpsMetrics()
    m.incr("a"); m.incr("a", 2); m.mark("job.x.last_success")
    m.record_error("job.y", "boom")
    snap = m.snapshot()
    assert snap["counters"]["a"] == 3
    assert "job.x.last_success" in snap["last_event"]
    assert snap["counters"]["job.y.errors"] == 1 and "boom" in snap["last_error"]["job.y"]


def test_metrics_thread_safe_increment():
    import threading
    m = OpsMetrics()
    def bump():
        for _ in range(1000):
            m.incr("c")
    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert m.snapshot()["counters"]["c"] == 4000  # no lost updates


# ─── /api/ops endpoint ───────────────────────────────────────────────────────

def test_ops_endpoint(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aprntc.web.app import AppState, create_app
    from aprntc.ops import METRICS

    METRICS.reset()
    METRICS.incr("job.distill.runs", 2)
    c = TestClient(create_app(AppState(lineage_path=str(tmp_path/"l.json"),
                                       bundle_path=str(tmp_path/"b.json"))))
    body = c.get("/api/ops").json()
    assert body["counters"]["job.distill.runs"] == 2
    assert "episodes" in body
