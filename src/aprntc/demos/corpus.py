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
                 "harbor life. About 71% of its surface is covered by water. It has one moon.",
    "doc_mars": "Mars is the fourth planet from the Sun, known as the Red Planet due to "
                "iron oxide on its surface. It has two small moons, Phobos and Deimos.",
    "doc_jupiter": "Jupiter is the largest planet in the Solar System, a gas giant with "
                   "a mass more than twice that of all other planets combined. It has a "
                   "Great Red Spot, a giant storm larger than Earth.",
    "doc_saturn": "Saturn is the sixth planet from the Sun and is famous for its prominent "
                  "ring system made of ice and rock. It is the second-largest planet.",
    "doc_venus": "Venus is the second planet from the Sun and the hottest planet, with "
                 "surface temperatures around 465 degrees Celsius due to a thick CO2 atmosphere.",
    "doc_mercury": "Mercury is the closest planet to the Sun and the smallest planet in the "
                   "Solar System. It has almost no atmosphere and extreme temperature swings.",
    "doc_neptune": "Neptune is the eighth and farthest planet from the Sun. It is an ice "
                   "giant with the strongest winds in the Solar System, exceeding 2,000 km/h.",
    "doc_moon": "The Moon is Earth's only natural satellite. It is about 384,400 km away and "
                "causes ocean tides. It takes about 27 days to orbit Earth.",
    "doc_pluto": "Pluto is a dwarf planet in the Kuiper Belt. It was reclassified from a "
                 "planet to a dwarf planet in 2006. Its largest moon is Charon.",
}


@dataclass(frozen=True)
class GoldItem:
    question: str
    reference_answer: str
    cited_docs: tuple[str, ...]  # doc ids that should ground the answer


# Frozen held-out gold set — the promotion-gate ruler. Distillation must NEVER train
# on this. Larger N (20) so the win-rate CI can actually be powered (N=4 never clears 50%).
GOLD: tuple[GoldItem, ...] = (
    GoldItem("How old is the Sun?", "About 4.6 billion years old.", ("doc_solar",)),
    GoldItem("Which planet is known as the Red Planet?", "Mars.", ("doc_mars",)),
    GoldItem("What fraction of Earth's surface is water?", "About 71%.", ("doc_earth",)),
    GoldItem("What is the largest planet?", "Jupiter.", ("doc_jupiter",)),
    GoldItem("How many moons does Mars have?", "Two — Phobos and Deimos.", ("doc_mars",)),
    GoldItem("Which planet has prominent rings?", "Saturn.", ("doc_saturn",)),
    GoldItem("What is the hottest planet?", "Venus.", ("doc_venus",)),
    GoldItem("Which planet is closest to the Sun?", "Mercury.", ("doc_mercury",)),
    GoldItem("What is the smallest planet?", "Mercury.", ("doc_mercury",)),
    GoldItem("Which planet has the strongest winds?", "Neptune.", ("doc_neptune",)),
    GoldItem("What is the farthest planet from the Sun?", "Neptune.", ("doc_neptune",)),
    GoldItem("How far is the Moon from Earth?", "About 384,400 km.", ("doc_moon",)),
    GoldItem("How long does the Moon take to orbit Earth?", "About 27 days.", ("doc_moon",)),
    GoldItem("Why is Mars red?", "Iron oxide on its surface.", ("doc_mars",)),
    GoldItem("What is the Great Red Spot?", "A giant storm on Jupiter.", ("doc_jupiter",)),
    GoldItem("Why is Venus so hot?", "A thick CO2 atmosphere traps heat.", ("doc_venus",)),
    GoldItem("How many moons does Earth have?", "One.", ("doc_earth",)),
    GoldItem("Is Pluto a planet?", "No, it is a dwarf planet.", ("doc_pluto",)),
    GoldItem("What is Pluto's largest moon?", "Charon.", ("doc_pluto",)),
    GoldItem("What are Saturn's rings made of?", "Ice and rock.", ("doc_saturn",)),
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
