"""Semantic cache for questions: a question that means the same as one answered before, over the
same documents, gets the earlier answer without a model call.

Two questions match when their embeddings (the search engine's dense model) have cosine
similarity at or above `RFP_QA_CACHE_THRESHOLD` and they name the same numbers and identifiers
("Bid1" vs "Bid2", "Addendum 1" vs "Addendum 2" read as near-identical sentences to an embedding
model, so these tokens must agree exactly). An entry is only reused under the same fingerprint:
the indexed files of the bids in scope, their extraction records, the answering model and this
module's version. Re-indexing a changed file or re-running an extraction makes old answers miss.
"""

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from rfp_intel.agents.qa import QAResult
from rfp_intel.search.manifest import Manifest

CACHE_VERSION = 2  # bump when the Q&A prompt or answer checks change

_SCHEMA = """
CREATE TABLE IF NOT EXISTS qa_cache (
    id INTEGER PRIMARY KEY,
    scope TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    question TEXT NOT NULL,
    anchors TEXT NOT NULL,
    vector TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS qa_cache_scope ON qa_cache (scope, fingerprint);
"""

_ANCHOR_RE = re.compile(r"\b\w*\d\w*\b")


def anchors(question: str) -> str:
    """The tokens holding a digit (bid ids, addendum numbers, years, SKUs), sorted."""
    return " ".join(sorted(set(_ANCHOR_RE.findall(question.casefold()))))


def fingerprint(db_path: Path, out_dir: Path, bid_ids: Sequence[str], model: str) -> str:
    """What an answer depends on: indexed file hashes, extraction runs, model, cache version."""
    parts = [f"v{CACHE_VERSION}", model]
    with Manifest(db_path) as manifest:
        bids = sorted(bid_ids) or manifest.bids()
        for bid in bids:
            entries = manifest.entries(bid)
            parts += [
                f"{bid}/{k}:{e.file_sha256}:{e.pipeline_version}"
                for k, e in sorted(entries.items())
            ]
            record = out_dir / f"{bid}.json"
            if record.exists():
                parts.append(
                    f"{bid}:record:{json.loads(record.read_text(encoding='utf-8')).get('run_id')}"
                )
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


@dataclass
class Hit:
    result: QAResult
    question: str
    similarity: float


class SemanticCache:
    def __init__(self, path: Path, embed: Callable[[str], list[float]], threshold: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.embed = embed
        self.threshold = threshold

    def lookup(self, question: str, scope: str, fp: str) -> Hit | None:
        rows = self.conn.execute(
            "SELECT question, vector, result FROM qa_cache "
            "WHERE scope = ? AND fingerprint = ? AND anchors = ?",
            (scope, fp, anchors(question)),
        ).fetchall()
        if not rows:
            return None
        q = _unit(self.embed(question))
        best: Hit | None = None
        for text, vector, result in rows:
            sim = float(np.dot(q, _unit(json.loads(vector))))
            if sim >= self.threshold and (best is None or sim > best.similarity):
                best = Hit(QAResult.model_validate_json(result), text, round(sim, 4))
        return best

    def store(self, question: str, scope: str, fp: str, result: QAResult) -> None:
        vector = [round(x, 6) for x in self.embed(question)]
        with self.conn:
            self.conn.execute(
                "INSERT INTO qa_cache (scope, fingerprint, question, anchors, vector, result, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (scope, fp, question, anchors(question), json.dumps(vector),
                 result.model_dump_json(), datetime.now(UTC).isoformat(timespec="seconds")),
            )  # fmt: skip

    def close(self) -> None:
        self.conn.close()


def _unit(v: Sequence[float]) -> np.ndarray:
    a = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(a))
    return a / n if n else a
