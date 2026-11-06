"""Chunks, search configuration and hits."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ChunkType(StrEnum):
    SECTION = "section"  # packed prose from one section
    TABLE = "table"  # a whole small table, header included
    TABLE_ROWS = "table_rows"  # a slice of a large table, header repeated
    KV = "kv"  # consecutive label-value fields (portal pages)
    QA_PAIR = "qa_pair"  # one question and its answer (addenda)


class Span(BaseModel):
    """Part of one block's text that a chunk covers: block_index and [start, end)."""

    block_index: int
    start: int
    end: int


class Chunk(BaseModel):
    chunk_id: str
    bid_id: str
    doc_id: str
    file_name: str
    doc_type: str
    addendum_number: int | None = None
    doc_date: str | None = None
    title: str
    page_start: int
    page_end: int
    section_path: list[str] = Field(default_factory=list)
    chunk_type: ChunkType
    text: str
    embed_text: str  # text with a short document and section header, used for embedding
    spans: list[Span]
    identifiers: list[str] = Field(default_factory=list)  # ids and their compact forms
    fact_types: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    is_boilerplate: bool = False
    token_estimate: int

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SearchConfig(BaseModel):
    """One retrieval configuration; the eval table has one row per named config."""

    name: str = "hybrid_facts_rerank"
    dense: bool = True
    sparse: bool = True
    identifiers: bool = True  # exact identifier matches as an extra ranked list
    fact_types: bool = True  # route the query to fact-labelled chunks as extra lists
    expand: bool = True  # synonym expansion on the BM25 query
    rerank: bool = True
    candidates: int = 30  # per list, and the number of fused candidates sent to the reranker
    rrf_k: int = 60
    boilerplate_penalty: float = 0.5  # multiplier on the fused score of form-scaffold chunks


# The configuration used when none is named; chosen from the retrieval evaluation.
DEFAULT_CONFIG = "hybrid_facts"

NAMED_CONFIGS: dict[str, SearchConfig] = {
    "dense": SearchConfig(
        name="dense", sparse=False, identifiers=False, fact_types=False, expand=False, rerank=False
    ),
    "sparse": SearchConfig(
        name="sparse", dense=False, identifiers=False, fact_types=False, rerank=False
    ),
    "hybrid": SearchConfig(name="hybrid", identifiers=True, fact_types=False, rerank=False),
    "hybrid_facts": SearchConfig(name="hybrid_facts", rerank=False),
    "hybrid_facts_rerank": SearchConfig(name="hybrid_facts_rerank"),
}


class Hit(BaseModel):
    rank: int
    score: float
    chunk_id: str
    bid_id: str
    file_name: str
    page_start: int
    page_end: int
    doc_type: str
    addendum_number: int | None = None
    section_path: list[str]
    chunk_type: str
    text: str
    signals: dict[str, Any] = Field(default_factory=dict)

    @property
    def pages(self) -> str:
        if self.page_start == self.page_end:
            return str(self.page_start)
        return f"{self.page_start}-{self.page_end}"


class QueryAnalysis(BaseModel):
    query: str
    identifiers: list[str] = Field(default_factory=list)
    fact_types: list[str] = Field(default_factory=list)
    sparse_query: str  # the BM25 query after synonym expansion
    expansions: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: QueryAnalysis
    config: str
    hits: list[Hit]
    timings_ms: dict[str, float] = Field(default_factory=dict)
