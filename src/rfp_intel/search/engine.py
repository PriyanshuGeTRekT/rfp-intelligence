"""Hybrid search.

For one query the engine builds several ranked lists, fuses them with RRF and optionally
reranks the fused candidates with a cross-encoder:

1. dense: the question's embedding against chunk embeddings;
2. bm25: the question plus procurement synonyms against BM25 term weights;
3. identifiers: chunks whose `identifiers` contain an id from the question, exactly;
4. facts: dense and BM25 again, restricted to chunks holding facts with the labels the
   question routes to (deadline, bond_insurance, ...), so "when is it due" reaches the
   handful of chunks that contain a due date even when boilerplate outnumbers them.

Metadata filters (bid, document type, addendum number) apply to every list. Form scaffolding
is down-weighted, not removed. Each hit reports its rank in every list, so a result can be
explained.
"""

import time
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any

from opentelemetry import trace

from rfp_intel.facts.labels import FactTypeConfig
from rfp_intel.search.backend import Filters, SearchBackend
from rfp_intel.search.embed import DenseEmbedder, Reranker, SparseEmbedder
from rfp_intel.search.fusion import RankedList, rrf
from rfp_intel.search.models import (
    DEFAULT_CONFIG,
    NAMED_CONFIGS,
    Hit,
    QueryAnalysis,
    SearchConfig,
    SearchResult,
)
from rfp_intel.search.query import Synonyms, analyze

tracer = trace.get_tracer(__name__)

IDENTIFIER_WEIGHT = 2.0  # an exact id match is strong evidence; it outweighs one fuzzy list
RERANK_BOILERPLATE_MARGIN = 2.0  # cross-encoder logits; subtract this for form scaffolding
RERANK_DEMOTED_TYPE_MARGIN = 2.0  # and this for document types a caller asks to demote


class SearchEngine:
    def __init__(
        self,
        backend: SearchBackend,
        dense: DenseEmbedder,
        sparse: SparseEmbedder,
        fact_config: FactTypeConfig,
        *,
        reranker: Reranker | None = None,
        synonyms: Synonyms | None = None,
    ) -> None:
        self.backend = backend
        self.dense = dense
        self.sparse = sparse
        self.reranker = reranker
        self.fact_config = fact_config
        self.synonyms = synonyms

    def search(
        self,
        query: str,
        *,
        bid_id: str | None = None,
        doc_types: Sequence[str] | None = None,
        addendum_number: int | None = None,
        doc_id: str | None = None,
        k: int = 5,
        config: SearchConfig | str = DEFAULT_CONFIG,
    ) -> SearchResult:
        cfg = NAMED_CONFIGS[config] if isinstance(config, str) else config
        with tracer.start_as_current_span("search") as span:
            timings: dict[str, float] = {}
            t0 = time.perf_counter()
            analysis = analyze(query, self.fact_config, self.synonyms, expand=cfg.expand)
            base = Filters(
                bid_id=bid_id,
                doc_types=list(doc_types or []),
                addendum_number=addendum_number,
                doc_id=doc_id,
            )
            n = cfg.candidates
            lists: list[RankedList] = []

            dense_vec = self.dense.embed_query(query) if cfg.dense else None
            sparse_vec = self.sparse.embed_query(analysis.sparse_query) if cfg.sparse else None
            timings["embed_query"] = _ms(t0)

            t1 = time.perf_counter()
            if dense_vec is not None:
                lists.append(
                    RankedList(
                        "dense", [c for c, _ in self.backend.dense_search(dense_vec, base, n)]
                    )
                )
            if sparse_vec is not None:
                lists.append(
                    RankedList(
                        "bm25", [c for c, _ in self.backend.sparse_search(sparse_vec, base, n)]
                    )
                )
            if cfg.identifiers and analysis.identifiers:
                ids = self.backend.match_identifiers(analysis.identifiers, base, n)
                lists.append(RankedList("identifiers", ids, IDENTIFIER_WEIGHT))
            if cfg.fact_types and analysis.fact_types:
                typed = Filters({**base, "fact_types": analysis.fact_types})
                if dense_vec is not None:
                    typed_dense = self.backend.dense_search(dense_vec, typed, n)
                    lists.append(RankedList("facts_dense", [c for c, _ in typed_dense]))
                if sparse_vec is not None:
                    typed_sparse = self.backend.sparse_search(sparse_vec, typed, n)
                    lists.append(RankedList("facts_bm25", [c for c, _ in typed_sparse]))
            timings["retrieve"] = _ms(t1)

            fused = rrf(lists, k=cfg.rrf_k)[:n]
            payloads = self.backend.fetch([f.chunk_id for f in fused])
            candidates: list[_Candidate] = []
            for f in fused:
                payload = payloads.get(f.chunk_id)
                if payload is None:
                    continue
                boiler = bool(payload.get("is_boilerplate"))
                candidates.append(
                    _Candidate(
                        payload=payload,
                        score=f.score * (cfg.boilerplate_penalty if boiler else 1.0),
                        signals={"ranks": f.ranks, "rrf": round(f.score, 5), "boilerplate": boiler},
                    )
                )
            candidates.sort(key=lambda c: c.score, reverse=True)

            if cfg.rerank and self.reranker is not None and candidates:
                t2 = time.perf_counter()
                texts = [str(c.payload["embed_text"]) for c in candidates]
                for c, rs in zip(candidates, self.reranker.score(query, texts), strict=True):
                    c.signals["rerank"] = round(rs, 4)
                    c.score = rs - (RERANK_BOILERPLATE_MARGIN if c.signals["boilerplate"] else 0.0)
                candidates.sort(key=lambda c: c.score, reverse=True)
                timings["rerank"] = _ms(t2)

            hits = [c.to_hit(rank) for rank, c in enumerate(candidates[:k], start=1)]
            timings["total"] = _ms(t0)

            span.set_attribute("search.query", query)
            span.set_attribute("search.config", cfg.name)
            span.set_attribute("search.filters", str({k_: v for k_, v in base.items() if v}))
            span.set_attribute("search.identifiers", analysis.identifiers)
            span.set_attribute("search.fact_types", analysis.fact_types)
            span.set_attribute("search.lists", [f"{rl.name}:{len(rl.chunk_ids)}" for rl in lists])
            span.set_attribute("search.top_chunk_ids", [h.chunk_id for h in hits])
            span.set_attribute("search.top_scores", [round(h.score, 4) for h in hits])
            span.set_attribute("search.latency_ms", timings["total"])
            return SearchResult(query=analysis, config=cfg.name, hits=hits, timings_ms=timings)

    def analyze(self, query: str) -> QueryAnalysis:
        """What the engine reads into a query: identifiers, fact labels it routes to, synonyms."""
        return analyze(query, self.fact_config, self.synonyms, expand=True)

    def rerank(
        self,
        query: str | Sequence[str],
        chunk_ids: Sequence[str],
        demote_doc_types: Collection[str] = (),
    ) -> list[tuple[str, float]]:
        """Order already-retrieved chunks by the cross-encoder, for callers that pool
        candidates from several searches. Without a reranker the order is kept. Given several
        queries, a chunk scores its best match among them (one cross-encoder pass per query).
        Chunks of a type in `demote_doc_types` lose a fixed margin: they stay in the ranking
        and still lead when nothing else comes close."""
        payloads = self.backend.fetch(chunk_ids)
        present = [c for c in chunk_ids if c in payloads]
        if self.reranker is None or not present:
            return [(c, 0.0) for c in present]
        with tracer.start_as_current_span("rerank") as span:
            texts = [str(payloads[c].get("embed_text") or payloads[c]["text"]) for c in present]
            queries = [query] if isinstance(query, str) else list(query)
            per_query = [self.reranker.score(q, texts) for q in queries]
            scores = [max(column) for column in zip(*per_query, strict=True)]
            for i, c in enumerate(present):
                if payloads[c].get("is_boilerplate"):
                    scores[i] -= RERANK_BOILERPLATE_MARGIN
                if payloads[c].get("doc_type") in demote_doc_types:
                    scores[i] -= RERANK_DEMOTED_TYPE_MARGIN
            ranked = sorted(zip(present, scores, strict=True), key=lambda x: x[1], reverse=True)
            span.set_attribute("search.query", queries)
            span.set_attribute("search.reranked", len(ranked))
            return ranked


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


@dataclass
class _Candidate:
    payload: dict[str, Any]
    score: float
    signals: dict[str, Any] = field(default_factory=dict)

    def to_hit(self, rank: int) -> Hit:
        p = self.payload
        return Hit(
            rank=rank,
            score=round(self.score, 5),
            chunk_id=p["chunk_id"],
            bid_id=p["bid_id"],
            file_name=p["file_name"],
            page_start=p["page_start"],
            page_end=p["page_end"],
            doc_type=p["doc_type"],
            addendum_number=p.get("addendum_number"),
            section_path=p.get("section_path", []),
            chunk_type=p["chunk_type"],
            text=p["text"],
            signals=self.signals,
        )
