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

## Stage 1 — Trajectory schema + Trajectory Store ⏳ IN PROGRESS
**Part 1 — schema ✅ DONE (2026-06-13):**
- Schema designed (dedicated pass), locked as **ADR 0007**, implemented in
  `src/aprntc/trajectory/schema.py` (stdlib dataclasses: Episode/Turn/Step/ContentPart/Label/Outcome
  + enums). Media **by reference** (no inline blobs); `schema_version`; `partial` flags;
  per-step `source_fidelity`; `pii_status`. **19 round-trip/edge-case tests, all green (33 total).**

**Part 2 — Trajectory Store ⏳ NEXT:**
- System of record (SQLite to bootstrap) — PII-scrub at ingest, append-only labels/outcomes,
  materialized fused `reward` view, `delete_by_subject` + retention TTL.
- **Verify:** schema round-trips through the store; PII scrubbed before persistence.

---

## Backlog / later stages (per docs/DESIGN.md §8)
- Stage 2: `AgentTap` + collectors (SDK wrapper → LiteLLM proxy → OTel → MCP/ContextForge).
- Stage 3: the two demo agents (support-chat + RAG-Q&A, synthetic data).
- Stage 4: Evaluation/Labeling (pairwise judge, outcome-joiner, fusion).
- Stage 5: Experience Memory (VikingDB REST adapter — remember control-plane `Action=` finding).
- Stage 6: Distillation + Child runtime.
- Stage 7: Promotion gate + Lineage + Streamlit UI.
