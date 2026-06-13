# CLAUDE.md — aprntc

> **This file is auto-loaded every session. Read it first. It is the orientation card,
> not the full design — follow the pointers below for depth.**

## What aprntc is
An **apprentice** ("child") agent that shadows a live **parent** agent, distills lessons from the
parent's behavior, becomes a measurably better version, and — gated by a human — is **promoted** to
replace it. Then the cycle repeats. Codename **"Shadow."** Standalone, framework-agnostic product.

Loop: **observe → label → distill → evaluate → promote** (human only at the promotion gate).
Phase-1 learning = **Experience Memory (RAG) + playbook distillation** (NO fine-tuning yet).
Quality is **anchored on outcomes**, with a **recused LLM judge (judge ≠ policy)**.

## ⛔ SCOPING PRINCIPLE (governs every decision)
**aprntc is NOT a monitoring/observability product.** It learns from the parent's overall **response
quality** to produce a better successor. Capturing every log / network call / interaction is NOT a
goal — **episode/task-level quality signal** is what matters. When unsure, optimize for "can the
apprentice judge response quality," not "did we capture every trace."

## Invariants — DO NOT BREAK (these are load-bearing)
1. **judge ≠ policy** — the eval judge model must differ from the agent/policy model (anti self-preference).
2. **Distillation NEVER sees the gold/hold-out eval set** — it is the clean ruler; leaking it invalidates the acceptance bar.
3. **Tap is async + fail-open** — it must never slow or break the parent agent.
4. **Core stays dependency-light** — heavy deps go in optional extras (`[byteplus]`, `[proxy]`, `[otel]`, `[ui]`). Core never imports a collector's libs.
5. **Anti-lock-in** — bet on open protocols (OpenTelemetry, MCP, OpenAI wire format); every external tool sits behind our interface, swappable. Permissive licenses only (MIT/Apache-2.0), no user-scaling paywalls on features we use.
6. **Never commit secrets** — `.env` is gitignored; `.env.example` documents vars.
7. **PII scrubbed at ingest** + 30-day TTL on raw trajectories; never embed raw PII into VikingDB.

## Working agreement — to prevent regressions (READ EVERY TIME)
- **Run the full test suite GREEN before starting a change AND before every commit.** If it's red, stop and fix first.
  ```bash
  .venv/bin/python -m pytest          # all unit tests (incl. signing oracle)
  ```
- **Every stage's "verify" step becomes a PERMANENT regression test** — do not delete or weaken tests to make them pass; fix the code.
- **Adding a feature or fixing a bug? First confirm existing tests pass, make the change, then confirm they STILL pass.** New behavior needs new tests.
- A `PostToolUse` hook auto-runs tests after edits (see `.claude/settings.json`) — heed its output.
- **Commit only when the user asks.** Work on a branch, not `main`. End commit messages with the Co-Authored-By line.

## Current status
See **[docs/STATUS.md](docs/STATUS.md)** — the build log. Always read it to know what's done and what's next.
- **Stage 0 ✅** package skeleton + VikingDB SigV4 signing (oracle-verified + live-verified) + ModelArk client.
- **Next: Stage 1** — Trajectory schema (dedicated design pass, then lock) + Trajectory Store.

## Where the knowledge lives
- **[docs/DESIGN.md](docs/DESIGN.md)** — full canonical design (decisions, architecture, API contracts, build plan, acceptance bar). The source of truth for *what* and *why*.
- **[docs/decisions/](docs/decisions/)** — ADRs: individual decisions with rationale + rejected alternatives.
- **[docs/STATUS.md](docs/STATUS.md)** — per-stage build log + live findings.
- **BytePlus API docs** (reference, not in repo): `/Users/ankur/mdfiles/` (ModelArk) + `/Users/ankur/mdfiles/byteplus-vikingdb-docs/` (VikingDB V2 + signing oracle).

## Stack quick-reference
- **Models (BytePlus ModelArk, OpenAI-compatible):** policy = Seed-2.0-pro; judge = DeepSeek-V4-pro. Endpoint-ids in `.env`. Region `ap-southeast-1`.
- **Memory:** VikingDB via **REST** (our own SigV4 signer in `src/aprntc/byteplus/signing.py`). Data plane = fixed paths; **control plane = `Action=` query params** (live finding).
- **Tap collectors:** SDK wrapper (ours) + LiteLLM egress proxy + MCP via IBM ContextForge + OTel ingester. A2A deferred post-v1.
- **Layout:** `src/aprntc/` (package), `tests/`, `scripts/`, `docs/`.

## How to run
```bash
.venv/bin/python -m pytest                      # unit tests
.venv/bin/python -m pytest -m oracle            # signing oracle vs volcengine SDK
.venv/bin/python scripts/smoke_byteplus.py      # live: needs real keys in .env
```
