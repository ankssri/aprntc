# ADR 0007 — Canonical Trajectory schema

**Status:** Accepted (2026-06)

## Context
Every tap collector (SDK wrapper, LiteLLM egress proxy, OTel ingester, MCP/ContextForge) produces
heterogeneous data that must converge on ONE canonical schema — the normalizer's output and the unit
everything downstream (labeling, distillation, eval) consumes. Per the build plan, the schema is
designed and locked in its own pass BEFORE collectors are built (they are pure adapters into it).

## Decision
Lock the `Trajectory` schema below. Implemented as dataclasses in
`src/aprntc/trajectory/schema.py` with JSON round-trip + edge-case tests.

### Shape (turn → task; ADR-aligned with the data model in DESIGN.md §4)
- **Episode** (task = unit of learning): `episode_id, trace_id?, generation_id?, agent_artifact_hash?,
  collector, schema_version, ts_start, ts_end?, task_input, input_context[], turns[], final_output?,
  metrics(latency_ms?, ttft_ms?, tokens_in?, tokens_out?, cost_usd?), model_id?,
  pii_status(raw|scrubbed|redacted), retention_until?, partial(bool), labels[], outcome?`
- **Turn**: `turn_index, user_content[], agent_content[], reasoning_content?, steps[], partial(bool)`
- **ContentPart**: `type(text|image|video|file|audio), text?, ref?, mime?` — media stored **by
  reference** (URL/content-hash), NEVER raw blobs inline.
- **Step**: `step_index, type(thought|tool_call|tool_result|model_call|handoff), tool_name?, tool_args?,
  tool_result?, duration_ms?, tokens?, error?, source_fidelity(full|partial|inferred)`
- **Label** (1..N, append-only): `source(judge|user_explicit|user_implicit|outcome|human), score[0..1],
  rubric_dim?, rationale?, confidence?, judge_model?, created_at`
- **Outcome** (delayed, joined by `trace_id`): `trace_id, resolved?, correct?, downstream_metric?,
  arrived_at`

## Key design choices (the edge cases this absorbs)
- **True superset:** anything any collector can emit has a home → optional fields dominate.
- **Missing-per-source:** uncertain fields are Optional; `Step.source_fidelity` records HOW trustworthy
  the capture is (full=SDK wrapper, partial/inferred=proxy/OTel).
- **Best-effort capture (ADR 0005):** `partial` flags on Episode + Turn mark incomplete captures
  (stream cut off, external agent) instead of discarding them.
- **Provenance:** `Episode.collector` + per-step `source_fidelity`.
- **Privacy-by-shape:** media **by reference** + `pii_status` → supports scrub-at-ingest, TTL,
  `delete_by_subject`; no raw PII/blobs inline (ties to the privacy invariant).
- **Versioned:** `schema_version` on every Episode → clean future migrations as collectors land.
- **Correlation is best-effort:** `trace_id` optional; absence is acceptable (ADR 0005).

## Alternatives rejected
- **Inline base64 media** — bloats the store, complicates PII-scrub/TTL, risks storing sensitive media.
- **No version field** — forces awkward migrations later when the schema evolves.
- **Rigid required fields** — would drop data from lower-fidelity collectors (proxy/OTel).

## Consequences
- Collectors (Stage 2) implement adapters that emit this schema; they never extend it ad hoc.
- The Trajectory Store (Stage 1 part 2) persists exactly this shape; labels/outcomes attach over time,
  the episode body is otherwise append-only/immutable.
- Schema changes go through a new ADR + `schema_version` bump.
