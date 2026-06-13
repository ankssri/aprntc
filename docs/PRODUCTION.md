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

## How this maps to the roadmap (docs/ROADMAP.md)
- **A1 (external collectors)** = build the proxy/OTel/MCP tap → the production CONNECTION mechanism so a
  real external parent can attach without being one of our demo agents.
- **A2 (online shadow/canary)** = test the child against REAL live traffic before/at promotion.
Those two turn the proven-offline loop into a live production product. (A0 distillation quality comes
first — so there's a child worth promoting.)
