"""FastAPI app exposing the aprntc engine to the web dashboard.

Read endpoints serve dashboard data (gate report, lineage, trajectories, lessons);
write endpoints perform the human decisions (promote / rollback). State is held in
an injectable :class:`AppState` so tests drive it with in-memory fakes and the real
server wires the live store / lineage / review bundle.

Design notes:
* No business logic here — endpoints delegate to the engine (`promote`, `trajectory`,
  `memory`). The API is a thin transport, consistent with "the gate computes the bar,
  the UI only displays it and records the human decision".
* CORS is open in dev so the Vite dev server (localhost:5173) can call it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from aprntc.promote.lineage import LineageRegistry
from aprntc.trajectory.store import TrajectoryStore


@dataclass
class AppState:
    """Injectable backing state for the API (real or fake)."""

    lineage_path: str = "lineage.json"
    bundle_path: str = "review_bundle.json"
    store: TrajectoryStore | None = None
    # optional: a memory retriever (callable(query, k) -> list[dict]) for the lessons screen
    memory_search: Any | None = None
    # optional: a runner (agent_id, task) -> dict, for the "Try an agent" screen
    agent_run: Any | None = None

    def lineage(self) -> LineageRegistry:
        return LineageRegistry(self.lineage_path)

    def bundle(self) -> dict[str, Any]:
        p = Path(self.bundle_path)
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    @classmethod
    def from_env(
        cls,
        *,
        db_path: str = "aprntc.db",
        lineage_path: str = "lineage.json",
        bundle_path: str = "review_bundle.json",
        load_dotenv: bool = True,
    ) -> "AppState":
        """Wire real persistent backends (SQLite store + VikingDB memory) from config.

        Degrades gracefully: a missing DB file still gives an (empty) store; if VikingDB
        config/creds are absent or httpx isn't installed, ``memory_search`` stays ``None``
        and the lessons screen shows its "not connected" state.
        """
        store = TrajectoryStore(db_path)
        memory_search = _build_memory_search(load_dotenv=load_dotenv)
        agent_run = _build_agent_run(store, load_dotenv=load_dotenv)
        return cls(
            lineage_path=lineage_path,
            bundle_path=bundle_path,
            store=store,
            memory_search=memory_search,
            agent_run=agent_run,
        )


def _build_memory_search(*, load_dotenv: bool = True) -> Any | None:
    """Return a ``(query, k) -> list[dict]`` retriever backed by VikingDB, or None."""
    try:
        from aprntc.config import Settings
        from aprntc.memory.vikingdb import VikingDBMemoryStore

        settings = Settings.from_env(dotenv=".env" if load_dotenv else None)
        settings.vikingdb.validate()  # raises if creds missing
        mem = VikingDBMemoryStore(
            settings.vikingdb,
            collection="ankur_aprntc_collection",
            index="ankur_aprntc_index",
            dim=2048,
        )
    except Exception:
        return None

    def search(query: str, k: int) -> list[dict[str, Any]]:
        results = mem.retrieve(query=query or "lesson", k=k, min_reward=0.0)
        return [
            {
                "lesson_id": r.lesson.lesson_id,
                "content": r.lesson.content,
                "lesson_type": r.lesson.lesson_type.value,
                "reward": r.lesson.reward,
                "score": r.score,
            }
            for r in results
        ]

    return search


def _build_agent_run(store: TrajectoryStore, *, load_dotenv: bool = True) -> Any | None:
    """Return an ``(agent_id, task) -> dict`` runner backed by live ModelArk, or None.

    Runs the chosen demo agent on the task, captures the trajectory into the shared
    store (so it appears on the Trajectories screen), scores it with the matching
    outcome scorer, and returns the answer + the captured steps + the reward.
    """
    try:
        from aprntc.byteplus.modelark import ModelArkClient
        from aprntc.config import Settings

        settings = Settings.from_env(dotenv=".env" if load_dotenv else None)
        settings.modelark.validate()  # raises if keys missing
        client = ModelArkClient(settings.modelark)
        model = settings.modelark.policy_model
    except Exception:
        return None

    def run(agent_id: str, task: str) -> dict[str, Any]:
        from aprntc.demos.agents import RagAgent, SupportAgent
        from aprntc.demos.corpus import GOLD
        from aprntc.eval.outcomes import rag_outcome, support_outcome
        from aprntc.tap import AgentTap
        from aprntc.trajectory import Collector

        tap = AgentTap(store.put_episode, collector=Collector.SDK_WRAPPER)
        if agent_id == "support":
            agent = SupportAgent(client, tap, model=model)
            res = agent.run(task, generation_id="try")
            ep = store.get_episode(res.episode_id)
            label = support_outcome(ep)
        else:
            agent = RagAgent(client, tap, model=model)
            res = agent.run(task, generation_id="try")
            ep = store.get_episode(res.episode_id)
            # score against a gold item if the task matches one, else groundedness-only
            gold = next((g for g in GOLD if g.question.lower() == task.lower()), None)
            label = rag_outcome(ep, gold) if gold else support_outcome(ep)
        store.attach_label(res.episode_id, label)

        steps = [
            {
                "type": s.type.value,
                "tool_name": s.tool_name,
                "tool_args": s.tool_args,
                "duration_ms": round(s.duration_ms, 1) if s.duration_ms else None,
            }
            for turn in ep.turns
            for s in turn.steps
        ]
        return {
            "answer": res.answer,
            "episode_id": res.episode_id,
            "agent_id": agent_id,
            "reward": label.score,
            "reward_rationale": label.rationale,
            "reasoning": next((t.reasoning_content for t in ep.turns if t.reasoning_content), None),
            "steps": steps,
        }

    return run


def create_app(state: AppState | None = None) -> FastAPI:
    state = state or AppState()
    app = FastAPI(title="aprntc dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- health ----------------------------------------------------------
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "aprntc"}

    # -- review / gate ---------------------------------------------------
    @app.get("/api/review")
    def get_review() -> dict[str, Any]:
        """The current candidate review bundle: gate report + attributable diff."""
        bundle = state.bundle()
        gate = bundle.get("gate", {})
        passed = gate.get("passed")
        if passed is None:
            passed = all(gate.get(k, False) for k in
                         ("win_rate_ok", "ci_ok", "loss_ok", "regression_ok", "safety_ok"))
        return {
            "available": bool(bundle),
            "candidate_playbook_hash": bundle.get("candidate_playbook_hash"),
            "gate": gate,
            "passed": passed,
            "diff": bundle.get("diff", {}),
        }

    # -- lineage ---------------------------------------------------------
    @app.get("/api/lineage")
    def get_lineage() -> dict[str, Any]:
        reg = state.lineage()
        cur = reg.current
        return {
            "current": cur.to_dict() if cur else None,
            "generations": [g.to_dict() for g in reg.history()],
        }

    @app.post("/api/lineage/promote")
    def promote(body: dict[str, Any]) -> dict[str, Any]:
        playbook_hash = body.get("playbook_hash")
        if not playbook_hash:
            raise HTTPException(status_code=400, detail="playbook_hash required")
        reg = state.lineage()
        if reg.current is None:
            reg.register_parent(playbook_hash, note="seeded at first promote")
            return {"action": "registered_parent", "current": reg.current.to_dict()}
        gen = reg.promote(playbook_hash, gate_summary=body.get("gate_summary", ""),
                          note=body.get("note", "human-approved"))
        return {"action": "promoted", "current": gen.to_dict()}

    @app.post("/api/lineage/rollback")
    def rollback() -> dict[str, Any]:
        reg = state.lineage()
        try:
            gen = reg.rollback()
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e))
        return {"action": "rolled_back", "current": gen.to_dict()}

    # -- trajectories ----------------------------------------------------
    @app.get("/api/trajectories")
    def list_trajectories(limit: int = 50, generation: str | None = None) -> dict[str, Any]:
        if state.store is None:
            return {"episodes": [], "count": 0}
        eps = state.store.query(generation_id=generation, limit=limit)
        return {
            "count": state.store.count(),
            "episodes": [_episode_summary(e, state.store) for e in eps],
        }

    @app.get("/api/trajectories/{episode_id}")
    def get_trajectory(episode_id: str) -> dict[str, Any]:
        if state.store is None:
            raise HTTPException(status_code=404, detail="no store configured")
        try:
            ep = state.store.get_episode(episode_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"no episode {episode_id}")
        data = ep.to_dict()
        data["labels"] = [l.to_dict() for l in state.store.labels_for(episode_id)]
        fused = state.store.fused_reward(episode_id)
        data["fused_reward"] = {"reward": fused[0], "confidence": fused[1]} if fused else None
        return data

    # -- lessons (experience memory) ------------------------------------
    @app.get("/api/lessons")
    def search_lessons(q: str = "", k: int = 10) -> dict[str, Any]:
        if state.memory_search is None:
            return {"lessons": [], "query": q, "available": False}
        try:
            results = state.memory_search(q, k)
        except Exception as e:  # memory is best-effort; surface the error, don't 500
            return {"lessons": [], "query": q, "available": True, "error": str(e)}
        return {"lessons": results, "query": q, "available": True}

    # -- try an agent ---------------------------------------------------
    @app.get("/api/agents")
    def list_agents() -> dict[str, Any]:
        """Available demo agents + a few example prompts for the UI."""
        return {
            "available": state.agent_run is not None,
            "agents": [
                {
                    "id": "support",
                    "name": "Support chat",
                    "description": "Customer-support agent. Tools: KB lookup, order status.",
                    "examples": [
                        "What is your refund policy?",
                        "Where is order A1001?",
                        "How do I cancel my order?",
                    ],
                },
                {
                    "id": "rag",
                    "name": "RAG-Q&A",
                    "description": "Answers from a small doc corpus (Sun, Earth, Mars, Jupiter) with citations.",
                    "examples": [
                        "How old is the Sun?",
                        "Which planet is the Red Planet?",
                        "What is the largest planet?",
                    ],
                },
            ],
        }

    @app.post("/api/agents/run")
    def run_agent(body: dict[str, Any]) -> dict[str, Any]:
        agent_id = body.get("agent_id")
        task = (body.get("task") or "").strip()
        if agent_id not in ("support", "rag"):
            raise HTTPException(status_code=400, detail="agent_id must be 'support' or 'rag'")
        if not task:
            raise HTTPException(status_code=400, detail="task is required")
        if state.agent_run is None:
            raise HTTPException(status_code=503, detail="agent runtime not configured (needs ModelArk keys)")
        try:
            return state.agent_run(agent_id, task)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"agent run failed: {e}")

    return app


def _episode_summary(ep: Any, store: TrajectoryStore) -> dict[str, Any]:
    fused = store.fused_reward(ep.episode_id)
    return {
        "episode_id": ep.episode_id,
        "task_input": ep.task_input,
        "final_output": ep.final_output,
        "collector": ep.collector.value,
        "generation_id": ep.generation_id,
        "ts_start": ep.ts_start,
        "partial": ep.partial,
        "n_turns": len(ep.turns),
        "n_steps": sum(len(t.steps) for t in ep.turns),
        "reward": fused[0] if fused else None,
    }


# Module-level app for `uvicorn aprntc.web.app:app` — wires the real persistent
# SQLite store + VikingDB memory from env/cwd (degrades gracefully if absent).
app = create_app(AppState.from_env())
