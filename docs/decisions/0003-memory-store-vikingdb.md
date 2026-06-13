# ADR 0003 — Experience Memory = VikingDB (not KnowledgeBase)

**Status:** Accepted (2026-06)

## Context
The apprentice retrieves distilled **lessons** at inference. Two BytePlus options sit behind our
`MemoryStore` interface: VikingDB (vector DB) and KnowledgeBase (managed RAG).

## Decision
**VikingDB** is the default `MemoryStore`.

## Rationale
Experience Memory is a **curated, generation-versioned index of machine-written lessons we control** —
not a document corpus:
- We own the embed + write path; lessons carry our own scalar fields (`generation`, `reward`,
  `lesson_type`, `pii_status`).
- Core retrieval primitive = **filtered hybrid dense+sparse search** (`dense_weight`) + scalar filters
  + MMR dedup — directly exposed by VikingDB's search API.
- Generation-tagged lifecycle: recency decay, prune low-efficacy, `delete_by_subject` (GDPR).

## Alternatives rejected
- **KnowledgeBase (managed RAG)** — abstracts ingestion (feed docs → it chunks/embeds), giving less
  control over the fusion/filter knobs our reward-anchored retrieval needs. *Note:* the RAG-Q&A demo's
  own subject-matter corpus could itself be a KnowledgeBase — that's separate from apprentice memory.

## Consequences
- We own embedding choice + upsert of raw vectors.
- Not a one-way door: both sit behind `MemoryStore`; swapping is contained.
