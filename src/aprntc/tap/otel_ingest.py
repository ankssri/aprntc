"""OTel ingester collector — map OpenTelemetry GenAI spans into Episodes.

For agents instrumented with OpenTelemetry (LangChain/LlamaIndex/CrewAI via
OpenLLMetry/OpenInference): they emit GenAI-convention spans; we map those to our
schema (ADR 0004). This module is pure dict-in/Episode-out — it does NOT run an
OTLP server (that's the OpenTelemetry Collector's job; you point its export at a
small endpoint that calls :func:`spans_to_episodes`). So it's testable offline.

GenAI semantic conventions are still evolving + differ across instrumentations;
we read a tolerant union of the common attribute names (OpenLLMetry `gen_ai.*`,
OpenInference `llm.*`, plus `traceloop.*`). Fidelity = ``partial`` (we get what the
source chose to emit).
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

# Attribute aliases across instrumentations (first match wins).
_MODEL = ("gen_ai.request.model", "gen_ai.response.model", "llm.model_name", "llm.model")
_PROMPT = ("gen_ai.prompt", "llm.input_messages", "traceloop.entity.input", "input.value")
_COMPLETION = ("gen_ai.completion", "llm.output_messages", "traceloop.entity.output", "output.value")
_TOKENS_IN = ("gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens", "llm.token_count.prompt")
_TOKENS_OUT = ("gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens", "llm.token_count.completion")


def _first(attrs: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in attrs and attrs[k] not in (None, ""):
            return attrs[k]
    # also try prefix matches (e.g. gen_ai.prompt.0.content)
    for k in keys:
        for ak in attrs:
            if ak.startswith(k):
                return attrs[ak]
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


def span_to_episode(span: dict[str, Any], *, trace_id: str | None = None) -> Episode | None:
    """Map one GenAI span (``{name, attributes, ...}``) to an Episode, or None if
    it isn't an LLM/agent span we can use."""
    attrs = span.get("attributes") or span.get("attrs") or {}
    name = (span.get("name") or "").lower()

    model = _first(attrs, _MODEL)
    prompt = _first(attrs, _PROMPT)
    completion = _first(attrs, _COMPLETION)
    # only ingest spans that look like a model/agent interaction
    if not (model or prompt or completion or "llm" in name or "chat" in name or "agent" in name):
        return None

    task = _as_text(prompt) or "(unknown task)"
    answer = _as_text(completion) or None

    turn = Turn(turn_index=0)
    if task:
        turn.user_content.append(ContentPart.text_part(task))
    if answer:
        turn.agent_content.append(ContentPart.text_part(answer))
    turn.steps.append(Step(step_index=0, type=StepType.MODEL_CALL,
                           tool_name=str(model) if model else None,
                           source_fidelity=SourceFidelity.PARTIAL))

    tin = _first(attrs, _TOKENS_IN)
    tout = _first(attrs, _TOKENS_OUT)
    return Episode(
        task_input=task,
        collector=Collector.OTEL,
        trace_id=trace_id or span.get("trace_id"),
        model_id=str(model) if model else None,
        turns=[turn],
        final_output=answer,
        tokens_in=int(tin) if _is_num(tin) else None,
        tokens_out=int(tout) if _is_num(tout) else None,
    )


def spans_to_episodes(spans: list[dict[str, Any]]) -> list[Episode]:
    """Map a batch of spans to Episodes, skipping non-LLM spans."""
    out: list[Episode] = []
    for s in spans:
        ep = span_to_episode(s)
        if ep is not None:
            out.append(ep)
    return out


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit())
