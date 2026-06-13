"""MemoryStore interface + the Lesson model.

A **Lesson** is a distilled, reusable improvement (ADR 0003) — NOT a raw
trajectory. It carries the scalar fields the retrieval layer filters on
(generation, reward, lesson_type, pii_status) plus a situation embedding and the
human-readable content injected at inference.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class LessonType(str, Enum):
    EXEMPLAR = "exemplar"              # a good situation→approach example to imitate
    DIRECTIVE = "directive"           # a generalized "do this" rule
    ROUTING_HEURISTIC = "routing_heuristic"
    FAILURE_PATTERN = "failure_pattern"  # an anti-pattern / "watch out for"

    @classmethod
    def coerce(cls, v: "LessonType | str") -> "LessonType":
        return v if isinstance(v, cls) else cls(str(v))


def new_lesson_id() -> str:
    return f"les_{uuid.uuid4().hex}"


@dataclass
class Lesson:
    """A distilled, retrievable lesson."""

    content: str                         # the human-readable lesson injected at inference
    lesson_type: LessonType
    situation: str                       # the situation text this lesson applies to
    embedding: list[float] = field(default_factory=list)  # dense vector of `situation`
    reward: float = 0.0                  # quality of the source episode(s) [0,1]
    generation: int = 0                  # lineage generation that produced it
    lesson_id: str = field(default_factory=new_lesson_id)
    pii_status: str = "scrubbed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.lesson_type = LessonType.coerce(self.lesson_type)
        if not self.content or not self.content.strip():
            raise ValueError("Lesson.content must be non-empty")
        if not 0.0 <= float(self.reward) <= 1.0:
            raise ValueError(f"Lesson.reward must be in [0,1]; got {self.reward}")

    def to_fields(self) -> dict[str, Any]:
        """Scalar+vector fields for a VikingDB row (excludes nothing sensitive — lessons
        are already distilled + scrubbed)."""
        return {
            "lesson_id": self.lesson_id,
            "content": self.content,
            "situation": self.situation,
            "lesson_type": self.lesson_type.value,
            "reward": self.reward,
            "generation": self.generation,
            "pii_status": self.pii_status,
            "embedding": list(self.embedding),
        }

    @classmethod
    def from_fields(cls, d: dict[str, Any]) -> "Lesson":
        return cls(
            content=d["content"],
            lesson_type=d.get("lesson_type", LessonType.DIRECTIVE),
            situation=d.get("situation", ""),
            embedding=list(d.get("embedding", [])),
            reward=float(d.get("reward", 0.0)),
            generation=int(d.get("generation", 0)),
            lesson_id=d.get("lesson_id", new_lesson_id()),
            pii_status=d.get("pii_status", "scrubbed"),
            metadata={k: v for k, v in d.items() if k not in {
                "content", "lesson_type", "situation", "embedding",
                "reward", "generation", "lesson_id", "pii_status",
            }},
        )


@dataclass
class RetrievedLesson:
    lesson: Lesson
    score: float  # similarity/relevance score from the store


@runtime_checkable
class MemoryStore(Protocol):
    """Upsert/retrieve distilled lessons. VikingDB is the default implementation."""

    def upsert_lessons(self, lessons: list[Lesson]) -> int:
        """Insert/update lessons. Returns the count written."""
        ...

    def retrieve(
        self,
        *,
        query: str,
        k: int = 4,
        min_reward: float = 0.0,
        generation: int | None = None,
        lesson_type: str | None = None,
        diversify: bool = True,
    ) -> list[RetrievedLesson]:
        """Filtered retrieval by query TEXT (server-side vectorize) + optional MMR."""
        ...
