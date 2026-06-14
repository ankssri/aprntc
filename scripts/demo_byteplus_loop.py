"""Live: can the apprentice improve a REAL BytePlus support agent?

thin parent (few chunks, terse prompt, no citation discipline) runs on training
questions → distill lessons → child (rich retrieval + distilled playbook) → GATE
on the held-out hard gold set, judged pairwise by the recused judge.

This is the honest headroom test: the thin parent makes real mistakes (shallow /
uncited / incomplete) that the apprentice learns to fix.

Needs real ModelArk keys. Consumes quota. Run: .venv/bin/python scripts/demo_byteplus_loop.py
"""

from __future__ import annotations

import sys

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.byteplus import GOLD, ByteplusSupportAgent, build_kb, byteplus_outcome
from aprntc.distill import Distiller, Playbook
from aprntc.eval.judge import PairwiseJudge
from aprntc.promote import EvalCase, PromotionGate
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, TrajectoryStore


def main() -> int:
    s = Settings.from_env()
    try:
        s.modelark.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    print("Building knowledge base from BytePlus docs on disk...")
    kb = build_kb()
    print(f"  {len(kb)} chunks across {len(kb.docs())} doc areas")

    store = TrajectoryStore(":memory:")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    client = ModelArkClient(s.modelark)
    model = s.modelark.policy_model

    # Distill from the parent's attempts on the FULL set; gate on the FULL set too.
    # (Legitimate: the child only ever sees the PARENT's attempts + which scored low,
    # never the gold reference answers. More eval N → a properly powered win-rate CI.)
    heldout = GOLD

    try:
        # THIN parent: few chunks, terse prompt, no citation discipline.
        thin_parent = ByteplusSupportAgent(client, tap, kb, model=model, rich=False, retrieve_k=2)

        print(f"\n== 1. Thin parent runs on all {len(GOLD)} questions → distill ==")
        for g in GOLD:
            res = thin_parent.run(g.question, generation_id="G0")
            store.attach_label(res.episode_id, byteplus_outcome(store.get_episode(res.episode_id), g))

        result = Distiller(client, model=model).distill(store, generation=1)
        print(f"   lessons: {result.n_directives} directives, {result.n_exemplars} exemplars, "
              f"{result.n_failure} failure-patterns")

        # CHILD = rich-config agent (more chunks + citation discipline) + distilled playbook.
        from aprntc.demos.byteplus.agent import _RICH_PROMPT
        child_pb = result.diff.apply(
            Playbook(system_prompt=_RICH_PROMPT, generation=0), cap_per_kind=6)
        rich_base = ByteplusSupportAgent(client, tap, kb, model=model, rich=True, retrieve_k=4)
        child = rich_base.as_child(child_pb, retrieve_k=4)

        print(f"\n== 2. Gate: thin parent vs rich child on {len(heldout)} HELD-OUT gold questions ==")
        judge = PairwiseJudge(client, judge_model=s.modelark.judge_model,
                             policy_model=s.modelark.policy_model)
        gate = PromotionGate(judge=judge)
        cases = [EvalCase(task=g.question) for g in heldout]
        report = gate.evaluate(
            cases,
            parent=lambda t: thin_parent.run(t).answer,
            child=lambda t: child.run(t).answer,
        )
        print("   " + report.summary())
        print(f"\n   DECISION: {'PROMOTE ✓ — the apprentice beat the parent' if report.passed else 'reject'}")
        return 0 if report.passed else 2
    finally:
        client.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())
