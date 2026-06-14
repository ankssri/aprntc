"""Outcome scorer for the BytePlus support agent — the ground-truth anchor.

Deterministic (no LLM). Scores an answered episode against a :class:`GoldQA` on
three axes the thin parent often misses:
  - **grounded:** did it actually retrieve docs (a search_docs step with results)?
  - **cited:** does the answer cite a source ([doc › section]) when expected?
  - **correct:** does the answer contain the reference fact's key terms?
mean of the three → reward in [0,1].
"""

from __future__ import annotations

import re

from aprntc.demos.byteplus.gold import GoldQA
from aprntc.trajectory.schema import Episode, Label, LabelSource, StepType

_CITE = re.compile(r"\[[^\]]+›[^\]]+\]")  # [doc › section]
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "is", "are", "with"}


def _key_terms(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9_]+", text.lower())
            if len(w) > 2 and w not in _STOP}


def byteplus_outcome(episode: Episode, gold: GoldQA) -> Label:
    answer = episode.final_output or ""
    answer_low = answer.lower()

    grounded = any(
        s.type is StepType.TOOL_CALL and s.tool_name == "search_docs" and s.tool_result
        for turn in episode.turns
        for s in turn.steps
    )
    cited = (not gold.must_cite) or bool(_CITE.search(answer))

    ref = _key_terms(gold.reference)
    answer_terms = set(answer_low.split())
    correct = bool(ref) and (len(ref & answer_terms) / len(ref) >= 0.5)

    score = (int(grounded) + int(cited) + int(correct)) / 3.0
    return Label(
        source=LabelSource.OUTCOME,
        score=score,
        rubric_dim="byteplus_support",
        confidence=0.9,
        rationale=f"grounded={grounded} cited={cited} correct={correct}",
    )
