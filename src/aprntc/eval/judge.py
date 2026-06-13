"""Pairwise rubric judge — recused (judge ≠ policy), the lowest-reliability signal.

Compares a child answer vs a parent answer on the same task and returns which is
better + a [0,1] score for the child. Bias mitigations baked in (ADR 0002):

* **Recusal enforced** — constructor raises if ``judge_model == policy_model``.
* **Order randomization** — the child is presented as A or B per a caller-supplied
  flag (the orchestrator randomizes), and we map the verdict back. Kills position bias.
* **Rubric + structured output** — the judge must return strict JSON.

The judge is a *prior, never the anchor*: outcomes outrank it in fusion.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from aprntc.providers.base import LLMProvider
from aprntc.trajectory.schema import Label, LabelSource

_RUBRIC = (
    "You are an impartial evaluator. Compare two assistant answers to the SAME user task "
    "on these dimensions: correctness, helpfulness, and conciseness. "
    "Respond with STRICT JSON only: "
    '{"winner": "A" | "B" | "tie", "child_score": <float 0..1>, "rationale": "<one sentence>"}. '
    "child_score is how good the CHILD answer is (0=poor, 1=excellent)."
)


@dataclass
class JudgeVerdict:
    winner: str            # "child" | "parent" | "tie" (already de-mapped from A/B)
    child_score: float     # [0,1]
    rationale: str
    raw: dict[str, Any]


class PairwiseJudge:
    def __init__(self, provider: LLMProvider, *, judge_model: str, policy_model: str) -> None:
        if judge_model == policy_model:
            raise ValueError(
                f"judge_model must differ from policy_model (recused judge); both are {judge_model!r}"
            )
        self._provider = provider
        self._judge_model = judge_model

    def compare(
        self,
        *,
        task: str,
        child_answer: str,
        parent_answer: str,
        child_is_a: bool = True,
    ) -> JudgeVerdict:
        """Judge child vs parent. ``child_is_a`` controls which slot the child occupies
        (the orchestrator randomizes this to defeat position bias)."""
        a, b = (child_answer, parent_answer) if child_is_a else (parent_answer, child_answer)
        messages = [
            {"role": "system", "content": _RUBRIC},
            {"role": "user", "content": f"Task:\n{task}\n\nAnswer A:\n{a}\n\nAnswer B:\n{b}"},
        ]
        # The judge scores from a rubric; it doesn't need extended chain-of-thought.
        # Disable thinking when supported → faster, cheaper, avoids long reasoning stalls.
        result = self._provider.complete(
            model=self._judge_model, messages=messages, thinking="disabled"
        )
        data = _parse_json(result.text)

        raw_winner = str(data.get("winner", "tie")).upper()
        # De-map A/B back to child/parent using which slot the child was in.
        if raw_winner == "TIE":
            winner = "tie"
        elif (raw_winner == "A") == child_is_a:
            winner = "child"
        else:
            winner = "parent"

        score = _clamp01(_as_float(data.get("child_score"), default=0.5))
        return JudgeVerdict(
            winner=winner,
            child_score=score,
            rationale=str(data.get("rationale", "")),
            raw=data,
        )

    def label(self, verdict: JudgeVerdict, *, confidence: float = 0.5) -> Label:
        """Build a ``judge``-source Label from a verdict (for the store)."""
        return Label(
            source=LabelSource.JUDGE,
            score=verdict.child_score,
            rubric_dim="pairwise",
            rationale=verdict.rationale or None,
            confidence=confidence,
            judge_model=self._judge_model,
        )


# ─── parsing helpers (robust to minor LLM JSON noise) ───────────────────────

def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))
