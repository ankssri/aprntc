"""Lightweight in-process ops metrics so aprntc can observe itself.

Counters + last-event timestamps, thread-safe (the web API + scheduler touch it
from different threads). Not a full metrics backend — a minimal health snapshot
surfaced at ``/api/ops`` and used by the scheduler to record job runs. For real
deployments these can be exported to Prometheus/etc. later.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpsMetrics:
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    counters: dict[str, int] = field(default_factory=dict)
    last_event: dict[str, str] = field(default_factory=dict)   # name -> ISO ts
    last_error: dict[str, str] = field(default_factory=dict)   # name -> message

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self.counters[name] = self.counters.get(name, 0) + n

    def mark(self, name: str, *, ts: str | None = None) -> None:
        with self._lock:
            self.last_event[name] = ts or _now()

    def record_error(self, name: str, message: str) -> None:
        with self._lock:
            self.counters[f"{name}.errors"] = self.counters.get(f"{name}.errors", 0) + 1
            self.last_error[name] = message[:300]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "last_event": dict(self.last_event),
                "last_error": dict(self.last_error),
            }

    def reset(self) -> None:
        with self._lock:
            self.counters.clear()
            self.last_event.clear()
            self.last_error.clear()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# Process-wide default instance (the web API + scheduler share this).
METRICS = OpsMetrics()
