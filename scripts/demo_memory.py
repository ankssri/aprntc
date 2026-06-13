"""Live VikingDB Experience-Memory demo (uses the real collection).

Upserts a few distilled lessons (server-side vectorize embeds the `situation`
text), then runs a filtered text search. Needs real VIKINGDB_AK/SK in .env and
the collection/index created in the console (ankur_aprntc_collection / _index).

Run:  .venv/bin/python scripts/demo_memory.py
"""

from __future__ import annotations

import sys
import time

from aprntc.config import Settings
from aprntc.memory import Lesson, LessonType
from aprntc.memory.vikingdb import VikingDBError, VikingDBMemoryStore


def main() -> int:
    settings = Settings.from_env()
    try:
        settings.vikingdb.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    store = VikingDBMemoryStore(
        settings.vikingdb,
        collection="ankur_aprntc_collection",
        index="ankur_aprntc_index",
        dim=2048,
    )

    print("== VikingDB Experience Memory demo (ap-southeast-1, server-side vectorize) ==")
    lessons = [
        Lesson(content="For refund questions, ground the answer in the KB refund_policy entry.",
               lesson_type=LessonType.DIRECTIVE, situation="customer asks about refunds",
               reward=0.9, generation=0),
        Lesson(content="Always cite the doc id used to answer factual questions.",
               lesson_type=LessonType.DIRECTIVE, situation="factual question over documents",
               reward=0.85, generation=0),
        Lesson(content="Do not guess order status; call the order_status tool.",
               lesson_type=LessonType.FAILURE_PATTERN, situation="customer asks where their order is",
               reward=0.7, generation=0),
    ]

    print("Upserting lessons (text embedded server-side)...")
    try:
        n = store.upsert_lessons(lessons)
        print(f"  [ok] upserted {n} lessons")
    except VikingDBError as e:
        print(f"  [FAIL] upsert: {str(e)[:240]}")
        return 1

    print("  ...waiting for data to be searchable (15s)")
    time.sleep(15)

    print("Filtered text search (query='how do refunds work?', min_reward=0.8):")
    try:
        results = store.retrieve(query="how do refunds work?", k=2, min_reward=0.8)
        if not results:
            print("  (no results yet — indexing may still be catching up)")
        for r in results:
            print(f"  -> [{r.score:.3f}] ({r.lesson.lesson_type.value}) {r.lesson.content[:80]}")
        ok = True
    except VikingDBError as e:
        print(f"  [FAIL] retrieve: {str(e)[:240]}")
        ok = False

    print(f"\nResult: {'OK' if ok else 'NOT OK'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
