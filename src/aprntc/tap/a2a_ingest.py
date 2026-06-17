"""A2A interceptor collector — capture agent-to-agent tasks/artifacts as Episodes.

For multi-agent systems where one agent delegates work to another over the
**Agent-to-Agent (A2A)** protocol: a client sends a *Task* (a message) to a remote
agent, which works and returns *Artifacts* plus a terminal status. We map one A2A
Task to one Episode at the **agent boundary** (ADR 0004) — the coarsest tap.
Granularity is task/artifact-level: we see what was delegated and what came back,
but the remote agent's *internal* tool calls are not visible to the caller, so tool
tracking is the weakest of any collector (``SourceFidelity.COARSE``). The delegation
itself is recorded as a single ``HANDOFF`` step.

Like the other external collectors this is a **pure normalizer** — the A2A
transport / SDK only delivers the raw Task dict, so the mapping is fully unit-tested
offline and there is no hard A2A dependency. We read a tolerant union of field names
across A2A revisions (``id``/``taskId``, ``contextId``/``sessionId``, ``history``/
``messages``, part ``kind``/``type``), first match wins.
"""

from __future__ import annotations

import json
from typing import Any

from aprntc.trajectory.schema import (
    Collector,
    ContentPart,
    Episode,
    SourceFidelity,
    Step,
    StepType,
    Turn,
)

_TASK_ID = ("id", "taskId", "task_id")
_CONTEXT_ID = ("contextId", "context_id", "sessionId", "session_id")
_AGENT = ("agent", "agentName", "agent_name", "skill", "remote_agent", "to")
_ARTIFACTS = ("artifacts",)
_HISTORY = ("history", "messages")
_STATUS = ("status",)
_INPUT_MSG = ("message", "input", "request")
_TERMINAL_FAIL = ("failed", "rejected", "canceled", "cancelled", "error")


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] not in (None, "", [], {}):
            return d[k]
    return None


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _part_text(part: Any) -> str:
    """Render one A2A message/artifact part. Media is referenced, never inlined."""
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return _as_text(part)
    if part.get("text"):
        return str(part["text"])
    kind = str(part.get("kind") or part.get("type") or "").lower()
    if kind == "file" or "file" in part:
        f = part.get("file") or {}
        ref = f.get("uri") or f.get("name") or f.get("mimeType") or "file"
        return f"[file: {ref}]"
    if kind == "data" or "data" in part:
        return _as_text(part.get("data"))
    return _as_text(part)


def _parts_text(parts: Any) -> str:
    if parts is None:
        return ""
    if isinstance(parts, (str, dict)):
        parts = [parts]
    if not isinstance(parts, list):
        return _as_text(parts)
    return "\n".join(t for t in (_part_text(p) for p in parts) if t)


def _message_text(msg: Any) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        parts = msg.get("parts")
        if parts is None:
            parts = msg.get("content")
        if parts is not None:
            return _parts_text(parts)
        if msg.get("text"):
            return str(msg["text"])
        return _as_text(msg)
    return _as_text(msg)


def _input_text(task: dict[str, Any]) -> str:
    for k in _INPUT_MSG:
        if task.get(k):
            t = _message_text(task[k])
            if t:
                return t
    hist = _first(task, _HISTORY)
    if isinstance(hist, list):
        for m in hist:  # prefer the first client/user message
            if isinstance(m, dict) and str(m.get("role", "")).lower() in ("user", "client"):
                t = _message_text(m)
                if t:
                    return t
        for m in hist:  # else the first message of any role
            t = _message_text(m)
            if t:
                return t
    return ""


def _artifact_text(task: dict[str, Any]) -> str:
    arts = _first(task, _ARTIFACTS)
    chunks: list[str] = []
    if isinstance(arts, list):
        for a in arts:
            if isinstance(a, dict):
                t = _parts_text(a.get("parts") if a.get("parts") is not None else a.get("content"))
                name = a.get("name")
                if t:
                    chunks.append(f"{name}: {t}" if name else t)
            else:
                chunks.append(_as_text(a))
    out = "\n".join(c for c in chunks if c)
    if out:
        return out
    hist = _first(task, _HISTORY)  # fallback: last agent message
    if isinstance(hist, list):
        for m in reversed(hist):
            if isinstance(m, dict) and str(m.get("role", "")).lower() in ("agent", "assistant"):
                t = _message_text(m)
                if t:
                    return t
    return ""


def _status(task: dict[str, Any]) -> tuple[str, str]:
    """Return (state, message_text) from the task's terminal status."""
    st = _first(task, _STATUS)
    if isinstance(st, dict):
        state = str(st.get("state") or st.get("status") or "").lower()
        return state, _message_text(st.get("message"))
    if isinstance(st, str):
        return st.lower(), ""
    return str(task.get("state") or "").lower(), ""


def a2a_task_to_episode(task: dict[str, Any], *, trace_id: str | None = None) -> Episode | None:
    """Map one A2A Task to an Episode (a single ``HANDOFF`` step, coarse fidelity).

    Returns None if the task carries neither an input message nor any artifact —
    i.e. nothing learnable. The remote agent's internal tool calls are invisible at
    this boundary by design (ADR 0005); correlation with finer collectors is
    best-effort.
    """
    if not isinstance(task, dict):
        return None
    input_text = _input_text(task)
    output_text = _artifact_text(task)
    if not (input_text or output_text):
        return None

    state, status_msg = _status(task)
    failed = state in _TERMINAL_FAIL
    err = (status_msg or f"a2a task {state}") if failed else None
    agent = _first(task, _AGENT)

    turn = Turn(turn_index=0)
    if input_text:
        turn.user_content.append(ContentPart.text_part(input_text))
    if output_text:
        turn.agent_content.append(ContentPart.text_part(output_text))
    turn.steps.append(
        Step(
            step_index=0,
            type=StepType.HANDOFF,
            tool_name=str(agent) if agent else None,
            tool_args={"task": input_text} if input_text else None,
            tool_result=output_text or None,
            error=err,
            source_fidelity=SourceFidelity.COARSE,  # agent boundary: task/artifact only
        )
    )
    return Episode(
        task_input=input_text or "(a2a task)",
        collector=Collector.A2A,
        trace_id=trace_id or _first(task, _TASK_ID) or _first(task, _CONTEXT_ID),
        turns=[turn],
        final_output=output_text or None,
    )


def a2a_tasks_to_episodes(tasks: list[dict[str, Any]]) -> list[Episode]:
    """Map a batch of A2A Tasks to Episodes, skipping empty/unusable ones."""
    out: list[Episode] = []
    for t in tasks:
        ep = a2a_task_to_episode(t)
        if ep is not None:
            out.append(ep)
    return out
