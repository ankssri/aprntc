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

__all__ = ["AgentTap", "EpisodeRecorder", "TurnRecorder", "wrap"]
