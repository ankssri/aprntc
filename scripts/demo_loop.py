"""Live end-to-end loop demo — the whole apprentice cycle on real infra.

  parent runs -> episodes scored -> distiller mines lessons -> lessons to VikingDB
  -> child runs WITH playbook + memory retrieval.

Needs real ModelArk + VikingDB keys in .env. Consumes API quota.

Run:  .venv/bin/python scripts/demo_loop.py
"""

from __future__ import annotations

import sys
import time

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.agents import SupportAgent
from aprntc.distill import ChildAgent, Distiller, Playbook
from aprntc.eval.outcomes import support_outcome
from aprntc.memory.vikingdb import VikingDBMemoryStore
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
        print("== 1. Parent runs (generation 0) ==")
        parent = SupportAgent(client, tap, model=model)
        tasks = ["What is your refund policy?", "Where is order A1001?",
                 "How do I reset my password?"]
        for t in tasks:
            res = parent.run(t, generation_id="G0")
            # attach an outcome label so the distiller can bucket it
            ep = store.get_episode(res.episode_id)
            store.attach_label(res.episode_id, support_outcome(ep))
            print(f"  [{t[:35]}] -> {res.answer[:50]}")

        print("\n== 2. Distill lessons from scored episodes ==")
        distiller = Distiller(client, model=model)
        result = distiller.distill(store, generation=1)
        print(f"  mined {len(result.lessons)} lessons "
              f"({result.n_success} success, {result.n_failure} failure)")
        for l in result.lessons:
            print(f"   - ({l.lesson_type.value}) {l.content[:70]}")

        if result.lessons:
            print("\n== 3. Write lessons to VikingDB memory ==")
            n = memory.upsert_lessons(result.lessons)
            print(f"  upserted {n} lessons; waiting 15s to index...")
            time.sleep(15)

        print("\n== 4. Build child G1 (playbook diff applied) + run with memory ==")
        base_pb = Playbook(system_prompt=parent.system_prompt, generation=0)
        child_pb = result.diff.apply(base_pb)
        print(f"  playbook G{child_pb.generation}: +{len(result.diff.add_directives)} directives, "
              f"+{len(result.diff.add_watch_out)} watch-outs  [{child_pb.hash}]")
        child = ChildAgent(parent, child_pb, memory=memory)
        res = child.run("Can I get a refund?", generation_id="G1")
        ep = store.get_episode(res.episode_id)
        used_memory = any(s.tool_name == "memory_retrieve" for s in ep.turns[0].steps)
        print(f"  child answer: {res.answer[:70]}")
        print(f"  child retrieved from memory: {used_memory}")

        print("\nResult: OK — full loop ran end-to-end on live infra.")
        return 0
    finally:
        client.close(); store.close()


if __name__ == "__main__":
    sys.exit(main())
