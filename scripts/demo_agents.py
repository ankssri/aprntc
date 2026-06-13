"""Live demo: run both demo agents on real ModelArk, tapped into a SQLite store.

Needs real keys in .env (Stage-0 verified). Consumes a little API quota.

Run:  .venv/bin/python scripts/demo_agents.py
"""

from __future__ import annotations

import sys

from aprntc.byteplus.modelark import ModelArkClient
from aprntc.config import Settings
from aprntc.demos.agents import RagAgent, SupportAgent
from aprntc.demos.corpus import GOLD
from aprntc.tap import AgentTap
from aprntc.trajectory import Collector, TrajectoryStore


def main() -> int:
    settings = Settings.from_env()
    try:
        settings.modelark.validate()
    except ValueError as e:
        print(f"[skip] {e}")
        return 1

    store = TrajectoryStore("aprntc.db")
    tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
    client = ModelArkClient(settings.modelark)
    model = settings.modelark.policy_model

    try:
        print("== Support-chat demo ==")
        support = SupportAgent(client, tap, model=model)
        for q in ("What is your refund policy?", "Where is order A1001?"):
            res = support.run(q, generation_id="G0")
            print(f"  Q: {q}\n  A: {res.answer}\n  episode: {res.episode_id}")

        print("\n== RAG-Q&A demo (gold questions) ==")
        rag = RagAgent(client, tap, model=model)
        for item in GOLD[:3]:
            res = rag.run(item.question, generation_id="G0")
            cited = "yes" if any(d in res.answer for d in item.cited_docs) else "no"
            print(f"  Q: {item.question}\n  A: {res.answer}\n  retrieved={rag.last_retrieved} "
                  f"cited_expected_doc={cited}\n  episode: {res.episode_id}")

        print(f"\nStored {store.count()} episodes in aprntc.db")
    finally:
        client.close()
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
