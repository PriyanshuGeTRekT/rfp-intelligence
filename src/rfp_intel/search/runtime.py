"""Build the search stack from settings: models, vector store, engine and indexer.

Everything is injectable, so tests pass hashing fakes and an in-memory Qdrant while the CLI
and API get the real models and the on-disk index.
"""

from dataclasses import dataclass
from types import TracebackType
from typing import Self

from rfp_intel.config import Settings
from rfp_intel.facts.labels import FactTypeConfig, load_fact_types
from rfp_intel.ingestion.meta import CueConfig, load_cues
from rfp_intel.search.backend import QdrantBackend, SearchBackend
from rfp_intel.search.embed import (
    DenseEmbedder,
    FastEmbedDense,
    FastEmbedReranker,
    FastEmbedSparse,
    Reranker,
    SparseEmbedder,
)
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.indexer import Indexer
from rfp_intel.search.query import Synonyms, load_synonyms


@dataclass
class Runtime:
    settings: Settings
    backend: SearchBackend
    dense: DenseEmbedder
    sparse: SparseEmbedder
    reranker: Reranker | None
    cues: CueConfig
    fact_config: FactTypeConfig
    synonyms: Synonyms

    def engine(self) -> SearchEngine:
        return SearchEngine(
            self.backend,
            self.dense,
            self.sparse,
            self.fact_config,
            reranker=self.reranker,
            synonyms=self.synonyms,
        )

    def indexer(self) -> Indexer:
        return Indexer(
            self.backend,
            self.dense,
            self.sparse,
            self.settings.db_path,
            self.cues,
            self.fact_config,
            docs_dir=self.settings.docs_dir,
        )

    def close(self) -> None:
        self.backend.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_runtime(
    settings: Settings,
    *,
    dense: DenseEmbedder | None = None,
    sparse: SparseEmbedder | None = None,
    reranker: Reranker | None = None,
    load_reranker: bool = True,
    qdrant_location: str | None = None,
) -> Runtime:
    cache = settings.models_dir
    dense = dense or FastEmbedDense(settings.embed_model, cache_dir=cache)
    sparse = sparse or FastEmbedSparse(settings.sparse_model, cache_dir=cache)
    if reranker is None and load_reranker:
        reranker = FastEmbedReranker(settings.rerank_model, cache_dir=cache)
    backend = QdrantBackend(
        dense.dim,
        path=None if settings.qdrant_url or qdrant_location else settings.qdrant_path,
        url=settings.qdrant_url,
        location=qdrant_location,
        collection=settings.qdrant_collection,
    )
    return Runtime(
        settings=settings,
        backend=backend,
        dense=dense,
        sparse=sparse,
        reranker=reranker,
        cues=load_cues(settings.config_dir / "doc_types.yaml"),
        fact_config=load_fact_types(settings.config_dir / "fact_types.yaml"),
        synonyms=load_synonyms(settings.config_dir / "synonyms.yaml"),
    )
