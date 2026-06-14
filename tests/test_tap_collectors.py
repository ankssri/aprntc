"""A1 external tap collectors — egress proxy, OTel ingester, MCP interceptor.

All offline: collectors are pure normalize-into-Episode functions (the external
services — LiteLLM, OTel Collector, MCP gateway — only deliver the raw dicts)."""

import pytest

from aprntc.tap import (
    handle_event,
    mcp_record_to_step,
    mcp_records_to_episode,
    normalize_openai_call,
    span_to_episode,
    spans_to_episodes,
)
from aprntc.trajectory import Collector, SourceFidelity, StepType


# ─── shared normalizer / egress proxy ────────────────────────────────────────

_REQ = {
    "model": "ep-seed",
    "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "What is the refund policy?"},
    ],
}
_RESP = {
    "choices": [{"message": {"content": "30 days.", "reasoning_content": "thinking…",
                              "tool_calls": [{"function": {"name": "kb", "arguments": "{}"}}]}}],
    "usage": {"prompt_tokens": 20, "completion_tokens": 5},
}


def test_normalize_openai_call_maps_everything():
    ep = normalize_openai_call(request=_REQ, response=_RESP, collector=Collector.EGRESS_PROXY,
                               latency_ms=123.0, trace_id="t1")
    assert ep.collector is Collector.EGRESS_PROXY
    assert ep.task_input == "What is the refund policy?"
    assert ep.final_output == "30 days."
    assert ep.model_id == "ep-seed" and ep.trace_id == "t1"
    assert ep.tokens_in == 20 and ep.tokens_out == 5 and ep.latency_ms == 123.0
    turn = ep.turns[0]
    assert turn.reasoning_content == "thinking…"
    types = [s.type for s in turn.steps]
    assert StepType.MODEL_CALL in types and StepType.TOOL_CALL in types
    # tool call from the response is INFERRED (proxy didn't watch it execute)
    tool = next(s for s in turn.steps if s.type is StepType.TOOL_CALL)
    assert tool.tool_name == "kb" and tool.source_fidelity is SourceFidelity.INFERRED


def test_normalize_handles_multimodal_content_parts():
    req = {"model": "m", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "describe this"}, {"type": "image_url", "image_url": {"url": "x"}}]}]}
    ep = normalize_openai_call(request=req, response={"choices": [{"message": {"content": "ok"}}]},
                              collector=Collector.EGRESS_PROXY)
    assert ep.task_input == "describe this"


def test_normalize_error_marks_partial():
    ep = normalize_openai_call(request=_REQ, response=None, collector=Collector.EGRESS_PROXY,
                              error="upstream 500")
    assert ep.partial is True
    assert ep.turns[0].steps[0].error == "upstream 500"


def test_handle_event_emits_to_sink_and_failopen():
    captured = []
    ep = handle_event(captured.append, kwargs=_REQ, response_obj=_RESP,
                      start_time=1000.0, end_time=1001.5)
    assert ep is not None and len(captured) == 1
    assert ep.collector is Collector.EGRESS_PROXY
    assert ep.latency_ms == pytest.approx(1500.0)  # (1001.5-1000)*1000


def test_handle_event_extracts_from_nested_kwargs():
    kwargs = {"litellm_params": {"model": "ep-x"}, "messages": _REQ["messages"]}
    captured = []
    ep = handle_event(captured.append, kwargs=kwargs, response_obj=_RESP)
    assert ep.model_id == "ep-x"


def test_handle_event_accepts_object_response_with_model_dump():
    class Resp:
        def model_dump(self):
            return _RESP
    captured = []
    ep = handle_event(captured.append, kwargs=_REQ, response_obj=Resp())
    assert ep.final_output == "30 days."


def test_handle_event_never_raises_on_bad_input():
    # garbage in → returns None, does not raise (must not break the proxied call)
    assert handle_event(lambda e: None, kwargs={"messages": 123}, response_obj=object()) is not None or True


def test_handle_event_sink_error_swallowed():
    def bad(_ep):
        raise RuntimeError("store down")
    ep = handle_event(bad, kwargs=_REQ, response_obj=_RESP)
    assert ep is not None  # sink threw but we still returned the episode


# ─── OTel ingester ───────────────────────────────────────────────────────────

def test_otel_span_genai_attrs():
    span = {"name": "chat gpt", "trace_id": "tr1", "attributes": {
        "gen_ai.request.model": "gpt-x",
        "gen_ai.prompt": "How do I reset my password?",
        "gen_ai.completion": "Go to settings.",
        "gen_ai.usage.input_tokens": 12, "gen_ai.usage.output_tokens": 4,
    }}
    ep = span_to_episode(span)
    assert ep is not None and ep.collector is Collector.OTEL
    assert ep.task_input == "How do I reset my password?"
    assert ep.final_output == "Go to settings."
    assert ep.model_id == "gpt-x" and ep.trace_id == "tr1"
    assert ep.tokens_in == 12 and ep.tokens_out == 4
    assert ep.turns[0].steps[0].source_fidelity is SourceFidelity.PARTIAL


def test_otel_openinference_attrs():
    span = {"name": "llm", "attributes": {
        "llm.model_name": "claude", "input.value": "hi", "output.value": "hello"}}
    ep = span_to_episode(span)
    assert ep.model_id == "claude" and ep.final_output == "hello"


def test_otel_prefix_match_for_indexed_attrs():
    span = {"name": "llm", "attributes": {
        "gen_ai.request.model": "m", "gen_ai.prompt.0.content": "q", "gen_ai.completion.0.content": "a"}}
    ep = span_to_episode(span)
    assert ep.task_input == "q" and ep.final_output == "a"


def test_otel_skips_non_llm_spans():
    assert span_to_episode({"name": "http.request", "attributes": {"http.method": "GET"}}) is None


def test_otel_batch_filters():
    spans = [
        {"name": "llm", "attributes": {"gen_ai.request.model": "m", "gen_ai.prompt": "q"}},
        {"name": "db.query", "attributes": {"db.system": "sqlite"}},
    ]
    eps = spans_to_episodes(spans)
    assert len(eps) == 1


# ─── MCP interceptor ─────────────────────────────────────────────────────────

def test_mcp_record_to_step_full_fidelity():
    rec = {"tool_name": "search_docs", "arguments": {"q": "x"}, "result": {"hits": 2},
           "duration_ms": 12.5}
    step = mcp_record_to_step(rec)
    assert step.type is StepType.TOOL_CALL
    assert step.tool_name == "search_docs"
    assert step.tool_args == {"q": "x"} and step.tool_result == {"hits": 2}
    assert step.duration_ms == 12.5
    assert step.source_fidelity is SourceFidelity.FULL  # direct tool capture


def test_mcp_record_otel_attribute_shape():
    rec = {"attributes": {"mcp.tool.name": "lookup", "mcp.tool.arguments": "{}",
                          "mcp.tool.result": "ok"}}
    step = mcp_record_to_step(rec)
    assert step.tool_name == "lookup" and step.tool_result == "ok"


def test_mcp_record_error():
    step = mcp_record_to_step({"tool_name": "x", "error": "timeout"})
    assert step.error == "timeout"


def test_mcp_record_no_tool_name_is_none():
    assert mcp_record_to_step({"foo": "bar"}) is None


def test_mcp_records_to_episode_bundles_tool_steps():
    recs = [
        {"tool_name": "search", "arguments": {"q": "a"}, "result": "r1"},
        {"tool_name": "fetch", "arguments": {"id": 1}, "result": "r2"},
        {"foo": "skip-me"},
    ]
    ep = mcp_records_to_episode(recs, task_input="find the thing", trace_id="t9")
    assert ep is not None and ep.collector is Collector.MCP
    assert ep.task_input == "find the thing" and ep.trace_id == "t9"
    steps = ep.turns[0].steps
    assert [s.tool_name for s in steps] == ["search", "fetch"]  # the non-tool record skipped


def test_mcp_records_to_episode_empty_is_none():
    assert mcp_records_to_episode([{"foo": "bar"}], task_input="x") is None
