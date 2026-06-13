# Architecture Decision Records (ADRs)

Each ADR captures one significant decision: the **context**, the **decision**, the **rationale**,
and the **alternatives rejected** — so future sessions (and people) know *why*, not just *what*.

Format: short. Status ∈ Accepted / Superseded / Proposed. Number sequentially.

| # | Decision | Status |
|---|---|---|
| [0001](0001-vikingdb-over-rest.md) | VikingDB access via REST (not SDK) | Accepted |
| [0002](0002-recused-judge.md) | Recused judge (judge ≠ policy) | Accepted |
| [0003](0003-memory-store-vikingdb.md) | Experience Memory = VikingDB (not KnowledgeBase) | Accepted |
| [0004](0004-tap-collector-set.md) | Tap = protocol-boundary collectors, wrap OSS | Accepted |
| [0005](0005-not-observability.md) | aprntc is a learning product, not observability | Accepted |
| [0006](0006-outcome-anchored-learning.md) | Outcome-anchored quality + playbook distillation (no fine-tuning in Phase 1) | Accepted |
| [0007](0007-trajectory-schema.md) | Canonical Trajectory schema | Accepted |
| [0008](0008-tap-build-order.md) | Tap build order: core + SDK wrapper first | Accepted |
