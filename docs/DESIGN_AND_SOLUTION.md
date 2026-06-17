# aprntc — Design & Solution Document

> **Status: MVP COMPLETE** — built through Stage 7; the full observe→label→distill→evaluate→promote
> loop, including the human-gated promotion gate, runs end-to-end on live BytePlus infra. This document
> describes the system **as built**, not as merely planned. Companion docs: `DESIGN.md` (concise
> design), `STATUS.md` (build log), `decisions/` (ADRs), `CLAUDE.md` (auto-loaded orientation).

---

## 1. Executive summary
**aprntc** is a standalone, framework-agnostic framework that makes a deployed LLM agent **improve
itself**. An *apprentice* ("child") agent is cloned from a live *parent* agent, **passively shadows**
the parent's behavior, distills reusable **lessons** from what worked and what didn't, and — gated by a
human — is **promoted** to replace the parent. Then the cycle repeats. Codename **"Shadow."**

The core loop — **observe → label → distill → evaluate → promote** — runs with a human only at the
promotion gate. Phase-1 learning is **Experience Memory (RAG) + playbook distillation** (no
fine-tuning): quality is **anchored on outcomes**, judged by a **recused** model (judge ≠ policy), and
every improvement is an **attributable, reversible** edit to the child's playbook.

**Reference implementation** runs on **BytePlus ModelArk** (Seed-2.0-pro policy, DeepSeek-V4-pro judge)
and **BytePlus VikingDB** (Experience Memory), but every external dependency sits behind an interface
(anti-lock-in). The whole loop has been verified end-to-end on live infrastructure.

---

## 2. The problem
The #1 limitation of production LLM agents is that they **don't learn from experience** — they stay
stateless and require manual prompt/dataset work to improve. aprntc closes that gap with an autonomous
improve-and-prove loop, while keeping a human approval gate and instant rollback so teams can trust it.

**Scoping principle (load-bearing):** aprntc is **NOT** a monitoring/observability product. It learns
from the parent's overall **response quality** to produce a better successor; the target is
episode/task-level quality signal, not exhaustive trace capture (ADR 0005).

---

## 3. The closed loop (as built)

```
            ┌──────────────────────────── parent agent (serves users) ───────────────────────────┐
            │                                                                                      │
   user ───▶│  AgentTap (SDK wrapper, fail-open)  ──▶  Trajectory  ──▶  Trajectory Store (SQLite)  │
            │                                                                  │                   │
            └──────────────────────────────────────────────────────────────── │ ──────────────────┘
                                                                               ▼
                          Evaluation/Labeling:  Outcome scorers (ANCHOR)  +  Pairwise Judge (recused)
                                                                               │  → fused (reward, confidence)
                                                                               ▼
                          Distiller:  bucket success/failure → mine Lessons → attributable Playbook DIFF
                                                                               │
                                          Lessons ──▶ Experience Memory (VikingDB, hybrid search)
                                                                               │
                          Child runtime:  parent clone + candidate Playbook + memory retrieval
                                                                               │
                          Promotion gate (Stage 7):  held-out eval → win-rate/CI → human approve → swap
                                                                               │
                                                          promote ──▶ new parent ──▶ next child …
```

Each arrow is implemented and the path from **parent run → distilled lesson → VikingDB → child
retrieval** is verified live (`scripts/demo_loop.py`).

---

## 4. Component design

### 4.1 LLMProvider (the model-agnostic seam) — `providers/`
A single `complete()` contract returns a normalized `CompletionResult` (`text`, `reasoning_content`,
`tool_calls`, `usage`). One OpenAI-compatible adapter serves Ark (Seed/DeepSeek) + OpenAI + Mistral;
Anthropic/Gemini get native adapters. The rest of the system never depends on a vendor's response shape.

### 4.2 AgentTap + collectors — `tap/`
Captures the parent's behavior into the canonical `Trajectory`. Principle: **intercept at stable
protocol boundaries, not framework internals** (ADR 0004). Collectors:
- **SDK wrapper** (built) — wraps the model client; full-fidelity (messages, reasoning, tool_calls,
  tokens, timing) for code we own. The tap is **async + fail-open**: a sink/recording error never
  reaches the parent agent.
- **LiteLLM egress proxy / OTel ingester / MCP (ContextForge) / A2A interceptor** — plug in behind the
  same `AgentTap` core for closed-source / instrumented / MCP-based / multi-agent (A2A) agents. All four
  protocol boundaries are now instrumented.
- Tool-tracking fidelity degrades gracefully: wrapper (full) → MCP (full) → OTel (if emitted) → proxy
  (inferred) → A2A (coarse; task/artifact only). Cross-collector correlation is best-effort by design (ADR 0005).

### 4.3 Trajectory schema + Store — `trajectory/`
The one canonical record every collector normalizes into (ADR 0007):
`Episode(task) → Turn → Step`, plus `Label` (1..N, attached over time) and delayed `Outcome`.
Design choices: media **by reference** (no inline blobs), `schema_version` (migrations), `partial`
flags (best-effort capture), per-step `source_fidelity` (missing-per-source), `pii_status`.

**Trajectory Store** (SQLite, Postgres-ready): scrub-PII-at-ingest, append-only labels/outcomes,
`fused_reward` (confidence-weighted, outcome>explicit>implicit>judge), `delete_by_subject` (GDPR),
`purge_expired` (TTL). PII scrubbing runs before any persistence (`trajectory/pii.py`).

### 4.4 Evaluation / Labeling — `eval/`
Turns trajectories into quality signals that feed fusion (ADR 0006):
- **Outcome scorers = the ANCHOR** (deterministic, no LLM): support = resolved-in-session; RAG =
  groundedness/citation-correctness vs the gold set. Highest reliability.
- **PairwiseJudge** = a *prior, never the anchor*: **recused** (raises if judge==policy),
  order-randomized (position de-bias), rubric + strict-JSON. Verified live: DeepSeek-V4-pro picked the
  better answer and the de-bias resolved correctly.
- **Health**: judge↔reference agreement (drift kill-switch) + reward-hacking alarm (judge↑ outcome-flat).

### 4.5 Experience Memory — `memory/`
Curated, generation-versioned **Lessons** (not raw logs; ADR 0003), behind a `MemoryStore` interface.
Default = **VikingDB via REST** (ADR 0001) with our own Volcengine **Signature-V4** signer
(`byteplus/signing.py`, byte-for-byte SDK-verified). The live collection uses **server-side vectorize**
(skylark-embedding-vision, 2048-dim): lessons store text in `situation`; retrieval is **filtered hybrid
search by text** with an always-on `pii_status=scrubbed` filter + MMR diversification. Lessons have
**stable content-derived ids** (re-upsert updates, not duplicates). Verified live: auth, upsert,
filtered search, dedup, delete.

### 4.6 Distillation + Child runtime — `distill/`
- **Playbook** — the child's mutable artifact (system prompt + exemplars + directives + watch-outs),
  content-addressed `hash`, token-budgeted render.
- **PlaybookDiff** — **attributable** (each item links to its source lesson_id) and **reversible**
  (single-lesson `revert`); `apply` = generation+1 + dedup + **capped change per generation**
  (catastrophic-forgetting guard). Edit, never regenerate (ADR 0006).
- **Distiller** — pulls scored episodes, buckets by fused reward (success/failure), mines lessons via
  the LLM (success→directives, failure→watch-outs), emits the diff + `Lesson`s for memory.
- **ChildAgent** — a parent clone whose only differences are the candidate Playbook (as system prompt)
  and memory retrieval (records a `memory_retrieve` step; best-effort/fail-open).

---

## 5. BytePlus integration (reference implementation)
- **ModelArk** (LLM): OpenAI-compatible, `Bearer` auth, base `…/api/v3`. Deep-thinking via
  `thinking:{type}` → reasoning in `message.reasoning_content`. Region `ap-southeast-1`. Policy + judge
  are distinct endpoint-ids (judge ≠ policy enforced in config).
- **VikingDB** (memory): SigV4 signing, **`service="vikingdb"`** (a hard-won finding — `"air"` 403s).
  Control plane = `Action=` query params on `vikingdb.…byteplusapi.com`; data plane = fixed paths on
  `api-vikingdb.…bytepluses.com`. Upsert key is `data`; server-side vectorize embeds text fields.

**Anti-lock-in (ADR + invariant):** the load-bearing bets are open *protocols* (OpenTelemetry, MCP,
OpenAI wire format); concrete gateways (LiteLLM, ContextForge) and BytePlus are swappable adapters
behind interfaces. Permissive licenses only; no designing against any tool's paid tier.

---

### 4.7 Promotion gate + Lineage + UI — `promote/`, `ui/`
- **PromotionGate** — runs parent vs child on a frozen held-out set, scores each pair with the recused
  judge (order-balanced), and applies the **acceptance bar** (win-rate ≥ 55%, **Wilson 95% CI low >
  50%**, loss < 10%) plus **zero-tolerance hard gates** (regression + safety, via per-case checkers).
  MVP uses offline replay. Verified live: the gate **correctly rejected** an underperforming child.
- **LineageRegistry** — generation DAG (G0→G1→…), `promote` appends + advances `current`, `rollback`
  reverts to the prior generation (instant one-click revert); JSON-persisted, inspectable by the UI.
- **Streamlit review UI** (`ui/review_app.py`) — the human-in-the-loop surface: shows the attributable
  diff, gate metrics, hard-gate flags; **Promote** (disabled until the bar passes) / **Rollback**.
  Reads a JSON review bundle so the UI is decoupled from live model calls.

## 6. Acceptance bar (enforced by the gate)
A distilled child must be **provably + reliably better** than the parent on a frozen held-out set never
seen by distillation: pairwise **win-rate ≥ 55%** (95% CI lower bound > 50%, powered N), **loss-rate
< 10%**, **zero** regression/safety failures (hard gates), within latency/cost guardrails, and
**promotable + revertible from the UI**. MVP eval uses **offline replay** (live shadow/canary deferred).

---

## 7. Key engineering decisions (see `decisions/` for full ADRs)
| ADR | Decision |
|---|---|
| 0001 | VikingDB via REST (own SigV4 signer; SDK as dev-only oracle) |
| 0002 | Recused judge (judge ≠ policy) |
| 0003 | Experience Memory = VikingDB (curated lesson index, not a doc corpus) |
| 0004 | Tap = protocol-boundary collectors, wrap OSS |
| 0005 | aprntc is a learning product, **not** observability (best-effort capture) |
| 0006 | Outcome-anchored quality + playbook distillation (no fine-tuning in Phase 1) |
| 0007 | Canonical Trajectory schema |
| 0008 | Tap build order: core + SDK wrapper first |

**Process note / hard-won lesson:** an SDK-equivalence ("oracle") test only proves we match the SDK
given the *same inputs* — it cannot catch a wrong input (we fed both our signer and the SDK
`service="air"`; both agreed while both were wrong vs the live server). **The live API is the ultimate
oracle.** This is why every stage is verified against live infra, not just unit tests.

---

## 8. Quality & process guardrails (how this was built safely)
- **Context persistence:** `CLAUDE.md` (auto-loaded), `DESIGN.md`, ADRs, `STATUS.md` build log — so a
  fresh session never loses the *why*.
- **Regression safety:** 117 tests (full suite green is a hard gate before every commit), GitHub
  Actions CI on every push, and a Claude Code `Stop` hook that auto-runs the suite after edits.
- **Stage discipline:** each stage on its own branch, merged to `main` only when green and (where
  applicable) live-verified; decisions captured as ADRs as they're made.

---

## 9. Status & what remains
- **MVP COMPLETE — built + live-verified:** Stages 0–7 — signing gate, trajectory schema/store, tap +
  SDK wrapper, two demo agents, evaluation/labeling, VikingDB memory, distillation + child runtime,
  promotion gate + lineage + Streamlit UI. **The full observe→label→distill→evaluate→promote loop runs
  end-to-end on live BytePlus infra, with the human-gated acceptance bar protecting promotions** (a live
  run correctly rejected an underperforming child).
- **Deferred to v1+ (with rationale in `DESIGN.md`/STATUS):** the proxy/OTel/MCP collectors, online
  shadow/canary, learned fusion weights, fine-tuning (PEFT), auto-promotion, multi-agent fleets.
- **Quality next steps (not MVP-blocking):** richer distillation (clustering, more lessons), larger
  held-out/gold sets for a powered win-rate, and per-lesson efficacy pruning — to get a child that
  reliably clears the bar.

---

## 10. Repository map
```
src/aprntc/
  providers/    LLMProvider seam (model-agnostic)
  byteplus/     signing (SigV4), modelark client
  trajectory/   schema, store (SQLite), pii scrubber
  tap/          AgentTap core + SDK-wrapper collector
  eval/         pairwise judge, outcome scorers, health metrics
  memory/       MemoryStore + VikingDB REST adapter + MMR
  distill/      playbook + diff, distiller, child runtime
  demos/        synthetic corpus + support/RAG demo agents
scripts/        smoke_byteplus, demo_agents, demo_memory, demo_loop (live)
tests/          117 tests (unit + signing oracle)
docs/           DESIGN, DESIGN_AND_SOLUTION (this), STATUS, decisions/ (ADRs)
```
