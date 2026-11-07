"""Change events from addenda, by one structured LLM call per addendum.

Date changes come from facts with no model (see reconcile.events_from_facts). Everything else
(a new form to submit, a clarified requirement, an amended term) needs reading. The addendum
is not pasted whole into the prompt: the search engine is queried within that one document for
change language and for each field an addendum can change, and the passages found are what the
model reads. Every event's quote is then checked to be verbatim addendum text, and the result
is cached by document id, so a re-run costs nothing.
"""

import json
from datetime import date
from pathlib import Path

from rfp_intel.agents.evidence import EvidenceItem, EvidenceStore
from rfp_intel.agents.fields import FieldCatalog, FieldSpec
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.llm import Usage
from rfp_intel.agents.outputs import EventsOut
from rfp_intel.agents.prompts import EVENTS_SYSTEM, events_user
from rfp_intel.agents.reconcile import ChangeEvent
from rfp_intel.agents.validate import ground
from rfp_intel.search.engine import SearchEngine

# Language addenda use for changes, searched besides the names of the fields they can change.
CHANGE_QUERIES = (
    "this addendum changes revises replaces",
    "is hereby amended extended deleted added",
    "questions and answers clarification",
    "acknowledge receipt of this addendum",
)
PER_QUERY = 4
MAX_PASSAGES = 16


def changeable_fields(catalog: FieldCatalog) -> list[FieldSpec]:
    """Fields whose change events come from the model (dates come from facts)."""
    return [f for f in catalog.fields if f.reconcile and f.type != "datetime"]


def addendum_items(
    engine: SearchEngine,
    store: EvidenceStore,
    catalog: FieldCatalog,
    *,
    bid_id: str,
    doc_id: str,
) -> list[EvidenceItem]:
    """Passages of one addendum that state changes, found by search, in page order."""
    queries = [*CHANGE_QUERIES, *(f.name for f in changeable_fields(catalog))]
    found: dict[str, int] = {}
    for q in queries:
        for hit in engine.search(q, bid_id=bid_id, doc_id=doc_id, k=PER_QUERY).hits:
            found[hit.chunk_id] = min(found.get(hit.chunk_id, hit.rank), hit.rank)
    best = sorted(found, key=lambda c: found[c])[:MAX_PASSAGES]
    items = store.many(best)
    return sorted(items, key=lambda i: (i.page_start, i.evidence_id))


def extract_events(
    llm: GuardedLLM,
    model: str,
    catalog: FieldCatalog,
    *,
    doc_id: str,
    doc_date: date | None,
    items: list[EvidenceItem],
    cache_dir: Path | None,
) -> tuple[list[ChangeEvent], Usage, str]:
    """Events for one addendum: (events, usage, how). `how` is "cached", "read", "empty" or
    "failed: <error>". Quotes that are not verbatim addendum text are dropped."""
    cache = cache_dir / f"{doc_id}.json" if cache_dir else None
    if cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return [ChangeEvent.model_validate(e) for e in data], Usage(), "cached"
    if not items:
        return [], Usage(), "empty"

    fields = changeable_fields(catalog)
    outcome = llm.call(
        system=EVENTS_SYSTEM,
        user=events_user(fields, items),
        schema=EventsOut,
        model=model,
        effort="medium",
    )
    if outcome.output is None:
        return [], outcome.usage, f"failed: {outcome.error}"  # not cached: retried next run

    events = _verified_events(outcome.output, fields, items, doc_date)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([e.model_dump(mode="json") for e in events]), encoding="utf-8")
    return events, outcome.usage, "read"


def _verified_events(
    out: EventsOut, fields: list[FieldSpec], items: list[EvidenceItem], doc_date: date | None
) -> list[ChangeEvent]:
    known = {f.key for f in fields}
    first = items[0]
    events: list[ChangeEvent] = []
    for seq, e in enumerate(out.events):
        if e.field not in known:
            continue
        # The passage that holds the quote, preferring one on the page the model named.
        ordered = sorted(items, key=lambda i: not i.page_start <= e.page <= i.page_end)
        found = next(((i, q) for i in ordered if (q := ground(e.quote, i.text)) is not None), None)
        if found is None:
            continue
        item, exact = found
        events.append(
            ChangeEvent(
                bid_id=first.bid_id,
                file_name=first.file,
                page=e.page if item.page_start <= e.page <= item.page_end else item.page_start,
                addendum_number=first.addendum_number,
                doc_date=doc_date,
                seq=seq,
                field=e.field,
                operation=e.operation,
                new_text=e.new_text,
                quote=exact,
                origin="llm",
            )
        )
    return events
