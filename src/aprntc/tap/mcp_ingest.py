"""MCP interceptor collector — capture tool calls from an MCP gateway's logs.

For agents whose tools are MCP-based: run an OSS MCP gateway (e.g. IBM ContextForge)
between the agent and its MCP servers; it logs every tool call+result. We map those
records to **tool steps** (ADR 0004). Unlike the model collectors, MCP gives the
*tool* boundary — direct tool name/args/result + timing (high fidelity for tools).

ContextForge exports OTel, so records can arrive either as OTel-style spans or as
plain gateway log dicts; :func:`mcp_record_to_step` accepts a tolerant union. Pure
dict-in → Step/Episode-out, testable offline.
"""

from __future__ import annotations

import json
from typing import Any

from aprntc.trajectory.schema import (
    Collector,
    Episode,
    SourceFidelity,
    Step,
    StepType,
    Turn,
)

_TOOL_NAME = ("mcp.tool.name", "tool.name", "tool_name", "name", "method")
_TOOL_ARGS = ("mcp.tool.arguments", "tool.arguments", "arguments", "params", "input")
_TOOL_RESULT = ("mcp.tool.result", "tool.result", "result", "output", "response")
_DURATION = ("duration_ms", "mcp.tool.duration_ms", "elapsed_ms")
_ERROR = ("error", "mcp.tool.error", "exception")


def _first(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    attrs = rec.get("attributes") or rec.get("attrs") or {}
    for src in (rec, attrs):
        for k in keys:
            if k in src and src[k] not in (None, ""):
                return src[k]
    return None


def mcp_record_to_step(rec: dict[str, Any], *, step_index: int = 0) -> Step | None:
    """Map one MCP gateway record to a ``tool_call`` Step (direct, full fidelity)."""
    name = _first(rec, _TOOL_NAME)
    if not name:
        return None
    dur = _first(rec, _DURATION)
    return Step(
        step_index=step_index,
        type=StepType.TOOL_CALL,
        tool_name=str(name),
        tool_args=_first(rec, _TOOL_ARGS),
        tool_result=_first(rec, _TOOL_RESULT),
        duration_ms=float(dur) if isinstance(dur, (int, float)) else None,
        error=_coerce_err(_first(rec, _ERROR)),
        source_fidelity=SourceFidelity.FULL,  # direct tool boundary capture
    )


def mcp_records_to_episode(
    records: list[dict[str, Any]],
    *,
    task_input: str,
    trace_id: str | None = None,
) -> Episode | None:
    """Bundle a session's MCP tool-call records into one Episode (tool steps only).

    Returns None if no usable tool records. (Model calls for the same session come
    from the egress proxy / OTel; correlation across collectors is best-effort —
    ADR 0005.)
    """
    turn = Turn(turn_index=0)
    idx = 0
    for rec in records:
        step = mcp_record_to_step(rec, step_index=idx)
        if step is not None:
            turn.steps.append(step)
            idx += 1
    if not turn.steps:
        return None
    return Episode(
        task_input=task_input or "(mcp session)",
        collector=Collector.MCP,
        trace_id=trace_id,
        turns=[turn],
    )


def _coerce_err(v: Any) -> str | None:
    if v in (None, "", False):
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(v)
