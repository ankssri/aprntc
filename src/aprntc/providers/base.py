"""The provider-agnostic LLM seam (anti-lock-in invariant).

A single ``complete()`` contract returns a normalized result so the rest of the
system never depends on a specific vendor's response shape. The BytePlus
``ModelArk`` client (``aprntc.byteplus.modelark``) already produces this shape;
this Protocol is what tap/eval/distillation code program against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class CompletionResult:
    """Normalized LLM completion (mirrors ModelArk's Completion, vendor-neutral)."""

    text: str
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract every model adapter satisfies."""

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> CompletionResult:
        ...
