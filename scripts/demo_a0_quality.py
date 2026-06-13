"""A0 distillation-quality demo: does the IMPROVED distiller produce a child that
actually beats the parent on the larger held-out gold set?

Compares: parent (no lessons) vs child (exemplars + specific directives + memory)
on the 20-item RAG gold set, judged pairwise by the recused judge.

Needs real ModelArk keys. Consumes quota (parent + child + judge per gold item).
Run:  .venv/bin/python scripts/demo_a0_quality.py
"""

from __future__ import annotations

import sys

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.agents import RagAgent
from aprntc.demos.corpus import GOLD
from aprntc.distill import ChildAgent, Distiller, Playbook
from aprntc.eval.judge import PairwiseJudge
from aprntc.eval.outcomes import rag_outcome
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

    store = TrajectoryStore(":memory:")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    client = ModelArkClient(s.modelark)
    model = s.modelark.policy_model

    # Split gold: first half = training (parent runs → distill), second half = held-out eval.
    train, heldout = GOLD[:10], GOLD[10:]

    try:
        print(f"== 1. Parent runs on {len(train)} training questions → distill ==")
        parent = RagAgent(client, tap, model=model)
        for item in train:
            res = parent.run(item.question, generation_id="G0")
            store.attach_label(res.episode_id, rag_outcome(store.get_episode(res.episode_id), item))

        distiller = Distiller(client, model=model)
        result = distiller.distill(store, generation=1)
        print(f"   lessons: {result.n_directives} directives, {result.n_exemplars} exemplars, "
              f"{result.n_failure} failure-patterns")

        child_pb = result.diff.apply(
            Playbook(system_prompt=parent.system_prompt, generation=0), cap_per_kind=6)
        child = ChildAgent(parent, child_pb, memory=None)  # lessons baked into playbook

        print(f"\n== 2. Gate: parent vs child on {len(heldout)} HELD-OUT questions ==")
        judge = PairwiseJudge(client, judge_model=s.modelark.judge_model,
                             policy_model=s.modelark.policy_model)
        gate = PromotionGate(judge=judge)
        cases = [EvalCase(task=item.question) for item in heldout]
        report = gate.evaluate(
            cases,
            parent=lambda t: parent.run(t).answer,
            child=lambda t: child.run(t).answer,
        )
        print("   " + report.summary())
        print(f"\n   DECISION: {'PROMOTE ✓' if report.passed else 'reject'}")
        return 0 if report.passed else 2
    finally:
        client.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())
