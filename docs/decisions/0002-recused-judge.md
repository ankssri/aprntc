# ADR 0002 — Recused judge (judge ≠ policy)

**Status:** Accepted (2026-06)

## Context
Quality signals are fused into a reward that drives learning. An LLM judge gives the broadest coverage
but is biased and gameable — especially toward its own outputs (self-preference).

## Decision
The judge model **must differ from the policy/agent model**. Default: policy = **Seed-2.0-pro**,
judge = **DeepSeek-V4-pro** (both on BytePlus ModelArk, confirmed distinct endpoints). Enforced in
`config.py` (`ModelArkConfig.validate` raises if they're equal).

## Rationale
- Anti self-preference: a model judging its own family inflates its scores.
- Pairwise, rubric-based, reference-guided grading on top of recusal further reduces bias.

## Alternatives rejected
- **Same model as judge and policy** — simplest, but reward-hacking/self-preference risk is too high
  for a self-modifying system.

## Consequences
- Always need two distinct model endpoints available.
- The judge is a **prior, never the anchor** — outcomes outrank it in fusion (see ADR 0006).
