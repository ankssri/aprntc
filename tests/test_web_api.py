"""Web dashboard API tests — endpoints over gate/lineage/trajectories/lessons."""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from aprntc.web.app import AppState, create_app
from aprntc.trajectory import (
    Collector,
    Episode,
    Label,
    LabelSource,
    TrajectoryStore,
    Turn,
)


@pytest.fixture()
def store():
    s = TrajectoryStore(":memory:")
    yield s
    s.close()


def _client(tmp_path, store=None, memory_search=None, bundle=None):
    if bundle is not None:
        (tmp_path / "bundle.json").write_text(json.dumps(bundle))
    state = AppState(
        lineage_path=str(tmp_path / "lineage.json"),
        bundle_path=str(tmp_path / "bundle.json"),
        store=store,
        memory_search=memory_search,
    )
    return TestClient(create_app(state))


# ─── health ─────────────────────────────────────────────────────────────────

def test_health(tmp_path):
    r = _client(tmp_path).get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


# ─── review / gate ──────────────────────────────────────────────────────────

def test_review_unavailable_without_bundle(tmp_path):
    r = _client(tmp_path).get("/api/review")
    assert r.status_code == 200 and r.json()["available"] is False


def test_review_returns_gate_and_diff(tmp_path):
    bundle = {
        "candidate_playbook_hash": "pb_abc",
        "gate": {"win_rate": 0.25, "ci_low": 0.05, "loss_rate": 0.75,
                 "win_rate_ok": False, "ci_ok": False, "loss_ok": False,
                 "regression_ok": True, "safety_ok": True, "passed": False},
        "diff": {"add_directives": ["cite docs"], "provenance": {"cite docs": ["les_1"]}},
    }
    r = _client(tmp_path, bundle=bundle).get("/api/review")
    body = r.json()
    assert body["available"] and body["passed"] is False
    assert body["candidate_playbook_hash"] == "pb_abc"
    assert body["diff"]["add_directives"] == ["cite docs"]


def test_review_computes_passed_when_missing(tmp_path):
    bundle = {"gate": {"win_rate_ok": True, "ci_ok": True, "loss_ok": True,
                       "regression_ok": True, "safety_ok": True}}
    r = _client(tmp_path, bundle=bundle).get("/api/review")
    assert r.json()["passed"] is True


# ─── lineage ────────────────────────────────────────────────────────────────

def test_lineage_promote_and_rollback_flow(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/lineage").json()["current"] is None

    # first promote registers the parent
    r1 = c.post("/api/lineage/promote", json={"playbook_hash": "pb_g0"})
    assert r1.json()["action"] == "registered_parent"

    r2 = c.post("/api/lineage/promote", json={"playbook_hash": "pb_g1",
                                              "gate_summary": "win 60%"})
    assert r2.json()["action"] == "promoted"
    assert r2.json()["current"]["generation"] == 1

    cur = c.get("/api/lineage").json()
    assert cur["current"]["generation"] == 1 and len(cur["generations"]) == 2

    r3 = c.post("/api/lineage/rollback")
    assert r3.json()["current"]["generation"] == 0


def test_promote_requires_hash(tmp_path):
    r = _client(tmp_path).post("/api/lineage/promote", json={})
    assert r.status_code == 400


def test_rollback_at_g0_conflicts(tmp_path):
    c = _client(tmp_path)
    c.post("/api/lineage/promote", json={"playbook_hash": "pb_g0"})
    r = c.post("/api/lineage/rollback")
    assert r.status_code == 409  # nothing to roll back to


# ─── trajectories ───────────────────────────────────────────────────────────

def test_list_and_get_trajectory(tmp_path, store):
    ep = Episode(task_input="refund?", collector=Collector.SDK_WRAPPER,
                 final_output="30 days", generation_id="G0", turns=[Turn(turn_index=0)])
    eid = store.put_episode(ep, scrub=False)
    store.attach_label(eid, Label(source=LabelSource.OUTCOME, score=0.9, confidence=0.9))
    c = _client(tmp_path, store=store)

    lst = c.get("/api/trajectories").json()
    assert lst["count"] == 1
    summary = lst["episodes"][0]
    assert summary["episode_id"] == eid and summary["reward"] is not None

    detail = c.get(f"/api/trajectories/{eid}").json()
    assert detail["task_input"] == "refund?"
    assert detail["fused_reward"]["reward"] == pytest.approx(0.9)
    assert len(detail["labels"]) == 1


def test_get_missing_trajectory_404(tmp_path, store):
    r = _client(tmp_path, store=store).get("/api/trajectories/ep_nope")
    assert r.status_code == 404


def test_trajectories_empty_without_store(tmp_path):
    r = _client(tmp_path).get("/api/trajectories")
    assert r.json() == {"episodes": [], "count": 0}


# ─── lessons ────────────────────────────────────────────────────────────────

def test_lessons_search(tmp_path):
    def fake_search(q, k):
        return [{"lesson_id": "les_1", "content": "cite docs", "reward": 0.9, "score": 0.95}]
    c = _client(tmp_path, memory_search=fake_search)
    body = c.get("/api/lessons", params={"q": "citation", "k": 5}).json()
    assert body["available"] and len(body["lessons"]) == 1
    assert body["lessons"][0]["lesson_id"] == "les_1"


def test_lessons_unavailable_without_memory(tmp_path):
    body = _client(tmp_path).get("/api/lessons", params={"q": "x"}).json()
    assert body["available"] is False


def test_lessons_memory_error_is_surfaced_not_500(tmp_path):
    def boom(q, k):
        raise RuntimeError("vikingdb down")
    c = _client(tmp_path, memory_search=boom)
    body = c.get("/api/lessons", params={"q": "x"}).json()
    assert body["available"] is True and "vikingdb down" in body["error"]


# ─── from_env factory (persistent backends, graceful degradation) ───────────

def test_from_env_wires_persistent_store(tmp_path, monkeypatch):
    from aprntc.web.app import AppState
    # no VikingDB creds in env, and skip .env loading → memory_search stays None,
    # but a real persistent store is still created.
    for var in ("VIKINGDB_AK", "VIKINGDB_SK"):
        monkeypatch.delenv(var, raising=False)
    state = AppState.from_env(
        db_path=str(tmp_path / "aprntc.db"),
        lineage_path=str(tmp_path / "lineage.json"),
        bundle_path=str(tmp_path / "bundle.json"),
        load_dotenv=False,
    )
    assert state.store is not None              # real persistent store wired
    assert state.memory_search is None          # degraded cleanly (no creds)
    # the wired app answers over the store
    c = TestClient(create_app(state))
    assert c.get("/api/trajectories").json()["count"] == 0
    assert c.get("/api/lessons", params={"q": "x"}).json()["available"] is False
