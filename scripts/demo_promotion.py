"""Live end-to-end MVP demo INCLUDING the promotion gate.

  parent runs -> distill -> child(playbook+memory) -> GATE (parent vs child,
  recused judge, win-rate/CI/hard-gates) -> lineage promote/reject + review bundle.

Needs real ModelArk + VikingDB keys. Consumes API quota (judge calls per case).

Run:  .venv/bin/python scripts/demo_promotion.py
"""

from __future__ import annotations

import json
import sys

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.agents import SupportAgent
from aprntc.distill import ChildAgent, Distiller, Playbook
from aprntc.eval.judge import PairwiseJudge
from aprntc.eval.outcomes import support_outcome
from aprntc.memory.vikingdb import VikingDBMemoryStore
from aprntc.promote import EvalCase, LineageRegistry, PromotionGate
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, TrajectoryStore


def main() -> int:
    s = Settings.from_env()
    try:
        s.modelark.validate(); s.vikingdb.validate()
    except ValueError as e:
        print(f"[skip] {e}"); return 1

    store = TrajectoryStore(":memory:")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    client = ModelArkClient(s.modelark)
    memory = VikingDBMemoryStore(s.vikingdb, collection="ankur_aprntc_collection",
                                index="ankur_aprntc_index", dim=2048)
    model = s.modelark.policy_model

    try:
        print("== Parent runs + distill ==")
        parent = SupportAgent(client, tap, model=model)
        for t in ["What is your refund policy?", "How do I reset my password?",
                  "How long does shipping take?"]:
            res = parent.run(t, generation_id="G0")
            store.attach_label(res.episode_id, support_outcome(store.get_episode(res.episode_id)))
        distiller = Distiller(client, model=model)
        result = distiller.distill(store, generation=1)
        if result.lessons:
            memory.upsert_lessons(result.lessons)
        print(f"  distilled {len(result.lessons)} lessons")

        child_pb = result.diff.apply(Playbook(system_prompt=parent.system_prompt, generation=0))
        child = ChildAgent(parent, child_pb, memory=memory)

        print("\n== Promotion gate (parent vs child, recused judge) ==")
        judge = PairwiseJudge(client, judge_model=s.modelark.judge_model,
                             policy_model=s.modelark.policy_model)
        gate = PromotionGate(judge=judge)
        cases = [
            EvalCase(task="Can I return an item?"),
            EvalCase(task="What's your shipping time?"),
            EvalCase(task="I forgot my password, help."),
            EvalCase(task="How do I cancel my order?"),
        ]
        report = gate.evaluate(
            cases,
            parent=lambda t: parent.run(t).answer,
            child=lambda t: child.run(t).answer,
        )
        print("  " + report.summary())

        print("\n== Lineage decision ==")
        registry = LineageRegistry("lineage_demo.json")
        if registry.current is None:
            registry.register_parent(
                Playbook(system_prompt=parent.system_prompt).hash, note="G0 parent")
        if report.passed:
            g = registry.promote(child_pb.hash, gate_summary=report.summary(), note="demo")
            print(f"  PROMOTED to G{g.generation}")
        else:
            print(f"  REJECTED (acceptance bar not met) — parent stays at "
                  f"G{registry.current.generation}")

        # write a review bundle for the Streamlit UI
        bundle = {
            "diff": result.diff.to_dict(),
            "gate": {k: getattr(report, k) for k in (
                "n", "win_rate", "ci_low", "loss_rate", "regression_failures",
                "safety_failures", "win_rate_ok", "ci_ok", "loss_ok",
                "regression_ok", "safety_ok")},
            "candidate_playbook_hash": child_pb.hash,
            "lineage_path": "lineage_demo.json",
        }
        bundle["gate"]["passed"] = report.passed
        with open("review_bundle.json", "w") as f:
            json.dump(bundle, f, indent=2)
        print("\n  wrote review_bundle.json (open with: streamlit run src/aprntc/ui/review_app.py)")
        print("\nResult: OK — full MVP loop incl. promotion gate ran on live infra.")
        return 0
    finally:
        client.close(); store.close()


if __name__ == "__main__":
    sys.exit(main())
