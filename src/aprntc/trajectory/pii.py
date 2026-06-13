"""PII scrubbing — runs at INGEST, before any trajectory is persisted.

Invariant (CLAUDE.md): scrub PII at ingest; never persist or embed raw PII.
This is a pragmatic, dependency-light regex scrubber for the MVP (synthetic demo
data). It is intentionally conservative and easily extended; a heavier NER-based
scrubber can replace it behind the same ``scrub_episode`` entry point later.

Scrubs across all free-text the schema carries: task_input, final_output,
input_context, content-part text, reasoning_content, tool args/results, and
label rationales. Media is by reference (never raw), so only its ref/text is seen.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from aprntc.trajectory.schema import (
    ContentPart,
    Episode,
    Label,
    PiiStatus,
    Step,
    Turn,
)

# Order matters: email before the generic "@" cases, etc. Each pattern → placeholder.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    # credit-card-like 13-16 digit runs (optionally space/dash separated)
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[CARD]"),
    # US SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    # international-ish phone numbers
    (re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)"), "[PHONE]"),
    # IPv4
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP]"),
    # bearer/api keys and long opaque tokens
    (re.compile(r"\b(?:sk|pk|gho|ghp|AKIA)[-_A-Za-z0-9]{12,}\b"), "[SECRET]"),
]


def scrub_text(text: str | None) -> str | None:
    """Replace recognized PII spans in a string. ``None`` passes through."""
    if not text:
        return text
    out = text
    for pattern, placeholder in _PATTERNS:
        out = pattern.sub(placeholder, out)
    return out


def _scrub_value(value: Any) -> Any:
    """Recursively scrub strings inside arbitrary tool_args / tool_result values."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub_value(v) for k, v in value.items()}
    return value


def _scrub_content(part: ContentPart) -> ContentPart:
    return replace(part, text=scrub_text(part.text))


def _scrub_step(step: Step) -> Step:
    return replace(
        step,
        tool_args=_scrub_value(step.tool_args),
        tool_result=_scrub_value(step.tool_result),
        error=scrub_text(step.error),
    )


def _scrub_turn(turn: Turn) -> Turn:
    return replace(
        turn,
        user_content=[_scrub_content(c) for c in turn.user_content],
        agent_content=[_scrub_content(c) for c in turn.agent_content],
        reasoning_content=scrub_text(turn.reasoning_content),
        steps=[_scrub_step(s) for s in turn.steps],
    )


def _scrub_label(label: Label) -> Label:
    return replace(label, rationale=scrub_text(label.rationale))


def scrub_episode(episode: Episode) -> Episode:
    """Return a scrubbed copy of an episode with ``pii_status = scrubbed``.

    Idempotent: re-scrubbing already-scrubbed text is a no-op. The original is
    not mutated (returns a new Episode).
    """
    scrubbed = replace(
        episode,
        task_input=scrub_text(episode.task_input) or episode.task_input,
        final_output=scrub_text(episode.final_output),
        input_context=[scrub_text(c) or c for c in episode.input_context],
        turns=[_scrub_turn(t) for t in episode.turns],
        labels=[_scrub_label(l) for l in episode.labels],
        pii_status=PiiStatus.SCRUBBED,
    )
    return scrubbed
