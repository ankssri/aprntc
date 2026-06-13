"""LLM provider abstraction — the model-agnostic seam.

Any model (BytePlus Seed/DeepSeek, OpenAI, Anthropic, Gemini, Mistral, …) plugs
in behind :class:`LLMProvider`. The BytePlus ModelArk client already matches this
shape; native adapters for other providers are added later.
"""

from aprntc.providers.base import CompletionResult, LLMProvider

__all__ = ["CompletionResult", "LLMProvider"]
