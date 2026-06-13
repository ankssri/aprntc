# ADR 0008 — Tap build order: core + SDK wrapper first

**Status:** Accepted (2026-06)

## Context
The tap has four collectors (ADR 0004): SDK wrapper, LiteLLM egress proxy, OTel ingester, MCP
(ContextForge). Each stage must be independently verifiable (build-plan principle). The proxy/OTel/MCP
collectors need (a) the demo agents (Stage 3) and (b) live external services to integration-test; the
SDK wrapper needs neither.

## Decision
Build the tap in this order:
1. **Stage 2 (now):** tap core (`AgentTap` + recorders) + **SDK wrapper** collector — fully testable
   offline with fakes + the in-memory store.
2. **Stage 3:** demo agents, tapped via the SDK wrapper (exercises the core on real ModelArk calls).
3. **Later (within the tap workstream):** LiteLLM proxy → OTel ingester → MCP/ContextForge, each behind
   the same `AgentTap` core / `Episode` schema.

## Rationale
- "Richest-first": the SDK wrapper gives full-fidelity capture and proves the core + normalizer end to
  end before we depend on external services.
- Keeps every stage independently green; external collectors are additive, not prerequisites.

## Alternatives rejected
- **Proxy-first** — would force standing up LiteLLM + a live model path before the core is proven;
  heavier first milestone, not offline-testable.
- **All collectors in Stage 2** — couples the stage to services + demos that don't exist yet.

## Consequences
- The external collectors remain first-class (not dropped) — they slot in behind the proven core.
- Cross-collector correlation stays best-effort (ADR 0005); revisited when the proxy/OTel paths land.
