"""Bounded retry + exponential backoff for flaky external calls.

ModelArk / VikingDB calls occasionally blip (timeouts, 5xx, rate limits). Wrap them
so a transient failure doesn't drop an episode or abort a nightly run. The sleep
function is injectable (default ``time.sleep``) so tests run instantly + deterministically.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


class RetryError(RuntimeError):
    """Raised when all retry attempts are exhausted; chains the last exception."""

    def __init__(self, attempts: int, last: BaseException) -> None:
        super().__init__(f"failed after {attempts} attempts: {type(last).__name__}: {last}")
        self.attempts = attempts
        self.last = last


def with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call ``fn`` with up to ``attempts`` tries and exponential backoff.

    Retries only ``retry_on`` exceptions; anything else propagates immediately
    (don't retry a 400/validation error). Raises :class:`RetryError` if exhausted.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if i == attempts - 1:
                break
            if on_retry is not None:
                on_retry(i + 1, exc)
            delay = min(base_delay * (2 ** i), max_delay)
            sleep(delay)
    raise RetryError(attempts, last)  # type: ignore[arg-type]
