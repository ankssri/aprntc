"""AgentTap — captures a parent agent's behavior into canonical Trajectories.

Collectors intercept at stable protocol boundaries and normalize into the one
``Trajectory`` schema (ADR 0004, 0007). This package holds the tap core
(``AgentTap`` + ``EpisodeRecorder``) and the collectors. The SDK wrapper
collector (full-fidelity, our-code path) ships first; LiteLLM proxy / OTel / MCP
collectors plug in behind the same core later.

Invariant: the tap is **fail-open** — recording must never slow or break the
parent agent (CLAUDE.md).
"""

from aprntc.tap.core import AgentTap, EpisodeRecorder, TurnRecorder
from aprntc.tap.sdk_wrapper import wrap
from aprntc.tap.normalize import normalize_openai_call
from aprntc.tap.egress_proxy import handle_event, make_proxy_logger
from aprntc.tap.otel_ingest import span_to_episode, spans_to_episodes
from aprntc.tap.mcp_ingest import mcp_record_to_step, mcp_records_to_episode
from aprntc.tap.a2a_ingest import a2a_task_to_episode, a2a_tasks_to_episodes

__all__ = [
    # core
    "AgentTap", "EpisodeRecorder", "TurnRecorder", "wrap",
    # collectors
    "normalize_openai_call",          # shared normalizer
    "handle_event", "make_proxy_logger",   # egress proxy (LiteLLM)
    "span_to_episode", "spans_to_episodes",  # OTel ingester
    "mcp_record_to_step", "mcp_records_to_episode",  # MCP interceptor
    "a2a_task_to_episode", "a2a_tasks_to_episodes",  # A2A interceptor (agent boundary)
]
