# ADR 0006 — Outcome-anchored quality + playbook distillation (no fine-tuning in Phase 1)

**Status:** Accepted (2026-06)

## Context
How should the apprentice learn, and what should it trust as "better"?

## Decision
- **Learning mechanism (Phase 1):** Experience Memory (RAG) + **playbook distillation** — edit the
  playbook (system prompt + exemplars + routing heuristics) via an **attributable diff**, NOT
  fine-tuning. Fine-tuning (PEFT) is Phase 2.
- **Quality fusion:** **anchored on outcomes**. Reliability order **outcome > explicit feedback >
  judge**; the judge is a prior, never the authority. Distillation never sees the gold/hold-out set.
- **Outcome signals:** support-chat = resolved-in-session (minutes); RAG-Q&A = automated
  groundedness/citation-correctness + user acceptance, with a separate frozen gold set as the ruler.

## Rationale
- Playbook diffs are fast, reversible (one row/diff to revert), fully attributable (needed for the
  human approval gate and reward-hacking debugging), and data-efficient.
- Outcome anchoring is the primary defense against reward-hacking the judge.

## Alternatives rejected
- **Fine-tuning first** — needs training infra + many clean labels (unavailable early), slow loop,
  catastrophic-forgetting risk, hard to reverse. Deferred to Phase 2 to *compress* validated lessons.
- **Judge as the anchor** — gameable; would let the child learn to please the judge, not users.

## Consequences
- MVP fusion uses fixed priority + confidence (learned weights deferred to v1+).
- Promotion is human-gated now; auto-promotion earned later once judge↔outcome trust is proven.
