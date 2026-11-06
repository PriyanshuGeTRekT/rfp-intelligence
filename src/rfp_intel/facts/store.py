"""SQLite storage for facts.

One file (`var/rfp.sqlite`) will also hold the indexing manifest and addendum change events,
so a run has a single piece of state to ship, inspect or delete. Facts are replaced per
document, which is what incremental indexing needs: a changed file swaps its facts in one
transaction, an unchanged file is never touched.
"""

import json
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

from rfp_intel.facts.models import Fact, FactKind

SCHEMA_VERSION = 1
_COLUMNS = (
    "fact_id", "bid_id", "doc_id", "file_name", "doc_type", "addendum_number", "doc_date",
    "page", "block_index", "section", "kind", "fact_types", "raw", "start", "end", "value",
    "context",
)  # fmt: skip
_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id TEXT PRIMARY KEY,
    bid_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    addendum_number INTEGER,
    doc_date TEXT,
    page INTEGER NOT NULL,
    block_index INTEGER NOT NULL,
    section TEXT,
    kind TEXT NOT NULL,
    fact_types TEXT NOT NULL,   -- JSON list of labels
    raw TEXT NOT NULL,
    start INTEGER NOT NULL,
    "end" INTEGER NOT NULL,
    value TEXT NOT NULL,        -- JSON object, shape depends on kind
    context TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_facts_bid_kind ON facts (bid_id, kind);
CREATE INDEX IF NOT EXISTS ix_facts_doc ON facts (doc_id);
"""


class FactStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    def replace_document(self, doc_id: str, facts: Iterable[Fact]) -> int:
        rows = [
            (
                f.fact_id,
                f.bid_id,
                f.doc_id,
                f.file_name,
                f.doc_type,
                f.addendum_number,
                f.doc_date,
                f.page,
                f.block_index,
                f.section,
                f.kind.value,
                json.dumps(f.fact_types),
                f.raw,
                f.start,
                f.end,
                json.dumps(f.value),
                f.context,
            )
            for f in facts
        ]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        columns = ", ".join(f'"{c}"' for c in _COLUMNS)
        with self.conn:
            self.conn.execute("DELETE FROM facts WHERE doc_id = ?", (doc_id,))
            self.conn.executemany(
                f"INSERT INTO facts ({columns}) VALUES ({placeholders})",  # noqa: S608 - fixed column list
                rows,
            )
        return len(rows)

    def delete_document(self, doc_id: str) -> int:
        with self.conn:
            cur = self.conn.execute("DELETE FROM facts WHERE doc_id = ?", (doc_id,))
        return cur.rowcount

    def query(
        self,
        bid_id: str | None = None,
        *,
        kinds: Sequence[FactKind] | None = None,
        fact_types: Sequence[str] | None = None,
        doc_types: Sequence[str] | None = None,
        doc_id: str | None = None,
    ) -> list[Fact]:
        # Only fixed SQL fragments and "?" placeholders are concatenated; every value is a
        # bound parameter.
        where: list[str] = []
        params: list[object] = []
        if bid_id is not None:
            where.append("bid_id = ?")
            params.append(bid_id)
        if doc_id is not None:
            where.append("doc_id = ?")
            params.append(doc_id)
        if kinds:
            where.append(f"kind IN ({', '.join('?' for _ in kinds)})")
            params.extend(k.value for k in kinds)
        if doc_types:
            where.append(f"doc_type IN ({', '.join('?' for _ in doc_types)})")
            params.extend(doc_types)
        if fact_types:
            where.append(
                "EXISTS (SELECT 1 FROM json_each(facts.fact_types) "  # noqa: S608
                f"WHERE json_each.value IN ({', '.join('?' for _ in fact_types)}))"
            )
            params.extend(fact_types)
        sql = "SELECT * FROM facts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY file_name, page, block_index, start"
        return [self._row_to_fact(r) for r in self.conn.execute(sql, params)]

    def count_by_type(self, bid_id: str) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT json_each.value AS t, COUNT(*) AS n FROM facts, json_each(facts.fact_types) "
            "WHERE bid_id = ? GROUP BY t ORDER BY t",
            (bid_id,),
        )
        return {r["t"]: r["n"] for r in rows}

    @staticmethod
    def _row_to_fact(row: sqlite3.Row) -> Fact:
        data = dict(row)
        data["fact_types"] = json.loads(data["fact_types"])
        data["value"] = json.loads(data["value"])
        return Fact.model_validate(data)
