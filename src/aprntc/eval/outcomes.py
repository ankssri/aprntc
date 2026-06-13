"""Outcome scorers — the ground-truth ANCHOR (highest reliability; ADR 0006).

Domain-specific, deterministic (no LLM), fast. They produce ``outcome``-source
:class:`Label`s that outrank the judge in fusion.

- **support_outcome:** resolved-in-session signal — did the agent actually use a
  tool to ground its answer and avoid an explicit non-answer? (Proxy for "issue
  resolved within session", the locked minutes-latency signal.)
- **rag_outcome:** groundedness / citation-correctness vs the gold set — did the
  answer cite the expected doc(s) and match the reference? Catches hallucination.
"""

from __future__ import annotations

from aprntc.demos.corpus import GoldItem
from aprntc.trajectory.schema import Episode, Label, LabelSource, StepType

_NON_ANSWER = ("i don't know", "i do not know", "cannot help", "can't help", "unable to")


def support_outcome(episode: Episode) -> Label:
    """Score a support episode by resolution signal.

    Heuristic ground truth for the synthetic demo: an answer is "resolved" when the
    agent grounded it on a successful tool result (KB/order) and did not punt.
    Real deployments replace this with the CRM resolved-in-session signal.
    """
    answer = (episode.final_output or "").lower()
    used_grounding = any(
        step.type is StepType.TOOL_CALL and step.tool_result
        for turn in episode.turns
        for step in turn.steps
    )
    punted = any(p in answer for p in _NON_ANSWER)
    resolved = used_grounding and not punted and bool(answer.strip())
    return Label(
        source=LabelSource.OUTCOME,
        score=1.0 if resolved else 0.0,
        rubric_dim="resolved",
        confidence=0.9,
        rationale="grounded + answered" if resolved else "no grounding / punted",
    )


def rag_outcome(episode: Episode, gold: GoldItem) -> Label:
    """Score a RAG episode against its gold item: groundedness + citation + correctness.

    score = mean(citation_ok, retrieval_ok, answer_match). All deterministic.
    """
    answer = (episode.final_output or "")
    answer_low = answer.lower()

    # citation: did the answer cite at least one expected doc id?
    citation_ok = any(doc_id in answer for doc_id in gold.cited_docs)

    # retrieval: did the agent actually retrieve an expected doc? (search_docs step)
    retrieved: set[str] = set()
    for turn in episode.turns:
        for step in turn.steps:
            if step.tool_name == "search_docs" and isinstance(step.tool_result, dict):
                retrieved.update(step.tool_result.get("doc_ids", []))
    retrieval_ok = bool(retrieved & set(gold.cited_docs))

    # correctness: lightweight reference overlap (key terms from the reference present).
    ref_terms = {w.lower().strip(".,") for w in gold.reference_answer.split() if len(w) > 3}
    answer_match = bool(ref_terms) and (len(ref_terms & set(answer_low.split())) / len(ref_terms) >= 0.5)

    score = (int(citation_ok) + int(retrieval_ok) + int(answer_match)) / 3.0
    return Label(
        source=LabelSource.OUTCOME,
        score=score,
        rubric_dim="groundedness",
        confidence=0.9,
        rationale=f"cite={citation_ok} retrieve={retrieval_ok} match={answer_match}",
    )
