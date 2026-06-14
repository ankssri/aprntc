"""Egress-proxy collector — tap model traffic via a self-hosted LiteLLM gateway.

For agents we DON'T own (closed-source): point the agent's model ``base_url`` at a
LiteLLM proxy and register this `CustomLogger`. LiteLLM forwards the call and hands
us the request (``kwargs``) + ``response_obj`` per call; we normalize → Episode →
sink. LiteLLM owns TLS/SSE/retries/multi-provider (ADR 0004).

Fidelity is ``inferred`` — the proxy sees model traffic, not local tool execution.

The litellm dependency is the ``[proxy]`` extra; this module never hard-imports it.
:class:`AprntcProxyLogger` extends litellm's ``CustomLogger`` only if it's installed
(:func:`make_proxy_logger`), but :func:`handle_event` — the pure normalize+emit core —
is testable offline with no litellm.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from aprntc.tap.normalize import normalize_openai_call
from aprntc.trajectory.schema import Collector, Episode

Sink = Callable[[Episode], Any]


def handle_event(
    sink: Sink,
    *,
    kwargs: dict[str, Any],
    response_obj: Any,
    start_time: float | None = None,
    end_time: float | None = None,
    error: str | None = None,
) -> Episode | None:
    """Normalize one LiteLLM logging event into an Episode and emit it (fail-open).

    ``kwargs`` is LiteLLM's call context (has ``messages``/``model`` or nests them
    under ``optional_params``/``litellm_params``); ``response_obj`` is the provider
    response (a dict, or an object with ``.model_dump()``/``.dict()``).
    Returns the Episode (also passed to ``sink``), or ``None`` on a fatal mapping
    error — never raises (must not break the proxied call).
    """
    try:
        request = _extract_request(kwargs)
        response = _to_dict(response_obj)
        latency = None
        if start_time is not None and end_time is not None:
            latency = (end_time - start_time) * 1000
        episode = normalize_openai_call(
            request=request, response=response, collector=Collector.EGRESS_PROXY,
            error=error, latency_ms=latency,
        )
    except BaseException:  # noqa: BLE001 - normalization must never break the call
        return None
    try:
        sink(episode)
    except BaseException:  # noqa: BLE001 - fail-open sink
        pass
    return episode


def _extract_request(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Pull messages + model out of LiteLLM's kwargs (shape varies by version)."""
    op = kwargs.get("optional_params") or {}
    lp = kwargs.get("litellm_params") or {}
    return {
        "messages": kwargs.get("messages") or op.get("messages") or [],
        "model": kwargs.get("model") or lp.get("model") or op.get("model") or "",
    }


def _to_dict(obj: Any) -> dict[str, Any] | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    for attr in ("model_dump", "dict", "json"):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                out = fn()
                return out if isinstance(out, dict) else None
            except BaseException:
                continue
    return None


def make_proxy_logger(sink: Sink):
    """Build a LiteLLM ``CustomLogger`` bound to ``sink`` (needs the ``[proxy]`` extra).

    Register the returned instance via ``litellm.callbacks = [logger]``. Raises a
    clear error if litellm isn't installed.
    """
    try:
        from litellm.integrations.custom_logger import CustomLogger  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - guidance path
        raise ModuleNotFoundError(
            "egress proxy needs litellm — install the proxy extra: pip install 'aprntc[proxy]'"
        ) from exc

    class AprntcProxyLogger(CustomLogger):  # type: ignore[misc]
        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            handle_event(sink, kwargs=kwargs, response_obj=response_obj,
                         start_time=_ts(start_time), end_time=_ts(end_time))

        def log_failure_event(self, kwargs, response_obj, start_time, end_time):
            handle_event(sink, kwargs=kwargs, response_obj=response_obj,
                         start_time=_ts(start_time), end_time=_ts(end_time),
                         error=str(kwargs.get("exception") or "call failed"))

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            handle_event(sink, kwargs=kwargs, response_obj=response_obj,
                         start_time=_ts(start_time), end_time=_ts(end_time))

        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            handle_event(sink, kwargs=kwargs, response_obj=response_obj,
                         start_time=_ts(start_time), end_time=_ts(end_time),
                         error=str(kwargs.get("exception") or "call failed"))

    return AprntcProxyLogger()


def _ts(t: Any) -> float | None:
    """LiteLLM passes datetimes or floats for start/end; normalize to epoch seconds."""
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return float(t)
    ts = getattr(t, "timestamp", None)
    if callable(ts):
        try:
            return ts()
        except BaseException:
            return None
    return None
