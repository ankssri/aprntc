"""Experience Memory — curated, generation-versioned lessons (ADR 0003).

`MemoryStore` is the interface; `VikingDBMemoryStore` is the default REST adapter.
Lessons are upserted with scalar fields (generation, reward, lesson_type,
pii_status) and retrieved via filtered hybrid search + MMR diversification, then
injected as a few sharp exemplars under a token budget.
"""

from aprntc.memory.base import Lesson, LessonType, MemoryStore, RetrievedLesson
from aprntc.memory.mmr import cosine, mmr_select
from aprntc.memory.vikingdb import VikingDBError, VikingDBMemoryStore

__all__ = [
    "Lesson",
    "LessonType",
    "MemoryStore",
    "RetrievedLesson",
    "cosine",
    "mmr_select",
    "VikingDBError",
    "VikingDBMemoryStore",
]
