# ADR 0005 — aprntc is a learning product, not observability

**Status:** Accepted (2026-06)

## Context
The tap captures parent-agent behavior. A tempting framing is "capture everything perfectly" (the
observability mindset). That over-engineers the hardest problem — cross-collector correlation — and
misframes the product.

## Decision
**aprntc is NOT a monitoring/observability product.** It learns from the parent's overall **response
quality** (good / mediocre / bad) to produce a better successor. The completeness target is
**episode/task-level quality signal**, NOT per-call trace completeness.

## Rationale
- The goal is a better child agent, not a dashboard. If a data point can't be captured or correlated
  (common for external/uninstrumented agents), that's acceptable as long as response quality is
  assessable.
- This consciously **relaxes cross-collector correlation** from "must solve" to "best-effort" —
  strongest for our own demos (propagate OTel trace context); for external agents, stitch
  heuristically by time+session, accept lower fidelity.

## Alternatives rejected
- **Exhaustive trace capture/correlation** — observability-grade completeness; large effort for data we
  don't need, and impossible to guarantee for closed agents.

## Consequences
- Don't build correlation infrastructure beyond best-effort.
- Schema/store design optimizes for quality signal per episode, not full distributed tracing.
