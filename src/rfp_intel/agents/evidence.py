"""Evidence gathering per field.

For each field, evidence is the union of:
- hybrid search for the field name and its configured queries, scoped to the bid;
- every chunk that contains a fact with the field's labels (deadline, delivery, ...), so a
  typed candidate can never be missed because search ranked it low.

Evidence text lives in an `EvidenceStore` keyed by chunk id; graph state carries only ids, so
checkpoints and traces stay small. The record of what was searched is kept per field: it is
the proof behind "not found".
"""

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from rfp_intel.agents.fields import FieldSpec
from rfp_intel.facts.models import Fact
from rfp_intel.facts.store import FactStore
from rfp_intel.search.backend import Filters
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.models import DEFAULT_CONFIG, SearchConfig

PER_QUERY = 5
MAX_ITEMS = 10
MIN_QUERIES_FOR_ABSENCE = 3


class EvidenceItem(BaseModel):
    evidence_id: str  # the chunk id
    bid_id: str = ""
    file: str
    page_start: int
    page_end: int
    doc_type: str
    addendum_number: int | None = None
    section: str = ""
    text: str

    @property
    def pages(self) -> str:
        if self.page_start == self.page_end:
            return str(self.page_start)
        return f"{self.page_start}-{self.page_end}"

    def header(self, *, with_bid: bool = False) -> str:
        add = f", addendum {self.addendum_number}" if self.addendum_number is not None else ""
        bid = f"bid {self.bid_id}, " if with_bid and self.bid_id else ""
        return f"[{self.evidence_id}] {bid}{self.file} p{self.pages} ({self.doc_type}{add})"


class FactCandidate(BaseModel):
    fact_id: str
    kind: str
    raw: str
    value: dict[str, Any]
    file: str
    page: int
    doc_type: str
    addendum_number: int | None = None
    context: str


class FieldEvidence(BaseModel):
    field: str
    evidence_ids: list[str] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list)
    candidates: list[FactCandidate] = Field(default_factory=list)
    typed_fact_count: int = 0

    def coverage_met(self, spec: FieldSpec) -> bool:
        """Searched enough, and no fact carries the field's labels."""
        return len(self.queries) >= MIN_QUERIES_FOR_ABSENCE and (
            not spec.fact_types or self.typed_fact_count == 0
        )

    def coverage_note(self) -> str:
        return (
            f"Searched {len(self.queries)} queries ({'; '.join(self.queries)}); "
            f"{self.typed_fact_count} labelled facts; {len(self.evidence_ids)} passages reviewed."
        )


Loader = Callable[[Sequence[str]], dict[str, dict[str, Any]]]


class EvidenceStore:
    """Evidence text by chunk id. With a loader (the backend's fetch), ids that were gathered
    in an earlier process, such as a resumed run, are fetched on first use."""

    def __init__(self, loader: Loader | None = None) -> None:
        self._items: dict[str, EvidenceItem] = {}
        self._loader = loader

    def add(self, item: EvidenceItem) -> None:
        self._items.setdefault(item.evidence_id, item)

    def _load(self, ids: Sequence[str]) -> None:
        missing = [i for i in ids if i not in self._items]
        if missing and self._loader is not None:
            for payload in self._loader(missing).values():
                self.add(_item(payload))

    def get(self, evidence_id: str) -> EvidenceItem | None:
        self._load([evidence_id])
        return self._items.get(evidence_id)

    def many(self, ids: Sequence[str]) -> list[EvidenceItem]:
        self._load(ids)
        return [self._items[i] for i in ids if i in self._items]

    def __len__(self) -> int:
        return len(self._items)


def _item(payload: dict[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=payload["chunk_id"],
        bid_id=payload.get("bid_id", ""),
        file=payload["file_name"],
        page_start=payload["page_start"],
        page_end=payload["page_end"],
        doc_type=payload["doc_type"],
        addendum_number=payload.get("addendum_number"),
        section=" > ".join(payload.get("section_path", [])),
        text=payload["text"],
    )


def _candidate(f: Fact) -> FactCandidate:
    return FactCandidate(
        fact_id=f.fact_id, kind=f.kind.value, raw=f.raw, value=f.value, file=f.file_name,
        page=f.page, doc_type=f.doc_type, addendum_number=f.addendum_number, context=f.context,
    )  # fmt: skip


def gather(
    engine: SearchEngine,
    facts: FactStore,
    store: EvidenceStore,
    bid_id: str,
    spec: FieldSpec,
    *,
    extra_queries: Sequence[str] = (),
    config: SearchConfig | str = DEFAULT_CONFIG,
) -> FieldEvidence:
    queries = list(dict.fromkeys([spec.name, *spec.queries, *extra_queries]))
    ranked: dict[
        str, tuple[int, int]
    ] = {}  # chunk id -> (best rank, number of queries that found it)
    for q in queries:
        for hit in engine.search(q, bid_id=bid_id, k=PER_QUERY, config=config).hits:
            best, count = ranked.get(hit.chunk_id, (hit.rank, 0))
            ranked[hit.chunk_id] = (min(best, hit.rank), count + 1)

    typed: list[Fact] = []
    if spec.fact_types:
        typed = facts.query(bid_id, fact_types=spec.fact_types, kinds=spec.fact_kinds or None)
    by_kind: list[Fact] = []
    if spec.fact_kinds and not spec.fact_types:
        by_kind = facts.query(bid_id, kinds=spec.fact_kinds)

    fact_chunks = engine.backend.chunks_with_facts(
        [f.fact_id for f in typed], Filters(bid_id=bid_id), limit=MAX_ITEMS
    )
    ordered = sorted(ranked, key=lambda c: (ranked[c][0], -ranked[c][1]))
    ids = list(dict.fromkeys([*fact_chunks, *ordered]))[:MAX_ITEMS]
    for payload in engine.backend.fetch(ids).values():
        store.add(_item(payload))
    return FieldEvidence(
        field=spec.key,
        evidence_ids=[i for i in ids if store.get(i) is not None],
        queries=queries,
        candidates=[_candidate(f) for f in (typed or by_kind)[:25]],
        typed_fact_count=len(typed),
    )
