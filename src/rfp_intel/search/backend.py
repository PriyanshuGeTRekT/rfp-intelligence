"""Vector store backends.

`SearchBackend` is the seam: the engine and indexer only call these methods. `QdrantBackend`
is the default, running embedded (a local folder, no server) for development and CI, or
against a Qdrant server by URL. One collection holds, per chunk:

- a named dense vector `dense` (cosine);
- a named sparse vector `bm25` with Qdrant's IDF modifier, so BM25 term weights from the
  embedder are combined with corpus IDF at query time;
- the chunk as payload, including keyword lists `identifiers` and `fact_types` that filters
  match exactly.

Keeping dense, sparse and metadata on the same point means adding, changing or deleting a
document is one operation on one store, never two stores to keep in step.

The embedded client (a local folder or memory) is not safe to call from several threads at
once, and the agents search from parallel graph branches, so in those modes every client call
is serialized. A Qdrant server handles concurrency itself and is called directly.
"""

import functools
import threading
import uuid
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from qdrant_client import QdrantClient, models

from rfp_intel.search.embed import SparseVector
from rfp_intel.search.models import Chunk

DENSE = "dense"
SPARSE = "bm25"
KEYWORD_FIELDS = (
    "bid_id", "doc_id", "doc_type", "chunk_type", "identifiers", "fact_types", "fact_ids",
)  # fmt: skip


class Filters(dict[str, Any]):
    """bid_id, doc_types, addendum_number, fact_types, identifiers; absent keys mean any."""


class SearchBackend(Protocol):
    def upsert(
        self, chunks: Sequence[Chunk], dense: Sequence[list[float]], sparse: Sequence[SparseVector]
    ) -> None: ...

    def delete_document(self, doc_id: str) -> None: ...

    def dense_search(
        self, vector: list[float], filters: Filters, limit: int
    ) -> list[tuple[str, float]]: ...

    def sparse_search(
        self, vector: SparseVector, filters: Filters, limit: int
    ) -> list[tuple[str, float]]: ...

    def match_identifiers(self, ids: Sequence[str], filters: Filters, limit: int) -> list[str]: ...

    def chunks_with_facts(
        self, fact_ids: Sequence[str], filters: Filters, limit: int
    ) -> list[str]: ...

    def fetch(self, chunk_ids: Sequence[str]) -> dict[str, dict[str, Any]]: ...

    def count(self, filters: Filters | None = None) -> int: ...

    def close(self) -> None: ...


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rfp-chunk:{chunk_id}"))


def _filter(filters: Filters) -> models.Filter | None:
    must: list[models.Condition] = []
    if filters.get("bid_id"):
        must.append(
            models.FieldCondition(key="bid_id", match=models.MatchValue(value=filters["bid_id"]))
        )
    if filters.get("doc_id"):
        must.append(
            models.FieldCondition(key="doc_id", match=models.MatchValue(value=filters["doc_id"]))
        )
    if filters.get("doc_types"):
        must.append(
            models.FieldCondition(
                key="doc_type", match=models.MatchAny(any=list(filters["doc_types"]))
            )
        )
    if filters.get("addendum_number") is not None:
        must.append(
            models.FieldCondition(
                key="addendum_number", match=models.MatchValue(value=filters["addendum_number"])
            )
        )
    if filters.get("fact_types"):
        must.append(
            models.FieldCondition(
                key="fact_types", match=models.MatchAny(any=list(filters["fact_types"]))
            )
        )
    if filters.get("identifiers"):
        must.append(
            models.FieldCondition(
                key="identifiers", match=models.MatchAny(any=list(filters["identifiers"]))
            )
        )
    if filters.get("fact_ids"):
        must.append(
            models.FieldCondition(
                key="fact_ids", match=models.MatchAny(any=list(filters["fact_ids"]))
            )
        )
    return models.Filter(must=must) if must else None


class _Serialized:
    """Proxy that runs one call at a time on the wrapped client."""

    def __init__(self, client: QdrantClient) -> None:
        self._client = client
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr
        return self._locked(attr)

    def _locked(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def call(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return fn(*args, **kwargs)

        return call


class QdrantBackend:
    def __init__(
        self,
        dense_dim: int,
        *,
        path: Path | None = None,
        url: str | None = None,
        location: str | None = None,
        collection: str = "chunks",
    ) -> None:
        if url:
            self.client = QdrantClient(url=url)
        elif location:
            self.client = cast(QdrantClient, _Serialized(QdrantClient(location=location)))
        elif path is not None:
            path.mkdir(parents=True, exist_ok=True)
            self.client = cast(QdrantClient, _Serialized(QdrantClient(path=str(path))))
        else:
            raise ValueError("give a path, a url or a location such as ':memory:'")
        self.collection = collection
        try:
            self._ensure_collection(dense_dim)
        except Exception:
            self.client.close()  # release the embedded store's folder lock before failing
            raise

    def _ensure_collection(self, dense_dim: int) -> None:
        if self.client.collection_exists(self.collection):
            info = self.client.get_collection(self.collection)
            vectors = info.config.params.vectors
            size = vectors[DENSE].size if isinstance(vectors, dict) else None
            if size != dense_dim:
                raise ValueError(
                    f"collection '{self.collection}' has dense size {size}, "
                    f"the model gives {dense_dim}; "
                    "the embedding model changed, so delete the index and re-index"
                )
            return
        self.client.create_collection(
            self.collection,
            vectors_config={
                DENSE: models.VectorParams(size=dense_dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        with warnings.catch_warnings():  # embedded mode ignores payload indexes and says so
            warnings.simplefilter("ignore")
            for name in KEYWORD_FIELDS:
                self.client.create_payload_index(
                    self.collection, name, models.PayloadSchemaType.KEYWORD
                )
            self.client.create_payload_index(
                self.collection, "addendum_number", models.PayloadSchemaType.INTEGER
            )

    def upsert(
        self, chunks: Sequence[Chunk], dense: Sequence[list[float]], sparse: Sequence[SparseVector]
    ) -> None:
        points = [
            models.PointStruct(
                id=point_id(c.chunk_id),
                vector={
                    DENSE: d,
                    SPARSE: models.SparseVector(indices=s.indices, values=s.values),
                },
                payload=c.payload(),
            )
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        if points:
            self.client.upsert(self.collection, points=points, wait=True)

    def delete_document(self, doc_id: str) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=_filter(Filters(doc_id=doc_id))),
            wait=True,
        )

    def dense_search(
        self, vector: list[float], filters: Filters, limit: int
    ) -> list[tuple[str, float]]:
        res = self.client.query_points(
            self.collection, query=vector, using=DENSE, query_filter=_filter(filters), limit=limit,
            with_payload=["chunk_id"],
        )  # fmt: skip
        return [(str((p.payload or {})["chunk_id"]), float(p.score)) for p in res.points]

    def sparse_search(
        self, vector: SparseVector, filters: Filters, limit: int
    ) -> list[tuple[str, float]]:
        if not vector.indices:
            return []
        res = self.client.query_points(
            self.collection,
            query=models.SparseVector(indices=vector.indices, values=vector.values),
            using=SPARSE, query_filter=_filter(filters), limit=limit, with_payload=["chunk_id"],
        )  # fmt: skip
        return [(str((p.payload or {})["chunk_id"]), float(p.score)) for p in res.points]

    def match_identifiers(self, ids: Sequence[str], filters: Filters, limit: int) -> list[str]:
        flt = Filters({**filters, "identifiers": list(ids)})
        points, _ = self.client.scroll(
            self.collection, scroll_filter=_filter(flt), limit=limit,
            with_payload=["chunk_id", "identifiers", "token_estimate"],
        )  # fmt: skip
        wanted = set(ids)

        def specificity(p: models.Record) -> tuple[int, int]:
            payload = p.payload or {}
            matched = len(wanted & set(payload.get("identifiers", [])))
            return (-matched, int(payload.get("token_estimate", 0)))  # more matches, then shorter

        return [str((p.payload or {})["chunk_id"]) for p in sorted(points, key=specificity)]

    def chunks_with_facts(self, fact_ids: Sequence[str], filters: Filters, limit: int) -> list[str]:
        if not fact_ids:
            return []
        points, _ = self.client.scroll(
            self.collection,
            scroll_filter=_filter(Filters({**filters, "fact_ids": list(fact_ids)})),
            limit=limit,
            with_payload=["chunk_id"],
        )
        return [str((p.payload or {})["chunk_id"]) for p in points]

    def fetch(self, chunk_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        points = self.client.retrieve(
            self.collection, ids=[point_id(c) for c in chunk_ids], with_payload=True
        )
        return {str((p.payload or {})["chunk_id"]): dict(p.payload or {}) for p in points}

    def count(self, filters: Filters | None = None) -> int:
        return self.client.count(
            self.collection, count_filter=_filter(filters or Filters()), exact=True
        ).count

    def close(self) -> None:
        self.client.close()
