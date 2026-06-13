"""Live VikingDB Experience-Memory demo (CREATES REAL CLOUD RESOURCES).

Creates the lessons collection + index, upserts a few distilled lessons, then runs
a filtered hybrid vector search. Needs real VIKINGDB_AK/SK in .env.

Idempotent-ish: create calls may report "already exists" on re-run (we tolerate
that). Uses small deterministic local embeddings so the demo is self-contained.

Run:  .venv/bin/python scripts/demo_memory.py
"""

from __future__ import annotations

import hashlib
import sys
import time

from aprntc.config import Settings
from aprntc.memory import Lesson, LessonType
from aprntc.memory.vikingdb import VikingDBError, VikingDBMemoryStore

DIM = 8  # tiny embeddings for a self-contained demo


def embed(text: str, dim: int = DIM) -> list[float]:
    """Deterministic toy embedding from a hash (demo only; real runs use an embed API)."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = [(h[i % len(h)] / 255.0) - 0.5 for i in range(dim)]
    norm = sum(v * v for v in vals) ** 0.5 or 1.0
    return [v / norm for v in vals]


def _safe(label: str, fn):
    try:
        out = fn()
        print(f"  [ok] {label}: {str(out)[:160]}")
        return True
    except VikingDBError as e:
        msg = str(e)
        if "exist" in msg.lower() or "already" in msg.lower():
            print(f"  [skip] {label}: already exists")
            return True
        print(f"  [FAIL] {label}: {msg[:240]}")
        return False


def main() -> int:
    settings = Settings.from_env()
    try:
        settings.vikingdb.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    store = VikingDBMemoryStore(settings.vikingdb, collection="aprntc_lessons_demo",
                               index="aprntc_lessons_demo_idx", dim=DIM)

    print("== VikingDB Experience Memory demo (ap-southeast-1) ==")
    print("Control plane: create collection + index")
    _safe("create_collection", store.create_collection)
    _safe("create_index", store.create_index)

    # Index build is async; give it a moment before writing/searching.
    print("  ...waiting for index to be ready (10s)")
    time.sleep(10)

    lessons = [
        Lesson(content="For refund questions, ground the answer in the KB refund_policy entry.",
               lesson_type=LessonType.DIRECTIVE, situation="customer asks about refunds",
               embedding=embed("customer asks about refunds"), reward=0.9, generation=0),
        Lesson(content="Always cite the doc id used to answer factual questions.",
               lesson_type=LessonType.DIRECTIVE, situation="factual question over docs",
               embedding=embed("factual question over docs"), reward=0.85, generation=0),
        Lesson(content="Do not guess order status; call order_status tool.",
               lesson_type=LessonType.FAILURE_PATTERN, situation="customer asks where their order is",
               embedding=embed("customer asks where their order is"), reward=0.7, generation=0),
    ]
    print("Data plane: upsert lessons")
    if not _safe("upsert_lessons", lambda: store.upsert_lessons(lessons)):
        store_close(store); return 1

    print("  ...waiting for data to be searchable (10s)")
    time.sleep(10)

    print("Data plane: filtered hybrid search (min_reward=0.8)")
    try:
        results = store.retrieve(query_embedding=embed("customer asks about refunds"),
                                 k=2, min_reward=0.8)
        for r in results:
            print(f"  -> [{r.score:.3f}] ({r.lesson.lesson_type.value}) {r.lesson.content[:80]}")
        ok = len(results) > 0
    except VikingDBError as e:
        print(f"  [FAIL] retrieve: {str(e)[:240]}")
        ok = False

    store_close(store)
    print(f"\nResult: {'OK' if ok else 'NOT OK'}")
    return 0 if ok else 1


def store_close(store):
    # VikingDBMemoryStore has no open sockets (httpx per-call), nothing to close.
    pass


if __name__ == "__main__":
    sys.exit(main())
