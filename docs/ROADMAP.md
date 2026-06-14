# aprntc — Roadmap (post-MVP)

> The MVP (stages 0–7) is complete and live-verified, plus the web dashboard + "Try an agent".
> This file tracks what comes next so nothing is lost across sessions. Two categories:
> **(A) planned v1+ features** (from the planning sessions — advance the product thesis) and
> **(B) productionization** (make the existing system deployable/robust — engineering, not new features).

## A0 — Distillation quality: DONE + a key product insight (2026-06-14)
**Built (real, tested):** the distiller now produces (a) **concrete exemplars** — high-reward real
answers the child imitates (far stronger than abstract rules for in-context learning), (b) **specific
directives** mined from task + tools-used + clustered by situation, with an anti-generic filter that
drops platitudes ("be concise"), and (c) failure-pattern warnings. Gold/held-out set expanded 5→20 so a
win-rate CI can actually be powered (N=4 could never clear 50%). +4 distiller tests.

**KEY FINDING (documented honestly, not a bug):** even with much better lessons, the DEMO child cannot
beat the demo parent — because **Seed-2.0-pro is already optimal on these easy synthetic tasks; there is
no headroom to improve.** RAG factual lookups: parent already correct → judge ties → ~50% ceiling.
Support: a bare strong LLM already gives fluent answers → grounding in terse synthetic KB facts doesn't
"win." **The apprentice can only measurably beat a parent where the parent genuinely fails/is
inconsistent AND there's ground truth to steer toward.** Our synthetic demo lacks that gap by design.
This is exactly why PRODUCTION headroom is real (customer agents make domain-specific mistakes,
outdated info, edge-case failures) and why a clean synthetic demo is the wrong place to *show* a win.

**Implication for the roadmap:** "make the demo child pass the gate" is the wrong goal (parent too good;
passing would require gaming the judge or a contrived weak parent). The distiller mechanics are now
genuinely better; demonstrating a win needs either (i) a deliberately flawed demo parent with real
mistakes to fix, or (ii) real production traffic (A2). Deferred that choice; mechanics shipped.

## A0b — Real BytePlus support agent + the loop PROVEN with headroom (2026-06-14)
Built a REAL doc-grounded demo parent (the eventual production agent):
`src/aprntc/demos/byteplus/` — `build_kb()` chunks the actual BytePlus docs on disk
(641 chunks / 39 doc areas: ModelArk LLM, VikingDB ×29, image/video/speech gen, files),
local keyword retrieval; `ByteplusSupportAgent` answers + cites, with a **thin** parent
config (k=2, terse prompt, no citation discipline → real mistakes) and a **rich** child
config (k=4, grounding + citation discipline) + `as_child(playbook)`; a 20-item hard
`GOLD` set; `byteplus_outcome` scorer (grounded + cited + correct). +12 tests (165 total).
Demo: `scripts/demo_byteplus_loop.py`.

**RESULT — the apprentice loop WORKS on a real agent:** thin parent → distill → rich
child, gated on the hard gold set, judged by the recused judge → child **wins 65–85%**
across runs (one run: 85%, CI [54%, 96%]). This is a genuine, measurable improvement of a
real BytePlus agent — the headroom (thin vs rich) is honest, not gamed.

**Honest caveat (kept, not tuned away):** it doesn't *reliably* clear the strict gate
(win≥55%, CI-low>50%, loss<10%). With a strong base model (Seed-2.0-pro) BOTH parent and
child are often correct; the judge then flips on style, producing ~25–35% "losses" that
push loss-rate over the 10% bar. The margin is real but moderate — a strong base model
limits how much a parent can be *wrong*. Over-tuning the child prompt for conciseness made
it WORSE (30%), confirming the substance-rich answers are genuinely better; we reverted.
This mirrors A0's insight: bigger, more decisive wins need a parent with bigger real flaws
(or real production traffic, A2). Chose to keep it real + documented, not chase a lucky pass.

## Current focus & locked sequencing (user, 2026-06-14)
Build order: **(0) Trajectories-detail thumbs feedback → A1 → A2 → [PAUSE] → A3 → A4 → A6 → then (B)**.
- **(0) DONE-NEXT:** wire 👍/👎 into the Trajectories detail view (thumbs currently only on "Try an agent").
- **A1 DONE** (external collectors). **A2 DONE** (online shadow/canary). **A3 DONE** (learned fusion).
  User tested the BytePlus agent (21 eps / 9 thumbs); A3 built + proven, activates once judge+anchor
  co-occur on episodes (current data has anchors only). **A4 DONE** (auto-promotion, default-off,
  hard-gated). **A6 DONE** (multi-agent fleets). **A-TRACK COMPLETE except A5** (deferred, closed-source
  — user to decide drop vs park). **→ (B) productionization next** (B0 Playbook/Config-fetch API first).
- **⏸ BEFORE A3:** STOP and tell the user — they will do **real testing with the "BytePlus support"
  agent** to generate real data first (A3 = learned fusion weights needs accumulated real data).
- **A4** after A3. **A5 SKIPPED for now** (see note). **A6** after A4.
- **⚠️ A5 reminder (raise with user before any A5 work):** fine-tuning (PEFT/LoRA) only applies to
  **open-source/open-weight** models. The user's current LLMs (Seed-2.0-pro, DeepSeek-V4-pro via
  ModelArk) are **closed-source → fine-tuning NOT possible** on them. Discuss whether to (a) keep A5
  for a future open-weight model, or (b) drop it. Do NOT start A5 without that discussion.
- After ALL (A) tasks → move to (B) Productionization.

## (A) Planned v1+ features (from planning sessions — canonical list)
Ordered by recommended sequence:

1. **A0 — Distillation quality** *(current)* — richer lesson mining (cluster by situation, more lessons,
   prune low-efficacy), larger gold/held-out sets for a powered win-rate, reference-guided distillation.
   Goal: a child that reliably clears the acceptance bar. *(Adjacent to learned-fusion; non-MVP-blocking
   in the original plan but the practical prerequisite for everything else.)*
2. **A1 — External tap collectors** ✅ DONE (2026-06-14). Built behind the AgentTap core, all normalize
   into the canonical Episode, all unit-tested offline (the external services only deliver raw dicts):
   - **Egress proxy** (`tap/egress_proxy.py`) — LiteLLM `CustomLogger`; `handle_event()` is the pure
     normalize+emit core (fail-open, testable w/o litellm); `make_proxy_logger()` builds the real
     CustomLogger when the `[proxy]` extra is installed. Captures model traffic for closed-source agents.
   - **OTel ingester** (`tap/otel_ingest.py`) — `span_to_episode()`/`spans_to_episodes()` map GenAI spans
     (tolerant union of OpenLLMetry `gen_ai.*` + OpenInference `llm.*`); pure dict→Episode (run the OTel
     Collector externally, point its export at this). Fidelity=partial.
   - **MCP interceptor** (`tap/mcp_ingest.py`) — `mcp_record_to_step()`/`mcp_records_to_episode()` map an
     MCP gateway's (e.g. ContextForge) tool-call logs/OTel-spans to tool steps (full fidelity).
   - Shared `tap/normalize.py`; +19 tests (188 total).
   - **Live-verify deferred:** each needs its external service (LiteLLM gateway / OTel Collector / MCP
     gateway) to exercise end-to-end — wire when a real external parent is connected. Mapping logic proven.
3. **A2 — Online shadow / A-B canary** ✅ DONE (2026-06-14). `src/aprntc/online/`:
   - `shadow.py` `ShadowRunner` — on each live request, shadow the child vs the parent (output
     discarded), judge pairwise, accumulate live win-rate + Wilson CI; async + **fail-open** (shadow
     never affects the user's response), sampled (`sample_rate`), position-debiased; `ready_to_promote()`
     applies the acceptance bar to live stats.
   - `canary.py` `CanaryController` — post-promotion staged rollout (5%→25%→50%→100%); deterministic
     hash routing (stable per user, no `random`); push-based metric feed; **auto-rollback** when the
     child's mean reward falls below the parent's baseline by `degrade_margin`.
   - +11 tests (199 total). Live-verify needs real traffic (that's the point) — wire at deploy.
4. **A3 — Learned fusion weights + judge calibration** ✅ DONE (2026-06-14).
   `eval/fusion.py` `learn_weights()` — calibrates each source by its agreement with the anchor
   (outcome > human > explicit) on the SAME episode; a source that disagrees gets auto-down-weighted
   (blend + min_n guard for cold-start). `store.fused_reward(weights=...)` accepts the learned map;
   `store.learn_fusion_weights()` learns from its own history. +9 tests (211 total). Verified: a judge
   that contradicts real user feedback over 12 episodes drops 0.40 → 0.23.
   **DATA NOTE:** activation needs episodes with BOTH a judge label AND an anchor (outcome/feedback) on
   the same episode. Current real data (21 eps, 9 thumbs) has anchors but NO judge labels (the judge
   only runs in the gate/shadow, not on individual Try-an-agent runs) → weights stay at priors until
   shadow/gate runs accumulate judge+anchor pairs. A3 falls back to priors safely until then.
5. **A4 — Auto-promotion (low-risk diffs)** ✅ DONE (2026-06-14). `promote/auto.py`
   `AutoPromotionPolicy.decide(gate, diff, trust)` → AUTO_PROMOTE / HUMAN_REVIEW / REJECT.
   **Default-OFF (opt-in)** per "human now, auto later". Auto fires ONLY if ALL clear: enabled +
   gate.passed + MARGIN above the bar (win≥60%, CI-low>55%, loss<5% — stricter than the 55/50/10 bar) +
   zero regression/safety (hard) + low-risk diff (small + additive) + established trust (≥0.80, e.g. A3
   judge↔outcome agreement). Anything short → HUMAN_REVIEW (never silent reject); failed gate → REJECT.
   Every blocked guardrail is reported for audit. +11 tests (222 total). Wiring into the live promote
   flow / dashboard is a small follow-up (policy is the decision core).
6. **A5 — Fine-tuning (PEFT/LoRA)** ⏸ PARKED (user decision 2026-06-14): **future / open-weight models
   ONLY.** NOT applicable to the current closed-source stack (Seed-2.0-pro, DeepSeek-V4-pro via ModelArk
   — weights can't be changed). Phase-1 playbook+memory already does the job without it. Revisit ONLY if
   an open-weight model is adopted AND prompt-context hits a ceiling; then PEFT compresses validated
   lessons into weights ON TOP of memory+playbook (never replaces them). No work now.
7. **A6 — Multi-agent fleets / cross-agent lesson sharing** ✅ DONE (2026-06-14). `src/aprntc/fleet/`:
   - `registry.py` `Fleet` + `AgentRef` — many parent agents under one apprentice, each with its OWN
     lineage (per-agent generations/playbook path); `by_domain()` scopes peers. JSON-persisted.
   - `sharing.py` `share_lessons()`/`shareable_lessons()` — offer one agent's lessons to another, GATED:
     reward gate (only good lessons), type gate (directives/failure-patterns/routing; NOT source-specific
     exemplars), dedup by stable content id, and `shared_from` provenance tagging. Domain scoping via
     `Fleet.by_domain`.
   - +9 tests (231 total). Wiring into the dashboard/distillation flow is a follow-up.

## Known issues / revisit later
- **BytePlus agent RAG quality** (user, 2026-06-14): retrieval+answers still not great after the KB
  expansion + TF-IDF/title-boost. Local keyword search has a ceiling at 1040 chunks. Likely next steps
  when revisited: (a) semantic embeddings retrieval (use BytePlus Embedding API / VikingDB instead of
  keyword), (b) better chunking (current heading-split can fragment tables/params), (c) rerank top-k.
  Deferred by user — "work on it later".

## (B) Productionization (not planned features — deployment/robustness)
Real work to run aprntc as a product, but never part of the planning-session feature roadmap:

- **B0 — Playbook registry + Config-fetch API** ✅ DONE (2026-06-14). `src/aprntc/serving/`:
  `PlaybookRegistry` (per-agent versions + active pointer; `register` G0, `ensure_g0_from_traffic`
  infer-fallback, `promote`/`set_active`/`rollback`, JSON-persisted) + REST endpoints
  `POST /api/playbooks/{id}/register`, `GET /api/playbooks/{id}/active`, `POST .../rollback`. The
  external agent does a one-line `GET .../active` fetch; promotion flips what's served. +12 tests
  (243 total). **Verified live:** register G0 → fetch active returns the rendered prompt over HTTP.
  Still needs auth/multi-tenancy (B2) for per-customer isolation; a tiny client SDK helper is optional.
- **B1 — Deploy** ✅ DONE (2026-06-14). Single-container deploy: multi-stage `Dockerfile` (node builds
  `web/dist` → python runtime serves API + static UI on :8000, no Node in final image),
  `docker-compose.yml` (env_file + `/data` volume), `.dockerignore` (no secrets/local data in image),
  `docs/DEPLOY.md`. App serves the SPA via `_mount_static` (env `APRNTC_STATIC_DIR`; optional so dev/Vite
  + tests unaffected; `/api/*` never shadowed). +3 tests (260 total). **Verified live:** built frontend
  served by uvicorn on one port — `/`, `/trajectories` (SPA), `/api/health`, `/assets/*` all 200.
  (Docker build itself unrun — Docker not installed on this machine; the integration it orchestrates is
  verified.) Follow-ups: Postgres for scale + multi-worker (B3); TLS at ingress.
- **B2 — Auth + multi-tenancy** ✅ DONE (2026-06-14). `src/aprntc/tenancy/`:
  `TenantStore` (tenants + API keys stored HASHED, never plaintext; create/issue/revoke/rotate/
  deactivate; authenticate) + `TenantResolver` (API key → tenant → that tenant's ISOLATED storage paths
  `{root}/{tenant_id}/...`). Wired into the web API: an optional `AppState.tenant_resolver` — when set,
  the externally-facing playbook endpoints require a key (X-API-Key / Bearer) and serve each tenant's own
  registry; when unset, single-tenant/dev mode (unchanged). +14 tests (257 total); verified tenant B
  can't read tenant A's data even with the same agent_id.
  **Follow-up:** apply the same tenant scoping to the OTHER endpoints (trajectories/lineage/lessons/
  feedback) — currently those still use the shared dev state; B0 playbook endpoints are the
  externally-critical ones and are isolated. Dashboard login UI is part of B4.
- **B3 — Robustness/ops** — background job scheduler for nightly distillation, retries, observability of
  aprntc itself, rate/cost controls, Postgres swap for the SQLite trajectory store at scale.
- **B4 — UI polish** — remaining screen edge cases, loading/error states, real-time updates.

## What's done (for reference)
MVP stages 0–7 (signing gate, trajectory schema/store, AgentTap+SDK-wrapper collector, demo agents,
eval/labeling, VikingDB memory, distillation+child runtime, promotion gate+lineage); web dashboard
(FastAPI + React, 5 screens incl. "Try an agent"); all live-verified on BytePlus. See STATUS.md.
