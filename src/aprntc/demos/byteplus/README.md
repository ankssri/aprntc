# BytePlus support agent (real doc-grounded demo parent)

A production-bound demo parent that answers questions about the BytePlus AI stack
(ModelArk LLM, VikingDB, image/video/speech generation, files API) grounded in the
**actual BytePlus documentation**. Unlike the toy support/RAG demos, this agent has
genuine *headroom* for the apprentice to improve.

## Pieces
- `kb.py` — `build_kb()` chunks markdown docs (default: `/Users/ankur/mdfiles` +
  `.../byteplus-vikingdb-docs`) into retrievable passages; local keyword search.
  (Production: swap for VikingDB behind the same interface.)
- `agent.py` — `ByteplusSupportAgent`: retrieves doc chunks, answers, cites sources.
  - **thin** config (`rich=False`, `retrieve_k=2`, terse prompt): the parent —
    sometimes shallow / uncited / incomplete (real mistakes to learn from).
  - **rich** config (`rich=True`, more chunks, citation discipline): what a good
    child approximates. `agent.as_child(playbook)` makes a child driven by a
    distilled playbook.
- `gold.py` — `GOLD`: 20 hard BytePlus questions + reference facts (the held-out
  promotion-gate ruler; distillation must never train on it).
- `outcome.py` — `byteplus_outcome`: deterministic scorer (grounded + cited + correct).

## Run the loop (live, needs ModelArk keys)
```bash
.venv/bin/python scripts/demo_byteplus_loop.py
```
Thin parent runs the gold questions → distill lessons → rich child → gate (parent vs
child, recused judge). Observed: the child wins ~65–85% — a real, measurable improvement.

## The honest result (see docs/ROADMAP.md A0b)
The apprentice **demonstrably improves a real agent**. It doesn't always clear the
*strict* gate (loss-rate), because a strong base model means both parent and child are
often correct and the judge flips on style. The margin is real but moderate — bigger,
gate-clearing wins need a parent with bigger real flaws or real production traffic.

## Toward production
This is the agent intended for eventual production deployment. There, the parent is the
customer's real agent (connected via a tap — see `docs/PRODUCTION.md`), the corpus is the
customer's real docs/tools, and headroom is larger (real domain mistakes, outdated info).
