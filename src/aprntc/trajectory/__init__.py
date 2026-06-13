"""Trajectory: the canonical record of one parent-agent task execution.

The schema (see ADR 0007) is the single shape every tap collector normalizes
into and everything downstream (labeling, distillation, eval) consumes.
"""

from aprntc.trajectory.pii import scrub_episode, scrub_text
from aprntc.trajectory.schema import (
    SCHEMA_VERSION,
    Collector,
    ContentPart,
    ContentType,
    Episode,
    Label,
    LabelSource,
    Outcome,
    PiiStatus,
    SourceFidelity,
    Step,
    StepType,
    Turn,
)
from aprntc.trajectory.store import TrajectoryStore

__all__ = [
    "SCHEMA_VERSION",
    "Collector",
    "ContentPart",
    "ContentType",
    "Episode",
    "Label",
    "LabelSource",
    "Outcome",
    "PiiStatus",
    "SourceFidelity",
    "Step",
    "StepType",
    "Turn",
    "TrajectoryStore",
    "scrub_episode",
    "scrub_text",
]
