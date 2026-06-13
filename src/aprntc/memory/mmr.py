"""Maximal Marginal Relevance (MMR) — diversify retrieved lessons to prevent bloat.

Picks items that are relevant to the query yet dissimilar to already-picked items,
balancing the two with ``lambda_`` (1.0 = pure relevance, 0.0 = pure diversity).
Pure function (stdlib only); reused by any MemoryStore implementation.
"""

from __future__ import annotations

import math
from typing import Sequence


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def mmr_select(
    query: Sequence[float],
    candidates: list[tuple[int, Sequence[float], float]],
    *,
    k: int,
    lambda_: float = 0.7,
) -> list[int]:
    """Select up to ``k`` candidate indices by MMR.

    ``candidates`` = list of ``(id, embedding, relevance)``. ``relevance`` is a
    precomputed query-relevance score (e.g. the store's similarity). Returns the
    chosen ids in selection order.
    """
    if k <= 0 or not candidates:
        return []
    remaining = list(candidates)
    selected: list[tuple[int, Sequence[float], float]] = []
    chosen_ids: list[int] = []

    while remaining and len(chosen_ids) < k:
        best_idx = -1
        best_score = -math.inf
        for i, (cid, emb, rel) in enumerate(remaining):
            if not selected:
                score = rel
            else:
                max_sim = max(cosine(emb, s_emb) for _, s_emb, _ in selected)
                score = lambda_ * rel - (1.0 - lambda_) * max_sim
            if score > best_score:
                best_score = score
                best_idx = i
        cid, emb, rel = remaining.pop(best_idx)
        selected.append((cid, emb, rel))
        chosen_ids.append(cid)

    return chosen_ids
