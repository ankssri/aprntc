"""VikingDB MemoryStore — REST adapter (ADR 0001, 0003).

Two planes (Stage-0 live finding):
* **Control plane** (collection/index lifecycle) — host ``vikingdb...byteplusapi.com``,
  **``Action=`` query param** (e.g. ``CreateVikingdbCollection``), ``Version`` param,
  UpperCamelCase body.
* **Data plane** (upsert/search) — host ``api-vikingdb...bytepluses.com``, fixed
  paths (``/api/vikingdb/data/upsert``, ``/api/vikingdb/data/search/vector``),
  snake_case body.

Both planes are signed with our Volcengine SigV4 signer (service ``air``).

The HTTP transport is **injectable** (``transport=``) so request construction +
response handling are unit-tested offline against the real adapter; live calls use
httpx. Filtered hybrid retrieval uses ``dense_weight`` + a ``filter`` DSL; MMR
diversification is applied client-side over the returned candidates.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from aprntc.byteplus.signing import Credentials, sign
from aprntc.config import VikingDBConfig
from aprntc.memory.base import Lesson, MemoryStore, RetrievedLesson
from aprntc.memory.mmr import mmr_select

CONTROL_VERSION = "2025-06-09"

# A transport takes a signed request and returns (status_code, json_body).
Transport = Callable[[str, dict[str, str], bytes], tuple[int, dict[str, Any]]]


class VikingDBError(RuntimeError):
    pass


def _httpx_transport(url: str, headers: dict[str, str], body: bytes) -> tuple[int, dict[str, Any]]:
    import httpx

    resp = httpx.post(url, headers=headers, content=body, timeout=30.0)
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return resp.status_code, data


class VikingDBMemoryStore(MemoryStore):
    def __init__(
        self,
        config: VikingDBConfig,
        *,
        collection: str = "aprntc_lessons",
        index: str = "aprntc_lessons_idx",
        dim: int = 1024,
        dense_weight: float = 0.5,
        transport: Transport | None = None,
    ) -> None:
        config.validate()
        self._cfg = config
        self._collection = collection
        self._index = index
        self._dim = dim
        self._dense_weight = dense_weight
        self._transport = transport or _httpx_transport
        self._creds = Credentials(ak=config.ak, sk=config.sk,
                                  service=config.service, region=config.region)

    # -- low-level signed calls -----------------------------------------

    def _call_data(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        signed = sign(method="POST", host=self._cfg.data_host, path=path,
                      creds=self._creds, body=raw,
                      headers={"Content-Type": "application/json"})
        return self._invoke(signed.url, signed.headers, raw)

    def _call_control(self, action: str, body: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        query = {"Action": action, "Version": CONTROL_VERSION}
        signed = sign(method="POST", host=self._cfg.control_host, path="/",
                      creds=self._creds, body=raw, query=query,
                      headers={"Content-Type": "application/json"})
        return self._invoke(signed.url, signed.headers, raw)

    def _invoke(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        status, data = self._transport(url, headers, body)
        if status != 200:
            raise VikingDBError(f"VikingDB HTTP {status}: {json.dumps(data)[:300]}")
        return data

    # -- control plane: lifecycle ---------------------------------------

    def create_collection(self) -> dict[str, Any]:
        body = {
            "CollectionName": self._collection,
            "Description": "aprntc distilled lessons (Experience Memory)",
            "Fields": [
                {"FieldName": "lesson_id", "FieldType": "string", "IsPrimaryKey": True},
                {"FieldName": "content", "FieldType": "string"},
                {"FieldName": "situation", "FieldType": "string"},
                {"FieldName": "lesson_type", "FieldType": "string"},
                {"FieldName": "reward", "FieldType": "float32"},
                {"FieldName": "generation", "FieldType": "int64"},
                {"FieldName": "pii_status", "FieldType": "string"},
                {"FieldName": "embedding", "FieldType": "vector", "Dim": self._dim},
            ],
        }
        return self._call_control("CreateVikingdbCollection", body)

    def create_index(self) -> dict[str, Any]:
        body = {
            "CollectionName": self._collection,
            "IndexName": self._index,
            "VectorIndex": {"IndexType": "hnsw", "Distance": "cosine", "Quant": "float"},
            # scalar fields we filter on must be indexed
            "ScalarIndex": ["reward", "generation", "lesson_type", "pii_status"],
        }
        return self._call_control("CreateVikingdbIndex", body)

    # -- data plane: write ----------------------------------------------

    def upsert_lessons(self, lessons: list[Lesson]) -> int:
        if not lessons:
            return 0
        written = 0
        # VikingDB upsert cap is 100 rows per request.
        for i in range(0, len(lessons), 100):
            chunk = lessons[i : i + 100]
            self._call_data(
                "/api/vikingdb/data/upsert",
                {"collection_name": self._collection,
                 "fields": [l.to_fields() for l in chunk]},
            )
            written += len(chunk)
        return written

    # -- data plane: read -----------------------------------------------

    @staticmethod
    def _build_filter(min_reward: float, generation: int | None,
                      lesson_type: str | None) -> dict[str, Any] | None:
        conds: list[dict[str, Any]] = []
        if min_reward > 0.0:
            conds.append({"op": "range", "field": "reward", "gte": min_reward})
        if generation is not None:
            conds.append({"op": "must", "field": "generation", "conds": [generation]})
        if lesson_type is not None:
            conds.append({"op": "must", "field": "lesson_type", "conds": [lesson_type]})
        # always exclude unscrubbed rows (privacy invariant)
        conds.append({"op": "must", "field": "pii_status", "conds": ["scrubbed"]})
        if not conds:
            return None
        if len(conds) == 1:
            return conds[0]
        return {"op": "and", "conds": conds}

    def retrieve(
        self,
        *,
        query_embedding: list[float],
        k: int = 4,
        min_reward: float = 0.0,
        generation: int | None = None,
        lesson_type: str | None = None,
        diversify: bool = True,
    ) -> list[RetrievedLesson]:
        # Over-fetch so MMR has candidates to diversify over.
        fetch = max(k * 4, k) if diversify else k
        body: dict[str, Any] = {
            "collection_name": self._collection,
            "index_name": self._index,
            "dense_vector": list(query_embedding),
            "limit": fetch,
            "output_fields": ["lesson_id", "content", "situation", "lesson_type",
                              "reward", "generation", "pii_status", "embedding"],
            "advance": {"dense_weight": self._dense_weight},
        }
        flt = self._build_filter(min_reward, generation, lesson_type)
        if flt is not None:
            body["filter"] = flt

        data = self._call_data("/api/vikingdb/data/search/vector", body)
        items = _extract_items(data)
        candidates: list[RetrievedLesson] = []
        for it in items:
            fields = it.get("fields", it)
            score = float(it.get("score", 0.0))
            candidates.append(RetrievedLesson(lesson=Lesson.from_fields(fields), score=score))

        if not diversify or len(candidates) <= k:
            return candidates[:k]

        mmr_input = [
            (idx, c.lesson.embedding or query_embedding, c.score)
            for idx, c in enumerate(candidates)
        ]
        chosen = mmr_select(query_embedding, mmr_input, k=k)
        return [candidates[i] for i in chosen]


def _extract_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull the result list out of VikingDB's response envelope (tolerant of shape)."""
    if "data" in data and isinstance(data["data"], list):
        return data["data"]
    result = data.get("result") or data.get("Result") or {}
    if isinstance(result, dict):
        for key in ("data", "items", "Data"):
            if isinstance(result.get(key), list):
                return result[key]
    return []
