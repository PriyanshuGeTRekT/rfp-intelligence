"""The indexing manifest: which version of which file is in the index.

It lives in the same SQLite file as the facts. A file is re-indexed only when its content
hash or the pipeline version changes, so adding a bid folder never re-processes the others,
and editing one PDF touches only that PDF's chunks and facts.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import BaseModel

# Bump when parsing, fact extraction or chunking changes what an indexed file would contain.
PIPELINE_VERSION = 3  # 2: OCR reads vector-outline pages; 3: tables on OCR pages

_SCHEMA = """
CREATE TABLE IF NOT EXISTS manifest (
    bid_id TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    chunks INTEGER NOT NULL,
    facts INTEGER NOT NULL,
    pipeline_version INTEGER NOT NULL,
    embed_model TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    PRIMARY KEY (bid_id, rel_path)
);
"""


class ManifestEntry(BaseModel):
    bid_id: str
    rel_path: str
    file_sha256: str
    doc_id: str
    doc_type: str
    chunks: int
    facts: int
    pipeline_version: int
    embed_model: str
    indexed_at: str

    def is_current(self, sha: str, embed_model: str) -> bool:
        return (
            self.file_sha256 == sha
            and self.pipeline_version == PIPELINE_VERSION
            and self.embed_model == embed_model
        )


class Manifest:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.conn.close()

    def entries(self, bid_id: str) -> dict[str, ManifestEntry]:
        rows = self.conn.execute("SELECT * FROM manifest WHERE bid_id = ?", (bid_id,))
        return {r["rel_path"]: ManifestEntry.model_validate(dict(r)) for r in rows}

    def bids(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT bid_id FROM manifest ORDER BY 1")]

    def put(self, entry: ManifestEntry) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.bid_id, entry.rel_path, entry.file_sha256, entry.doc_id, entry.doc_type,
                    entry.chunks, entry.facts, entry.pipeline_version, entry.embed_model,
                    entry.indexed_at,
                ),
            )  # fmt: skip

    def remove(self, bid_id: str, rel_path: str) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM manifest WHERE bid_id = ? AND rel_path = ?", (bid_id, rel_path)
            )


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
