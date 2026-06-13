"""Thin BytePlus ModelArk client — OpenAI-compatible Chat Completions over REST.

Stage-0 scope: enough to (a) smoke-test that the policy and judge models are
both reachable and (b) read back the assistant text, reasoning trace, tool
calls, and token usage in a normalized shape. This is the seed of the
``LLMProvider`` interface; the full provider abstraction lands with the tap.

ModelArk is OpenAI-compatible (Bearer auth), so this is a small httpx wrapper —
no SDK. Deep-thinking is exposed via the ``thinking`` param; the reasoning trace
comes back in ``message.reasoning_content`` (separate from the answer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import httpx
except ModuleNotFoundError as exc:  # pragma: no cover - guides the user to the extra
    raise ModuleNotFoundError(
        "ModelArk client needs httpx — install the byteplus extra: pip install 'aprntc[byteplus]'"
    ) from exc

from aprntc.config import ModelArkConfig


@dataclass
class Completion:
    """Normalized result of a chat completion (provider-agnostic shape)."""

    text: str
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class ModelArkClient:
    """Minimal Chat Completions client for ModelArk."""

    def __init__(self, config: ModelArkConfig, *, timeout: float = 60.0) -> None:
        config.validate()
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ModelArkClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        thinking: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> Completion:
        """Call ``/chat/completions`` and return a normalized :class:`Completion`.

        ``thinking`` ∈ {"enabled","disabled","auto"} toggles deep reasoning;
        the trace returns in ``message.reasoning_content``.
        """
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if thinking is not None:
            payload["thinking"] = {"type": thinking}
        if tools is not None:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        resp = self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) or {}
        return Completion(
            text=message.get("content") or "",
            reasoning_content=message.get("reasoning_content"),
            tool_calls=message.get("tool_calls") or [],
            usage=data.get("usage") or {},
            model=data.get("model", model),
            raw=data,
        )
