"""Demo agents (synthetic data) — the two MVP domains tapped via the SDK wrapper.

- ``support`` — customer-support chat agent (tools: KB lookup, order status).
- ``rag`` — RAG-Q&A assistant over a synthetic doc corpus + a gold Q&A set.

Both are thin model→tool loops we own, so the SDK-wrapper tap captures
full-fidelity trajectories. Agent logic is provider-agnostic (works with any
``LLMProvider``); a fake provider drives the offline tests, real ModelArk drives
``scripts/demo_agents.py``.
"""
