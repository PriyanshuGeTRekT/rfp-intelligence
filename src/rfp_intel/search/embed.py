"""Embedding and reranking models behind small interfaces.

The real models run locally on CPU through fastembed (ONNX), so indexing and search need no
API key. Tests use the hashing fakes at the bottom of this module: deterministic, instant and
no download, which keeps CI fast and offline.
"""

import hashlib
import math
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

# Hugging Face Hub warns on Windows that it cannot create symlinks in the model cache.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


@dataclass(frozen=True)
class SparseVector:
    indices: list[int]
    values: list[float]


class DenseEmbedder(Protocol):
    name: str

    @property
    def dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SparseEmbedder(Protocol):
    name: str

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]: ...

    def embed_query(self, text: str) -> SparseVector: ...


class Reranker(Protocol):
    name: str

    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


# ---------------------------------------------------------------------------------------------
# fastembed implementations


class FastEmbedDense:
    def __init__(self, model_name: str, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding

        self.name = model_name
        self._model: Any = TextEmbedding(
            model_name, cache_dir=str(cache_dir) if cache_dir else None
        )
        self._dim: int | None = None

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed_query("dimension probe"))
        return self._dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.query_embed(text)))]


class FastEmbedSparse:
    """BM25 term weights; the collection applies IDF at query time (Qdrant's IDF modifier)."""

    def __init__(self, model_name: str = "Qdrant/bm25", cache_dir: Path | None = None) -> None:
        from fastembed import SparseTextEmbedding

        self.name = model_name
        self._model: Any = SparseTextEmbedding(
            model_name, cache_dir=str(cache_dir) if cache_dir else None
        )

    @staticmethod
    def _convert(v: Any) -> SparseVector:
        return SparseVector(indices=v.indices.tolist(), values=v.values.tolist())

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        return [self._convert(v) for v in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> SparseVector:
        return self._convert(next(iter(self._model.query_embed(text))))


class FastEmbedReranker:
    def __init__(self, model_name: str, cache_dir: Path | None = None) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = model_name
        self._model: Any = TextCrossEncoder(
            model_name, cache_dir=str(cache_dir) if cache_dir else None
        )

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, list(documents))]


# ---------------------------------------------------------------------------------------------
# Deterministic fakes for tests

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bucket(token: str, size: int) -> int:
    return int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16) % size


class HashingDense:
    """Bag-of-words hashed into a small vector: texts sharing words are close."""

    name = "hashing-dense"

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._dim
        for tok in _tokens(text):
            v[_bucket(tok, self._dim)] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class HashingSparse:
    """Term frequencies on hashed token ids; with the IDF modifier this behaves like BM25."""

    name = "hashing-sparse"

    def _vec(self, text: str) -> SparseVector:
        counts = Counter(_bucket(t, 2**31 - 1) for t in _tokens(text))
        indices = sorted(counts)
        return SparseVector(indices=indices, values=[float(counts[i]) for i in indices])

    def embed_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> SparseVector:
        q = self._vec(text)
        return SparseVector(indices=q.indices, values=[1.0] * len(q.indices))


class OverlapReranker:
    """Scores by the share of query words present in the document."""

    name = "overlap-reranker"

    def score(self, query: str, documents: Sequence[str]) -> list[float]:
        q = set(_tokens(query))
        return [len(q & set(_tokens(d))) / (len(q) or 1) for d in documents]
