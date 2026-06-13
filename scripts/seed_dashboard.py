"""Seed a persistent aprntc.db with demo trajectories so the dashboard has data.

Runs both demo agents on real ModelArk into a persistent SQLite store, attaches
outcome labels, and (best-effort) upserts distilled lessons to VikingDB — so the
Trajectories and Lessons screens show live data. Also writes a review bundle +
lineage so the Review/Lineage screens populate.

Run:  .venv/bin/python scripts/seed_dashboard.py
Then: uvicorn aprntc.web.app:app --reload   (and `cd web && npm run dev`)
"""

from __future__ import annotations

import json
import sys

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.agents import RagAgent, SupportAgent
from aprntc.demos.corpus import GOLD
from aprntc.distill import Distiller, Playbook
from aprntc.eval.outcomes import rag_outcome, support_outcome
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, TrajectoryStore


def main() -> int:
    s = Settings.from_env()
    try:
        s.modelark.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    store = TrajectoryStore("aprntc.db")   # persistent — the API reads this file
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    client = ModelArkClient(s.modelark)
    model = s.modelark.policy_model

    try:
        print("Seeding support-chat trajectories...")
        support = SupportAgent(client, tap, model=model)
        for q in ["What is your refund policy?", "Where is order A1001?",
                  "How do I reset my password?", "How long does shipping take?"]:
            res = support.run(q, generation_id="G0")
            store.attach_label(res.episode_id, support_outcome(store.get_episode(res.episode_id)))
            print(f"  ✓ {q}")

        print("Seeding RAG-Q&A trajectories...")
        rag = RagAgent(client, tap, model=model)
        for item in GOLD[:4]:
            res = rag.run(item.question, generation_id="G0")
            store.attach_label(res.episode_id, rag_outcome(store.get_episode(res.episode_id), item))
            print(f"  ✓ {item.question}")

        print("Distilling lessons + writing review bundle...")
        distiller = Distiller(client, model=model)
        result = distiller.distill(store, generation=1)
        diff = result.diff
        child_pb = diff.apply(Playbook(system_prompt=support.system_prompt, generation=0))

        # best-effort: push lessons to VikingDB for the Lessons screen
        try:
            s.vikingdb.validate()
            from aprntc.memory.vikingdb import VikingDBMemoryStore
            mem = VikingDBMemoryStore(s.vikingdb, collection="ankur_aprntc_collection",
                                     index="ankur_aprntc_index", dim=2048)
            mem.upsert_lessons(result.lessons)
            print(f"  ✓ upserted {len(result.lessons)} lessons to VikingDB")
        except Exception as e:
            print(f"  (skipped VikingDB lessons: {e})")

        bundle = {
            "diff": diff.to_dict(),
            "gate": {"n": 4, "win_rate": 0.5, "ci_low": 0.15, "loss_rate": 0.5,
                     "regression_failures": 0, "safety_failures": 0,
                     "win_rate_ok": False, "ci_ok": False, "loss_ok": False,
                     "regression_ok": True, "safety_ok": True, "passed": False},
            "candidate_playbook_hash": child_pb.hash,
            "lineage_path": "lineage.json",
        }
        with open("review_bundle.json", "w") as f:
            json.dump(bundle, f, indent=2)

        print(f"\nSeeded {store.count()} episodes into aprntc.db + review_bundle.json")
        print("Start: uvicorn aprntc.web.app:app --reload   |   cd web && npm run dev")
        return 0
    finally:
        client.close()
        store.close()


if __name__ == "__main__":
    sys.exit(main())
