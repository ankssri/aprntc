# STATUS — aprntc build log

> Updated at the end of every stage. A fresh session reads this to know exactly where to resume.
> Format per stage: what's DONE, what's NEXT, and any LIVE FINDINGS discovered during the work.

---

## Stage 0 — Skeleton + VikingDB signing gate ✅ DONE (2026-06-13)
**Done:**
- `aprntc` package under `src/` with dependency-light core + optional extras (`pyproject.toml`).
- `config.py` — stdlib `.env` loader + ModelArk/VikingDB settings (enforces judge ≠ policy).
- `byteplus/signing.py` — Volcengine **Signature-V4** signer (REST, no runtime SDK). **THE gate.**
- `byteplus/modelark.py` — thin OpenAI-compatible ModelArk client (seed of `LLMProvider`).
- `scripts/smoke_byteplus.py` — live gate.
- Tests: **14 passing**, incl. 5 **oracle** tests (byte-for-byte vs `volcengine` SDK).
- Branch `stage-0-skeleton` pushed; merged (ff) into `main`.

**Verified:**
- Offline: 14/14 tests green; signer == SDK byte-for-byte.
- Live: ModelArk policy (`ep-20260406222234-wpzvn`) + judge (`ep-20260613201727-5twvg`) both answer,
  judge ≠ policy confirmed. VikingDB signed call **accepted** (HTTP 400 wrong-shape, NOT 403).

**Live findings:**
- VikingDB **control plane needs `Action=`-style query params**, not RESTful paths (signed POST to
  `/api/v2/collection/list` → 400 "missing Action parameter" = signature OK, shape wrong). Data plane
  uses fixed paths. → matters for Stage 5 (VikingDB memory adapter).
- This `volcengine` SDK's `SignerV4.sign()` has no timestamp-pin kwarg; oracle test signs via SDK then
  aligns our `now` to the SDK's stamped `X-Date`.

**Next:** Stage 1.

---

## Project infrastructure — context + regression guards ✅ DONE (2026-06-13)
**Done:** `CLAUDE.md` (auto-loaded orientation), `docs/DESIGN.md` (canonical design), `docs/decisions/`
(ADRs), this `STATUS.md`, GitHub Actions CI (pytest on push/PR), `.claude/settings.json` PostToolUse
test hook. (Branch `chore/project-docs-ci`.)

---

## Stage 1 — Trajectory schema + Trajectory Store ✅ DONE (2026-06-13)
**Part 1 — schema:** designed (dedicated pass), locked as **ADR 0007**, implemented in
`src/aprntc/trajectory/schema.py` (stdlib dataclasses: Episode/Turn/Step/ContentPart/Label/Outcome
+ enums). Media **by reference**; `schema_version`; `partial` flags; per-step `source_fidelity`;
`pii_status`. 19 round-trip/edge-case tests.

**Part 2 — Trajectory Store + PII scrubber:**
- `src/aprntc/trajectory/pii.py` — regex PII scrubber (email/phone/card/SSN/IP/secrets), recurses into
  tool args/results; runs at ingest; idempotent; non-mutating. (Swappable for NER later, same entry point.)
- `src/aprntc/trajectory/store.py` — SQLite system of record: `put_episode` (scrub-at-ingest default),
  append-only `attach_label`/`attach_outcome`, `get_episode`/`labels_for`/`outcomes_for`/`query`/`count`,
  **`fused_reward`** (confidence-weighted, outcome>explicit>implicit>judge per ADR 0006),
  **`delete_by_subject`** (GDPR) + **`purge_expired`** (retention TTL).
- **Verified:** 55 tests total, all green (incl. 7 PII + 15 store). Episode body immutable; labels/
  outcomes attach over time; scrub proven before persistence; subject-delete cascades; TTL purge works.

**Live findings:** none (offline stage).
**Next:** Stage 2 — `AgentTap` + normalizer + collectors.

---

## Stage 2 — AgentTap + normalizer + SDK-wrapper collector ✅ DONE (2026-06-13)
**Scope note:** built the "richest-first" slice that's independently verifiable offline — the tap core
+ the **SDK wrapper** (full-fidelity, our-code path). The external collectors (LiteLLM proxy, OTel,
MCP/ContextForge) need the demo agents (Stage 3) + live services to integration-test, so they plug in
behind the same `AgentTap` core later. (ADR 0008.)

**Done:**
- `providers/base.py` — `LLMProvider` Protocol + `CompletionResult` (the model-agnostic seam; ModelArk
  client already matches it).
- `tap/core.py` — `AgentTap` / `EpisodeRecorder` / `TurnRecorder`: accumulate turns+steps, normalize to
  an `Episode`, emit to a sink (e.g. `TrajectoryStore.put_episode`). **Fail-open** (sink errors never
  reach the parent; `on_error` hook); context-manager marks `partial` on exception.
- `tap/sdk_wrapper.py` — `wrap(provider, turn_provider=…)`: transparent LLMProvider wrapper recording
  each completion as a full-fidelity `model_call` step (messages, reasoning, tool_calls, tokens, timing);
  records errors then re-raises unchanged; recording failures can't break the call.
- **Verified:** 67 tests total (+12). Incl. end-to-end tap → real store with scrub-at-ingest; fail-open
  proven (sink throws / resolver throws → call + finish still succeed).

## Stage 3 — Two demo agents (synthetic data), tapped ✅ DONE (2026-06-13)
**Done:**
- `demos/corpus.py` — synthetic, zero-PII data: support KB + ORDERS; RAG `DOCS` corpus + frozen `GOLD`
  Q&A set (reference answers + expected cited doc ids; the promotion-gate ruler, never trained on) +
  tiny lexical `search_docs`.
- `demos/agents.py` — `DemoAgent` base (tapped model→tool loop) + `SupportAgent` (kb_lookup,
  order_status tools) + `RagAgent` (search_docs retrieval, cites doc ids). Provider-agnostic.
- `scripts/demo_agents.py` — live runner (real ModelArk → SQLite store).
- **Verified offline:** 73 tests (+6); agents record complete trajectories (tool_call + model_call
  steps, reasoning, context injection); partial episode on provider error.
- **Verified LIVE (real ModelArk):** both agents answered correctly; RAG cited the expected doc on all
  3 gold questions; 5 episodes stored — `sdk_wrapper`, **pii=scrubbed**, real endpoint id, model_call
  tokens + reasoning captured. Stages 0→3 compose end-to-end on live infra. ✅

## Stage 4 — Evaluation / Labeling ✅ DONE (2026-06-13)
**Done:**
- `eval/judge.py` — `PairwiseJudge` (recused; constructor RAISES if judge==policy). Order-randomization
  de-bias (child A/B slot de-mapped back), rubric + strict-JSON output (robust parse), → `judge` Label.
- `eval/outcomes.py` — the ANCHOR (deterministic, no LLM): `support_outcome` (grounded + answered, not
  punted) and `rag_outcome` (citation + retrieval + reference-match vs gold) → `outcome` Labels.
- `eval/health.py` — `judge_reference_agreement` (drift kill-switch signal) + `reward_hacking_alarm`
  (judge↑ while outcome flat).
- Fusion reuses the store's `fused_reward` (outcome > judge), proven anchored.
- **Verified offline:** 90 tests (+17). **Verified LIVE:** DeepSeek-V4-pro judge picked the better
  answer AND position-de-bias resolved correctly (child in slot B → winner=child, score 1.0).

**Next:** Stage 5 — Experience Memory (VikingDB REST adapter; control plane uses `Action=` params).

## Stage 5 — Experience Memory (VikingDB) ✅ LIVE WORKING (2026-06-13, after fixes)
**RESOLVED — the data-plane 403 was `service="air"`; the V2 API uses `service="vikingdb"`.**
The control/data plane V2 calling-process docs were the key. Our oracle test gave false confidence
(we fed the SDK the same wrong "air", so they agreed while both wrong vs the live server). Live API =
the real oracle. Also: V2 upsert key is **`data`** (not `fields`); collection uses **server-side
vectorize** (skylark-embedding-vision-251215, 2048-dim) → upsert TEXT in `situation`, query by TEXT via
`/api/vikingdb/data/search/multi_modal` (not raw dense_vector).

**LIVE VERIFIED:** auth OK (service=vikingdb), upsert OK (3 lessons, server-side embedded), semantic
search OK — "how do refunds work?" ranked the refund lesson top (0.615). Adapter refactored to the
text-vectorize shape; `service` default fixed to "vikingdb"; collection/index names default to
ankur_aprntc_collection / ankur_aprntc_index, dim 2048. 104 tests green.

**FULLY LIVE-VERIFIED (2026-06-13):** scalar fields added to the index (console) → FILTERED retrieval
works: query "how do refunds work?" + min_reward=0.8 → refund directive (0.617), order-status (0.7)
correctly excluded. Also verified: stable content-derived lesson ids (re-upsert updates, not
duplicates — `content_lesson_id`), and `/api/vikingdb/data/delete` by ids. Stage 5 = DONE, all ops
(auth, upsert/server-side-embed, filtered hybrid search, dedup, delete) proven on live infra. 105 tests.

### (historical) earlier diagnosis — kept for context
## Stage 5 — Experience Memory (VikingDB) ⏳ OFFLINE DONE, LIVE BLOCKED (2026-06-13)
**Done (offline, 104 tests green):**
- `memory/base.py` — `MemoryStore` Protocol + `Lesson`/`LessonType`/`RetrievedLesson`.
- `memory/mmr.py` — cosine + MMR diversification (pure).
- `memory/vikingdb.py` — REST adapter: control-plane `Action=` calls (CreateVikingdbCollection/Index),
  data-plane fixed paths (upsert/search/vector), `dense_weight` hybrid + recursive filter DSL,
  `pii_status=scrubbed` always enforced, 100-row upsert batching, MMR over candidates. **HTTP transport
  injectable** → request construction + parsing tested against the REAL adapter offline.
- 14 new tests (104 total). Signing still byte-for-byte == SDK oracle.

**LIVE BLOCKER — VikingDB data-plane auth (needs user/account action):**
- Control plane ACCEPTED our signature (returned business error `InvalidAction` code 100008 with
  authenticated ResponseMetadata) → signing + creds valid there, but **Action/Version string wrong**
  for this region (confirm exact V2 Action names + Version from console/docs).
- Data plane REJECTED the SAME signer: `403 AccessDenied "check signature failed"` on BOTH candidate
  hosts (`api-vikingdb.vikingdb.ap-southeast-1.bytepluses.com` and `api-vikingdb.mlp.ap-mya.byteplus.com`).
  Our signer is byte-for-byte == volcengine SDK (oracle), and the control plane accepts it → NOT a code
  bug. Likely: (1) data plane = a separately-provisioned VikingDB *instance* needing console
  setup/instance-specific credential; (2) credential type mismatch (VIKINGDB_AK is 47ch prefix `AKAP`,
  SK 59ch — may be instance-scoped); (3) a required header/param specific to the data gateway.
- NOTE: Stage-0 only ever tested the CONTROL host (got "missing Action"), never the data host — so no
  contradiction; this is the first real data-host auth test.
- `scripts/demo_memory.py` written (creates collection+index, upserts, hybrid search) — re-run once the
  data-plane credential/provisioning is sorted.

**Update (2026-06-13):** corrected VIKINGDB_SK (now 60ch, base64 `=`-terminated) — data plane STILL
403s. **Definitive test:** signed the same data-plane request with the OFFICIAL volcengine SDK and sent
it → also `403 AccessDenied`. So this is conclusively NOT our code (vendor SDK fails identically); it is
account/provisioning. Decision: **user creates the collection + index from the BytePlus Console**
(also resolves the control-plane `InvalidAction`, since the instance/Action/Version come from the console).

**Need from console after creation (to finish live verify):** (1) exact collection + index names,
(2) data-plane host/endpoint for the instance, (3) any instance-scoped AK/SK, (4) field schema incl.
vector field name + dim. Then re-run `scripts/demo_memory.py` (adjust collection/index/dim to match).

**Next:** proceed to Stage 6 (Distillation + Child runtime) against the proven MemoryStore interface in
parallel; finish VikingDB live verify when console provisioning is done.

## Stage 6 — Distillation + Child runtime ✅ DONE (2026-06-13) — LOOP CLOSED
**Done:**
- `distill/playbook.py` — `Playbook` (system prompt + exemplars + directives + watch_out, content-
  addressed hash, token-budgeted render) + `PlaybookDiff` (attributable: provenance lesson_id→item;
  `apply` increments generation + dedups + caps change/gen; `revert` = single-lesson rollback).
- `distill/distiller.py` — buckets scored episodes by fused reward (success/failure), mines lessons via
  LLM, success→directives / failure→watch_out, builds an attributable diff.
- `distill/child.py` — `ChildAgent`: clone of parent driven by the Playbook (rendered system prompt) +
  optional memory retrieval (records a `memory_retrieve` step; best-effort — memory errors don't break it).
- 12 new tests (117 total). 
- **LIVE END-TO-END (`scripts/demo_loop.py`):** parent runs → episodes scored (support_outcome) →
  distiller mines 3 lessons → upserted to VikingDB → child G1 built (playbook diff applied) → child
  retrieves from memory at inference. The observe→label→distill→improve loop is CLOSED on live infra. ✅

## Stage 7 — Promotion gate + Lineage + UI ✅ DONE (2026-06-13) — MVP COMPLETE
**Done:**
- `promote/stats.py` — Wilson score CI for win-rate + `GateReport` (all-gates-must-hold `passed`).
- `promote/gate.py` — `PromotionGate`: parent vs child on a held-out set, recused pairwise judge,
  order-balanced (alternating A/B slot), acceptance bar (win-rate≥55%, CI-low>50%, loss<10%) + ZERO-
  tolerance hard gates (regression/safety via per-case checkers). Offline replay.
- `promote/lineage.py` — `LineageRegistry`: generation DAG (G0→G1→…), promote appends + advances
  `current`, rollback reverts to parent gen; JSON-persisted.
- `ui/review_app.py` — Streamlit human gate: shows diff + metrics + hard-gate flags, Promote (disabled
  until bar passes) / Rollback; reads a JSON review bundle (decoupled from live calls).
- 15 new tests (132 total).
- **Fix:** ModelArk client default timeout 60s→300s; judge calls now `thinking="disabled"` (judge scores
  from a rubric, doesn't need CoT) — fixed a judge read-timeout on the deep-reasoning DeepSeek model.
- **LIVE END-TO-END (`scripts/demo_promotion.py`):** parent→distill→child(playbook+memory)→GATE→lineage.
  Gate correctly **REJECTED** an underperforming child (win 25%, CI [5%,70%]) and kept parent at G0 —
  the safety gate working as designed. Review bundle written for the UI. ✅

**THE MVP IS COMPLETE.** The full observe→label→distill→evaluate→promote loop runs end-to-end on live
BytePlus infra, with the human-gated acceptance bar protecting against bad promotions.

### Next: the deliverable below (design doc) — UPDATE it to reflect Stage 7 complete.

## 📌 DELIVERABLE (user request, 2026-06-13): on Stage 6 completion
When Stage 6 completes, produce a **Design & Solution document** (committed `.md`) — a comprehensive
write-up of the built system: architecture, the closed observe→label→distill→evaluate→promote loop,
component design, data flow, the BytePlus integration (ModelArk + VikingDB), key decisions (link ADRs),
and how the apprentice produces a better child. Target: `docs/DESIGN_AND_SOLUTION.md`. Do NOT skip.

## Web dashboard (React + FastAPI) — ⏳ backend DONE, frontend SCAFFOLDED (2026-06-14)
User wanted a modern, professional UI (Streamlit replaced). Decision: **React + FastAPI**, full
dashboard (4 screens), **light/dark theme toggle**.
- **Backend (DONE, runnable + tested):** `src/aprntc/web/app.py` — FastAPI REST API over the engine:
  `/api/review` (gate report + diff), `/api/lineage` + promote/rollback, `/api/trajectories[/{id}]`,
  `/api/lessons`. Injectable `AppState` (real store/lineage/memory or fakes). New `[web]` extra
  (fastapi+uvicorn). 13 API tests (145 total). **Bug fixed:** TrajectoryStore now `check_same_thread=
  False` (FastAPI services requests on a thread pool — would have broken the live server).
- **Frontend (SCAFFOLDED, ready to run — needs Node):** `web/` — Vite + React + TS + Tailwind, light/dark
  theme tokens (`src/index.css`), typed API client, app shell + sidebar nav, 4 screens (Review, Lineage,
  Trajectories, Lessons). Linear/Vercel-style. **Node not installed on build machine** → `cd web && npm
  install && npm run dev` (proxies /api → uvicorn). Cross-file refs verified by hand (couldn't run tsc).
- Streamlit UI (`src/aprntc/ui/`) retained as the no-Node fallback.

**Next:** user installs Node → `npm install && npm run dev` to bring the dashboard live; verify render.

## Backlog / later stages (per docs/DESIGN.md §8)
- Stage 2 collectors (deferred within stage): LiteLLM proxy → OTel ingester → MCP/ContextForge.
- Stage 3: the two demo agents (support-chat + RAG-Q&A, synthetic data).
- Stage 4: Evaluation/Labeling (pairwise judge, outcome-joiner, fusion).
- Stage 5: Experience Memory (VikingDB REST adapter — remember control-plane `Action=` finding).
- Stage 6: Distillation + Child runtime.
- Stage 7: Promotion gate + Lineage + Streamlit UI.
