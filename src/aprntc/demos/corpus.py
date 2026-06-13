"""Synthetic data for the demo agents — zero PII, reproducible (no real-data dep).

- ``KB`` / ``ORDERS`` back the support-chat tools.
- ``DOCS`` is the RAG corpus; ``GOLD`` is the frozen Q&A gold set (reference
  answers + the doc ids that should be cited). The gold set is the promotion-gate
  ruler — distillation must NEVER train on it (ADR 0006).
"""

from __future__ import annotations

from dataclasses import dataclass

# ─── support-chat knowledge base + orders ───────────────────────────────────

KB: dict[str, str] = {
    "refund_policy": "Refunds are available within 30 days of purchase with a receipt.",
    "shipping_times": "Standard shipping takes 3-5 business days; express takes 1-2.",
    "password_reset": "Reset your password from Settings > Security > Reset Password.",
    "cancel_order": "Orders can be cancelled within 1 hour of placement from Order History.",
}

ORDERS: dict[str, dict[str, str]] = {
    "A1001": {"status": "shipped", "eta": "2 days"},
    "A1002": {"status": "processing", "eta": "5 days"},
    "A1003": {"status": "delivered", "eta": "-"},
}


# ─── RAG corpus + gold set ──────────────────────────────────────────────────

DOCS: dict[str, str] = {
    "doc_solar": "The Sun is the star at the center of the Solar System. It is about "
                 "4.6 billion years old and accounts for 99.8% of the system's mass.",
    "doc_earth": "Earth is the third planet from the Sun and the only known planet to "
                 "harbor life. About 71% of its surface is covered by water.",
    "doc_mars": "Mars is the fourth planet from the Sun, known as the Red Planet due to "
                "iron oxide on its surface. It has two small moons, Phobos and Deimos.",
    "doc_jupiter": "Jupiter is the largest planet in the Solar System, a gas giant with "
                   "a mass more than twice that of all other planets combined.",
}


@dataclass(frozen=True)
class GoldItem:
    question: str
    reference_answer: str
    cited_docs: tuple[str, ...]  # doc ids that should ground the answer


GOLD: tuple[GoldItem, ...] = (
    GoldItem("How old is the Sun?", "About 4.6 billion years old.", ("doc_solar",)),
    GoldItem("Which planet is known as the Red Planet?", "Mars.", ("doc_mars",)),
    GoldItem("What fraction of Earth's surface is water?", "About 71%.", ("doc_earth",)),
    GoldItem("What is the largest planet?", "Jupiter.", ("doc_jupiter",)),
    GoldItem("How many moons does Mars have?", "Two — Phobos and Deimos.", ("doc_mars",)),
)


def search_docs(query: str, *, k: int = 2) -> list[tuple[str, str]]:
    """Tiny lexical retriever over DOCS. Returns [(doc_id, text), ...] by overlap."""
    q_terms = {w.lower().strip("?.,") for w in query.split()}
    scored: list[tuple[int, str]] = []
    for doc_id, text in DOCS.items():
        terms = {w.lower().strip("?.,") for w in text.split()}
        scored.append((len(q_terms & terms), doc_id))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(doc_id, DOCS[doc_id]) for score, doc_id in scored[:k] if score > 0]
