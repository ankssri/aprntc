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

## Current focus
**→ next: pick A2 (online shadow) or build a flawed-parent demo** — see A0 implication above.

## (A) Planned v1+ features (from planning sessions — canonical list)
Ordered by recommended sequence:

1. **A0 — Distillation quality** *(current)* — richer lesson mining (cluster by situation, more lessons,
   prune low-efficacy), larger gold/held-out sets for a powered win-rate, reference-guided distillation.
   Goal: a child that reliably clears the acceptance bar. *(Adjacent to learned-fusion; non-MVP-blocking
   in the original plan but the practical prerequisite for everything else.)*
2. **A1 — External tap collectors** — LiteLLM egress proxy (closed-source agents), OTel ingester
   (instrumented frameworks), MCP/ContextForge (MCP-tool agents). Lets aprntc tap REAL external parent
   agents, not just our own SDK-wrapped demos. *The connection mechanism for production (see PRODUCTION.md).*
3. **A2 — Online shadow / A-B canary** — run the child on LIVE production traffic in parallel (shadow:
   outputs discarded, judged pairwise vs parent) or post-promotion gradual rollout (canary) with
   auto-rollback. Turns "proven on a held-out set" into "proven on real traffic." The marquee v1 feature.
4. **A3 — Learned fusion weights + judge calibration** — auto-learn how much to trust each signal
   (outcome/explicit/judge) from historical agreement with the anchor; auto-down-weight a biased judge.
   Needs accumulated data.
5. **A4 — Auto-promotion (low-risk diffs)** — promote without human approval once judge↔outcome trust is
   established. The payoff of the autonomous-loop thesis. (User decision: human now, auto later.)
6. **A5 — Fine-tuning (PEFT/LoRA)** — Phase-2: compress validated lessons into model weights when prompt
   length/latency hits a ceiling. Sits ON TOP of memory+playbook, never replaces it.
7. **A6 — Multi-agent fleets / cross-agent lesson sharing** — one apprentice across many parent agents;
   share lessons between them.

## (B) Productionization (not planned features — deployment/robustness)
Real work to run aprntc as a product, but never part of the planning-session feature roadmap:

- **B1 — Deploy** — containerize the FastAPI backend; serve the built React frontend (static) behind it
  or a CDN; env/secrets management; a hosted VikingDB/Postgres.
- **B2 — Auth + multi-tenancy** — login, per-customer isolation of trajectories/lessons/lineage.
- **B3 — Robustness/ops** — background job scheduler for nightly distillation, retries, observability of
  aprntc itself, rate/cost controls, Postgres swap for the SQLite trajectory store at scale.
- **B4 — UI polish** — remaining screen edge cases, loading/error states, real-time updates.

## What's done (for reference)
MVP stages 0–7 (signing gate, trajectory schema/store, AgentTap+SDK-wrapper collector, demo agents,
eval/labeling, VikingDB memory, distillation+child runtime, promotion gate+lineage); web dashboard
(FastAPI + React, 5 screens incl. "Try an agent"); all live-verified on BytePlus. See STATUS.md.
