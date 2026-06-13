"""Stage 5 tests — Lesson model, MMR, and the VikingDB adapter (offline, transport
injected so we test the REAL adapter's request construction + response handling)."""

import json

import pytest

from aprntc.config import VikingDBConfig
from aprntc.memory import (
    Lesson,
    LessonType,
    MemoryStore,
    VikingDBError,
    VikingDBMemoryStore,
    cosine,
    mmr_select,
)


# ─── Lesson model ───────────────────────────────────────────────────────────

def test_lesson_requires_content_and_valid_reward():
    with pytest.raises(ValueError):
        Lesson(content="  ", lesson_type=LessonType.DIRECTIVE, situation="s")
    with pytest.raises(ValueError):
        Lesson(content="c", lesson_type=LessonType.DIRECTIVE, situation="s", reward=1.5)


def test_lesson_fields_roundtrip():
    l = Lesson(content="prefer KB grounding", lesson_type="directive",
               situation="refund question", embedding=[0.1, 0.2], reward=0.8, generation=2)
    back = Lesson.from_fields(l.to_fields())
    assert back.content == l.content
    assert back.lesson_type is LessonType.DIRECTIVE
    assert back.reward == 0.8 and back.generation == 2
    assert back.embedding == [0.1, 0.2]


# ─── MMR ────────────────────────────────────────────────────────────────────

def test_cosine_basic():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([], [1]) == 0.0


def test_mmr_prefers_relevance_then_diversity():
    query = [1.0, 0.0]
    # two near-duplicates (high rel) + one diverse item
    cands = [
        (0, [1.0, 0.0], 0.99),   # most relevant
        (1, [0.99, 0.01], 0.98), # near-duplicate of 0
        (2, [0.0, 1.0], 0.50),   # diverse, lower rel
    ]
    chosen = mmr_select(query, cands, k=2, lambda_=0.6)
    assert chosen[0] == 0                 # most relevant first
    assert chosen[1] == 2                 # then the diverse one, not the duplicate


def test_mmr_empty_and_k_zero():
    assert mmr_select([1.0], [], k=3) == []
    assert mmr_select([1.0], [(0, [1.0], 1.0)], k=0) == []


# ─── VikingDB adapter (offline via injected transport) ──────────────────────

def _cfg() -> VikingDBConfig:
    return VikingDBConfig(ak="AK", sk="SK", region="ap-southeast-1",
                          data_host="data.example.com", control_host="control.example.com")


class RecordingTransport:
    """Captures the last signed request and returns a scripted (status, body)."""

    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body if body is not None else {"result": {"data": []}}
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append({"url": url, "headers": headers,
                           "body": json.loads(body.decode("utf-8"))})
        return self.status, self.body


def test_store_is_memorystore():
    assert isinstance(VikingDBMemoryStore(_cfg(), transport=RecordingTransport()), MemoryStore)


def test_create_collection_uses_control_action_and_is_signed():
    t = RecordingTransport(body={"Result": {"ResourceId": "rid"}})
    store = VikingDBMemoryStore(_cfg(), transport=t, dim=1024)
    store.create_collection()
    call = t.calls[0]
    assert "control.example.com" in call["url"]
    assert "Action=CreateVikingdbCollection" in call["url"]
    assert "Version=" in call["url"]
    assert call["headers"]["Authorization"].startswith("HMAC-SHA256 ")
    # vector field carries the configured dim
    vec = [f for f in call["body"]["Fields"] if f["FieldName"] == "embedding"][0]
    assert vec["Dim"] == 1024 and vec["FieldType"] == "vector"


def test_create_index_sets_scalar_index_and_hnsw():
    t = RecordingTransport(body={"Result": {"Message": "success"}})
    store = VikingDBMemoryStore(_cfg(), transport=t)
    store.create_index()
    body = t.calls[0]["body"]
    assert body["VectorIndex"]["IndexType"] == "hnsw"
    assert "reward" in body["ScalarIndex"] and "generation" in body["ScalarIndex"]


def test_upsert_uses_data_path_and_batches_over_100():
    t = RecordingTransport(body={"result": {}})
    store = VikingDBMemoryStore(_cfg(), transport=t)
    lessons = [Lesson(content=f"c{i}", lesson_type="directive", situation="s",
                      embedding=[0.1], reward=0.5) for i in range(150)]
    written = store.upsert_lessons(lessons)
    assert written == 150
    assert len(t.calls) == 2  # 100 + 50
    assert t.calls[0]["url"].endswith("/api/vikingdb/data/upsert")
    assert len(t.calls[0]["body"]["fields"]) == 100


def test_upsert_empty_is_noop():
    t = RecordingTransport()
    assert VikingDBMemoryStore(_cfg(), transport=t).upsert_lessons([]) == 0
    assert t.calls == []


def test_retrieve_builds_filter_and_dense_weight():
    # return 2 candidates so we can check parsing + filter shape
    body = {"result": {"data": [
        {"fields": {"lesson_id": "l1", "content": "c1", "situation": "s1",
                    "lesson_type": "directive", "reward": 0.9, "generation": 1,
                    "pii_status": "scrubbed", "embedding": [1.0, 0.0]}, "score": 0.95},
    ]}}
    t = RecordingTransport(body=body)
    store = VikingDBMemoryStore(_cfg(), transport=t, dense_weight=0.7)
    out = store.retrieve(query_embedding=[1.0, 0.0], k=4, min_reward=0.5,
                         generation=1, lesson_type="directive")
    req = t.calls[0]["body"]
    assert req["advance"]["dense_weight"] == 0.7
    assert req["dense_vector"] == [1.0, 0.0]
    # filter DSL: an AND of range(reward) + must(generation) + must(lesson_type) + must(pii)
    flt = req["filter"]
    assert flt["op"] == "and"
    ops = {(c["op"], c.get("field")) for c in flt["conds"]}
    assert ("range", "reward") in ops
    assert ("must", "generation") in ops
    assert ("must", "pii_status") in ops
    # parsed result
    assert len(out) == 1 and out[0].lesson.lesson_id == "l1" and out[0].score == 0.95


def test_retrieve_applies_mmr_diversification():
    # 3 candidates: two near-duplicates + one diverse; k=2 → expect diverse kept
    data = [
        {"fields": {"lesson_id": "a", "content": "a", "situation": "s",
                    "lesson_type": "exemplar", "reward": 0.9, "generation": 0,
                    "pii_status": "scrubbed", "embedding": [1.0, 0.0]}, "score": 0.99},
        {"fields": {"lesson_id": "b", "content": "b", "situation": "s",
                    "lesson_type": "exemplar", "reward": 0.9, "generation": 0,
                    "pii_status": "scrubbed", "embedding": [0.99, 0.01]}, "score": 0.98},
        {"fields": {"lesson_id": "c", "content": "c", "situation": "s",
                    "lesson_type": "exemplar", "reward": 0.9, "generation": 0,
                    "pii_status": "scrubbed", "embedding": [0.0, 1.0]}, "score": 0.85},
    ]
    t = RecordingTransport(body={"result": {"data": data}})
    store = VikingDBMemoryStore(_cfg(), transport=t)
    out = store.retrieve(query_embedding=[1.0, 0.0], k=2, diversify=True)
    ids = [r.lesson.lesson_id for r in out]
    # with default lambda=0.7: pick most-relevant 'a', then the diverse 'c'
    # beats the near-duplicate 'b' (which is penalized for similarity to 'a')
    assert ids[0] == "a" and "c" in ids and "b" not in ids


def test_retrieve_filter_always_excludes_unscrubbed():
    t = RecordingTransport(body={"result": {"data": []}})
    store = VikingDBMemoryStore(_cfg(), transport=t)
    store.retrieve(query_embedding=[1.0], k=2, min_reward=0.0)  # no other filters
    flt = t.calls[0]["body"]["filter"]
    # even with no user filters, pii_status=scrubbed is enforced
    blob = json.dumps(flt)
    assert "pii_status" in blob and "scrubbed" in blob


def test_non_200_raises_vikingdb_error():
    t = RecordingTransport(status=400, body={"Error": {"Message": "bad"}})
    store = VikingDBMemoryStore(_cfg(), transport=t)
    with pytest.raises(VikingDBError):
        store.upsert_lessons([Lesson(content="c", lesson_type="directive",
                                     situation="s", embedding=[0.1])])
