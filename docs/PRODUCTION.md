# aprntc — How it works in production

> The MVP demo uses two **dummy agents** (`SupportAgent`/`RagAgent`) with **synthetic data**
> (`demos/corpus.py`), run **manually**. That was a stand-in for a real parent agent so the loop could
> be built + proven offline. This doc explains what production actually looks like — the demo obscures it.

## Core principle: aprntc sits BESIDE your agent, never in front of it
aprntc is **not an agent runtime**. The customer's production agent keeps running exactly as today —
same code, infra, users. aprntc is a **separate service** that *watches* it, learns, and *proposes*
improvements. Coach on the sideline, not a player on the field.

**aprntc is never in the user request path.** It mirrors traffic asynchronously (fail-open). If aprntc
is down/slow/wrong, production is completely unaffected.

## Demo → production mapping
| Demo (what you saw) | Production (the real thing) |
|---|---|
| `SupportAgent`/`RagAgent` — toy agents we wrote | the customer's ACTUAL production agent (any stack) |
| `corpus.py` — fake KB + 4 planet docs | the customer's real knowledge/tools (we never touch them) |
| `scripts/demo_agents.py` run manually | live production traffic — real users, automatically |
| SDK wrapper baked into our demo agent | a **tap collector** mirroring the customer's traffic (v1+ A1) |
| outcome scorer with synthetic gold | real outcomes — ticket resolved, thumbs-up, answer accepted |

The machinery is real; the agent + data were placeholders for a customer we didn't have in dev.

## How the parent connects (3 integration modes — customer picks)
All three are **read-only async mirrors** — never gate/delay the user's request.
1. **SDK wrapper** (one-line code change): `client = aprntc.wrap(client)`. Richest data. *(demo used this)*
2. **Egress proxy** (zero code change): customer points their model `base_url` at an aprntc LiteLLM
   proxy; aprntc sees+forwards traffic. Works for CLOSED-source agents. *(v1+ A1)*
3. **OTel / MCP** (zero code change): if the agent emits OpenTelemetry traces or uses MCP tools, aprntc
   ingests that stream. *(v1+ A1)*

## Production lifecycle (automatic — no manual running)
- **Continuously (real-time):** real user traffic → tap mirrors → trajectory store.
- **Hourly:** judge + outcome scoring label the trajectories.
- **Nightly (batch):** distill lessons → build child G(n+1) → run the gate on a frozen held-out set.
- **Weekly (human moment):** reviewer opens the dashboard — "child beats parent 58%, here's the diff,
  approve?" → clicks Promote.
- **On regression:** one-click rollback (or auto-rollback if a live metric drops post-promotion).

## The single most important property
There is **exactly ONE** write back into production: the **gated config swap**. On human approval,
aprntc swaps the parent's **playbook** (system prompt + retrieved-lesson config) — NOT its code or
infra — and it's instantly reversible. Everything else is read-only observation. Worst case if aprntc
is wrong/down: "no improvement happened" — never "production broke."

## What "the child" actually is (and what gets promoted)
An agent = a **fixed engine** (LLM + retrieval + tools + loop) **+ a Playbook** (config artifact:
system_prompt + directives + exemplars + watch-out lessons). Parent and child share the SAME engine —
the ONLY difference is the Playbook. So:
- **The "child" is not a separate program** — it's the same agent running a candidate **Playbook G(n+1)**
  distilled from the parent's good/bad trajectories. (See `distill/playbook.py`, `as_child()`.)
- **The child "improves"** = the distiller edits its Playbook with lessons mined from where the parent
  succeeded/failed (directives + exemplars from wins, failure-patterns from losses).
- **Promotion = swap the Playbook** (point the live agent at G1 instead of G0). No model change, no
  redeploy. Rollback = point back to G0. Each Playbook is content-addressed (`hash`) → versioned +
  revertible. "Child becomes the new parent" = G1 is now live; the next child distills from G1.
- This is the Phase-1 mechanism (ADR 0006): playbook distillation, NOT fine-tuning — which is exactly
  why it works on CLOSED-source LLMs (Seed-2.0/DeepSeek): you can't change their weights, but you can
  change how they're prompted + what lessons/examples they're given. (Fine-tuning = A5, open-weights only.)
- Ceiling (honest): a Playbook makes the agent reliably APPLY lessons; it can't teach the base model
  capabilities it lacks. Two delivery channels for lessons: baked into the promoted Playbook (static) +
  retrieved from VikingDB memory per-query (dynamic).

## Connecting an EXTERNAL agent (e.g. someone's LangChain agent) — the integration contract
In the demo aprntc OWNS the agent + Playbook (in-process function calls). For an external agent aprntc
owns neither, so the Playbook becomes a **contract**, with an inbound and an outbound half:

**Inbound (observe) — built (A1).** The agent's traffic flows INTO aprntc via a tap (egress proxy / OTel
/ MCP). Read-only. This is how aprntc sees the parent's behavior without owning its code.

**Outbound (control) — B-track, NOT built yet.** The improved Playbook flows OUT to the agent. aprntc
can't push into the customer's process, so the model inverts: **the agent PULLS its config from aprntc.**

Decisions locked (2026-06-14):
- **Initial G0 = register, fallback to infer.** Customer registers their current system prompt/key
  instructions as G0 (aprntc needs only the prompt text, not code); if they don't, aprntc infers an
  approximate G0 from the system prompt the tap observes in traffic.
- **Delivery = Config-fetch API (primary).** aprntc serves the active Playbook; the customer adds a
  one-line fetch, e.g. `system_prompt = aprntc.get_active_playbook("agent-id")`. Promotion updates what
  aprntc serves; the agent picks up the new playbook. Rollback = aprntc serves G0 again. This makes the
  cross-process swap behave exactly like the demo's in-process swap — the fetch indirection IS the bridge.
  (PR/artifact + webhook delivery are possible later alternatives; config-fetch is the default.)

**Symmetry:** A1 tap = data flows IN (observation); Config-fetch API = playbook flows OUT (control).
Together = the full external integration. The outbound API + auth/multi-tenancy (per-customer playbook
isolation) are **B-track** (B1/B2) — design recorded here so it's not lost.

## How this maps to the roadmap (docs/ROADMAP.md)
- **A1 (external collectors)** = build the proxy/OTel/MCP tap → the production CONNECTION mechanism so a
  real external parent can attach without being one of our demo agents.
- **A2 (online shadow/canary)** = test the child against REAL live traffic before/at promotion.
Those two turn the proven-offline loop into a live production product. (A0 distillation quality comes
first — so there's a child worth promoting.)
