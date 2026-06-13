"""Trajectory: the canonical record of one parent-agent task execution.

The schema (see ADR 0007) is the single shape every tap collector normalizes
into and everything downstream (labeling, distillation, eval) consumes.
"""

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
]
