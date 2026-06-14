"""Normalizers — turn foreign capture formats into the canonical Trajectory schema.

Each external collector (egress proxy, OTel, MCP) captures data in a different
shape; these pure functions convert each into an :class:`Episode` so the rest of
the system never sees collector-specific formats (ADR 0004, 0007).

Pure + stdlib-only → fully unit-testable offline without the external service.
"""

from __future__ import annotations

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


def _messages_to_turns(messages: list[dict[str, Any]], answer: str | None,
                       reasoning: str | None, tool_calls: list[dict[str, Any]],
                       fidelity: SourceFidelity) -> tuple[str, list[Turn]]:
    """Build a single task-turn from an OpenAI-style messages array + the response.

    Returns ``(task_input, turns)``. The last user message is the task; the answer
    is the assistant reply. Tool calls present in the response become inferred steps.
    """
    user_msgs = [m for m in messages if m.get("role") == "user"]
    task = ""
    if user_msgs:
        task = _content_text(user_msgs[-1].get("content"))

    turn = Turn(turn_index=0)
    for m in messages:
        if m.get("role") == "user":
            turn.user_content.append(ContentPart.text_part(_content_text(m.get("content"))))
    if answer:
        turn.agent_content.append(ContentPart.text_part(answer))
    if reasoning:
        turn.reasoning_content = reasoning

    step_idx = 0
    turn.steps.append(Step(step_index=step_idx, type=StepType.MODEL_CALL,
                           source_fidelity=fidelity))
    step_idx += 1
    for tc in tool_calls or []:
        fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
        turn.steps.append(Step(
            step_index=step_idx,
            type=StepType.TOOL_CALL,
            tool_name=fn.get("name") or tc.get("name") if isinstance(tc, dict) else None,
            tool_args=fn.get("arguments") or tc.get("arguments") if isinstance(tc, dict) else None,
            source_fidelity=SourceFidelity.INFERRED,  # from the response, not direct execution
        ))
        step_idx += 1
    return task or "(unknown task)", [turn]


def _content_text(content: Any) -> str:
    """OpenAI content can be a string or a list of parts; extract the text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text", ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(parts)
    return str(content)


def normalize_openai_call(
    *,
    request: dict[str, Any],
    response: dict[str, Any] | None,
    collector: Collector,
    error: str | None = None,
    latency_ms: float | None = None,
    trace_id: str | None = None,
    fidelity: SourceFidelity = SourceFidelity.INFERRED,
) -> Episode:
    """Normalize one OpenAI-compatible chat call (request + response) into an Episode.

    Used by the egress-proxy collector (LiteLLM gives us exactly this shape). The
    proxy sees model traffic but not local tool execution → fidelity defaults to
    ``inferred`` (tool calls reconstructed from the response, no timing).
    """
    messages = request.get("messages", []) or []
    model = request.get("model", "")

    answer = reasoning = None
    tool_calls: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    if response:
        choice = (response.get("choices") or [{}])[0]
        msg = choice.get("message", {}) or {}
        answer = msg.get("content")
        reasoning = msg.get("reasoning_content")
        tool_calls = msg.get("tool_calls") or []
        usage = response.get("usage") or {}

    task, turns = _messages_to_turns(messages, answer, reasoning, tool_calls, fidelity)
    if error and turns:
        turns[0].steps[0].error = error
        turns[0].partial = True

    return Episode(
        task_input=task,
        collector=collector,
        trace_id=trace_id,
        model_id=model,
        turns=turns,
        final_output=answer,
        latency_ms=latency_ms,
        tokens_in=usage.get("prompt_tokens"),
        tokens_out=usage.get("completion_tokens"),
        partial=bool(error),
    )
