# aprntc — Design Document

> Canonical, in-repo design doc (the source of truth for *what* and *why*). Pairs with the ADRs in
> `docs/decisions/` (per-decision rationale) and `docs/STATUS.md` (build log). `CLAUDE.md` is the
> auto-loaded summary; this is the depth.

## 1. Concept
An **apprentice** ("child") agent is cloned from a live **parent** agent, **passively shadows** it,
distills lessons from its behavior (good / mediocre / bad), becomes a measurably better version, and —
gated by a human — is **promoted** to replace the parent. Then the cycle repeats. Codename **"Shadow."**

Standalone, framework-agnostic product. Loop: **observe → label → distill → evaluate → promote**, with
a human only at the promotion gate.

**Scoping principle (load-bearing):** NOT a monitoring/observability product. Learns from the parent's
overall **response quality** to produce a better successor; episode/task-level quality signal is the
target, not exhaustive trace capture. (ADR 0005.)

## 2. Locked decisions
- **Name/repo:** `aprntc` — https://github.com/aprntc/aprntc (private). MIT license.
- **Packaging:** standalone, framework-agnostic; BytePlus = one adapter set, not the core.
- **Demo domains:** customer-support chat + RAG-Q&A assistant — built in parallel; SYNTHETIC data.
- **Models (BytePlus ModelArk, OpenAI-compatible):** policy = Seed-2.0-pro, judge = DeepSeek-V4-pro;
  **judge ≠ policy** (ADR 0002). Region `ap-southeast-1`. Endpoint-ids live in `.env`.
- **Model-agnostic:** any Anthropic/Gemini/OpenAI/Mistral/other model pluggable behind `LLMProvider`.
  One OpenAI-compatible adapter serves Ark(Seed,DeepSeek)+OpenAI+Mistral; Anthropic+Gemini native.
- **Memory:** VikingDB default behind `MemoryStore`, via REST + our SigV4 signer (ADR 0001, 0003).
- **Learning:** Experience Memory (RAG) + playbook distillation; outcome-anchored; no fine-tuning in
  Phase 1 (ADR 0006).
- **Episode granularity:** turn-level records rolled up to a task-level canonical Episode.
- **Privacy:** scrub PII at ingest + 30-day TTL on raw trajectories; never embed raw PII into VikingDB.
- **Sampling (MVP):** capture 100%, no limits.
- **Promotion:** human-in-loop now; auto for low-risk diffs later.

## 3. Architecture
Provider-agnostic core depends only on interfaces; concrete adapters plug in behind them.

```
core interfaces:  LLMProvider · AgentTap · TrajectoryStore · Evaluator ·
                  MemoryStore · Distiller · PromotionGate · LineageRegistry
```

### Tap (ADR 0004) — intercept at protocol boundaries, wrap OSS
`AgentTap` + pluggable **collectors**, all normalizing to one `Trajectory` schema:
- **SDK wrapper** (our code; full-fidelity tool tracking) — for our demos.
- **Egress proxy = LiteLLM** (MIT) via CustomLogger — model traffic, incl. closed agents.
- **MCP interceptor = IBM ContextForge** (Apache-2.0) — tool tracking; exports OTel → reuses OTel path.
- **OTel ingester** — OpenTelemetry Collector + OpenLLMetry/OpenInference — instrumented frameworks.
- **A2A interceptor** — agent boundary; captures tasks/artifacts from an A2A server (multi-agent systems).

Tool tracking is must-have; fidelity degrades gracefully (wrapper → MCP → OTel → proxy → A2A). Cross-collector
correlation is best-effort (ADR 0005). Tap is async + fail-open.

### Pipeline shape
- Model traffic (incl. closed) → LiteLLM → normalizer.
- Tool traffic (MCP) → ContextForge → OTel → normalizer.
- Instrumented frameworks → OTel → normalizer.
- Our demos → SDK wrapper → normalizer.

### Memory (VikingDB, REST)
Curated lessons with scalar fields (`generation`, `reward`, `lesson_type`, `pii_status`); filtered
hybrid dense+sparse search (`dense_weight`) + MMR dedup; inject 2–4 exemplars + "watch out for" block
under a token budget.

## 4. Data model (turn → task)
- **Episode (task)** = unit of learning: `episode_id, generation_id, agent_artifact_hash, ts,
  task_input, input_context, turns[], final_output, latency_ms, ttft_ms, tokens, cost_usd, model_id,
  pii_status, retention_until`.
- **Turn** = `turn_index, user_content[] (multimodal parts), agent_msg, reasoning_content?, steps[]`.
- **Step** = `step_index, type(thought|tool_call|tool_result|model_call|handoff), tool_name?,
  tool_args?, tool_result?, duration_ms, tokens, error?`.
- **Label (1..N)** = `episode_id, source(judge|user_explicit|user_implicit|outcome|human), score[0..1],
  rubric_dim?, rationale?, confidence, judge_model?, created_at`.
- **Outcome (delayed)** = `trace_id, resolved?, correct?, downstream_metric?, arrived_at`.
- Append-only; labels/outcomes attach, episode never mutates; materialized fused `reward` view.
> The exact schema is designed + locked in Stage 1 as its own pass (then recorded as an ADR).

### Outcome signals (the learning anchor; ADR 0006)
- **Support chat:** resolved-in-session / no quick escalation (minutes) + thumbs.
- **RAG-Q&A:** automated groundedness/citation-correctness (RAGAS-style, seconds) + user acceptance.
  Separate frozen **gold set** (50–100 Q&A) = promotion-gate ruler + calibration; distillation NEVER
  sees it. Keep distinct: live outcome labels (learning) / gold set (ruler) / judge (a prior).

## 5. BytePlus API contracts (reference)
- **ModelArk:** OpenAI-compatible. Base `https://ark.ap-southeast.bytepluses.com/api/v3`,
  `Authorization: Bearer $ARK_API_KEY`. Chat Completions (`/chat/completions`). Deep thinking via
  `"thinking":{"type":...}` → reasoning in `message.reasoning_content`. Multimodal content parts.
  Streaming = SSE deltas + `data:[DONE]`. `model` = name OR endpoint-id (from console).
- **VikingDB V2 (ap-southeast-1):** Data plane `api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com`
  (fixed paths, snake_case); Control plane `vikingdb.ap-southeast-1.byteplusapi.com`
  (**`Action=` query params**, UpperCamelCase — confirmed live in Stage 0). All POST + JSON. Auth =
  Volcengine SigV4 HMAC-SHA256, service `air`, region `ap-southeast-1`. Index: hnsw/hnsw_hybrid/flat/
  diskann; distance ip|l2|cosine; `ScalarIndex[]` = filterable. Upsert ≤100 rows. Search: `limit`,
  `output_fields`, filter DSL (`must|must_not|range|and|or`), `advance.dense_weight` [0.2–1] hybrid.
> Full BytePlus docs (reference, not in repo): `/Users/ankur/mdfiles/` + `.../byteplus-vikingdb-docs/`.

## 6. Build plan (stages)
- **Stage 0 ✅** Skeleton + VikingDB SigV4 signing gate + ModelArk client. (Oracle + live verified.)
- **Stage 1** Trajectory schema (dedicated design pass → lock as ADR) + Trajectory Store (SQLite;
  PII-scrub, append-only labels/outcomes, retention TTL, `delete_by_subject`).
- **Stage 2** `AgentTap` + normalizer + collectors (SDK wrapper → LiteLLM → OTel → MCP/ContextForge).
- **Stage 3** Two demo agents (support-chat + RAG-Q&A, synthetic data).
- **Stage 4** Evaluation/Labeling (pairwise judge ≠ policy, outcome-joiner, confidence-weighted fusion).
- **Stage 5** Experience Memory (VikingDB REST adapter — control plane uses `Action=` params).
- **Stage 6** Distillation (attributable playbook diff) + Child runtime.
- **Stage 7** Promotion gate + Lineage + Streamlit UI (promote/rollback).

## 7. Acceptance bar (what "the MVP worked" means)
Frozen held-out set never seen by distillation. Run parent + child on the same tasks; recused judge
compares each pair. Passes only when ALL hold:

| Check | Threshold | Type |
|---|---|---|
| Win-rate | ≥ 55% | quality (average) |
| Confidence | 95% CI lower bound > 50% (powered N) | statistical |
| Loss-rate | < 10% | quality (downside) |
| Regression suite | 0 failures | HARD gate |
| Safety probes | 0 new violations | HARD gate |
| Guardrails | latency/cost within ε of parent | guardrail |
| Promote + rollback | both work from UI | operational |

MVP eval uses **offline replay** on recorded trajectories (not live traffic).

## 8. Deferred to v1+ (with why)
- **A2A collector** — ~~coarsest data, lowest adoption; 4 MVP collectors cover ~all agents.~~
  **Now built** (`tap/a2a_ingest.py`): agent boundary, task/artifact granularity, `SourceFidelity.COARSE`.
- **Online shadow / A-B canary** — needs live traffic + ~2× cost; MVP uses offline replay.
- **Learned fusion weights** — needs accumulated data; MVP uses fixed priority outcome>explicit>judge.
- **Fine-tuning (PEFT)** — Phase-2; needs training infra, hard to reverse; never replaces memory+playbook.
- **Auto-promotion** — earned after judge↔outcome trust proven; MVP is human-gated.
- **Multi-agent fleets / cross-agent lesson sharing** — prove single parent→child first.
