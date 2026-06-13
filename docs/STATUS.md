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

**Next:** Stage 3 — the two demo agents (support-chat + RAG-Q&A, synthetic data), tapped via the wrapper.

## Backlog / later stages (per docs/DESIGN.md §8)
- Stage 2 collectors (deferred within stage): LiteLLM proxy → OTel ingester → MCP/ContextForge.
- Stage 3: the two demo agents (support-chat + RAG-Q&A, synthetic data).
- Stage 4: Evaluation/Labeling (pairwise judge, outcome-joiner, fusion).
- Stage 5: Experience Memory (VikingDB REST adapter — remember control-plane `Action=` finding).
- Stage 6: Distillation + Child runtime.
- Stage 7: Promotion gate + Lineage + Streamlit UI.
