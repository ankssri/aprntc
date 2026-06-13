# ADR 0004 — Tap = protocol-boundary collectors, wrapping OSS

**Status:** Accepted (2026-06)

## Context
The tap must capture a parent agent's behavior to learn from it — and must work for agents built with
**any tool** (closed or open source), not just our demos.

## Decision
Intercept at **stable protocol boundaries, not framework internals.** `AgentTap` is an abstraction
with pluggable **collectors**, all normalizing into one canonical `Trajectory` schema:

- **SDK wrapper** — our own code (demos); full-fidelity tool tracking. IN.
- **Egress proxy** — **LiteLLM** (MIT), via a `CustomLogger` plugin; captures model traffic incl.
  closed-source agents. IN.
- **MCP interceptor** — **IBM ContextForge** (Apache-2.0) MCP gateway; clean tool tracking for
  MCP-based agents. Exports OTel → reuses the OTel ingester path (no bespoke MCP parser). IN.
- **OTel ingester** — OpenTelemetry Collector + OpenLLMetry/OpenInference; instrumented frameworks. IN.
- **A2A interceptor** — **DEFERRED until after v1** (coarsest data, lowest adoption).

Don't hand-build what a mature OSS project already does — **wrap it + feed our normalizer.**

## Rationale
- Tool tracking is must-have; fidelity degrades gracefully: SDK wrapper (full) → MCP (full if MCP-based)
  → OTel (if it emits tool spans) → egress proxy (partial/inferred from the function-call loop).
- MCP gateways already export OTel → MCP + OTel collectors **converge on one ingestion path**.

## Alternatives rejected
- **Hook framework internals** —每 framework differs and changes; brittle, not universal.
- **Build our own proxy / MCP transport** — reinvents TLS/SSE/retries/JSON-RPC the OSS already solves.

## Consequences
- The **normalizer** (heterogeneous inputs → one schema) is the real thing we own and must design
  carefully (its own design pass — Stage 1).
- Cross-collector correlation is **best-effort** (see ADR 0005), not exhaustive.
- All deps permissive-licensed, behind our interface (anti-lock-in).
