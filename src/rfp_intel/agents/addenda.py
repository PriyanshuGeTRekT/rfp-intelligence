"""Change events from addenda, by one structured LLM call per addendum.

Date changes come from facts with no model (see reconcile.events_from_facts). Everything else
(a new form to submit, a clarified requirement, an amended term) needs reading, so each
addendum is read once, its events are checked so that every quote is verbatim addendum text,
and the result is cached by document id. A re-run, or the same addendum in another run, costs
nothing; and the extraction pass never calls the model about addenda again.
"""

import json
from datetime import date
from pathlib import Path

from opentelemetry import trace

from rfp_intel.agents.evidence import EvidenceItem
from rfp_intel.agents.fields import FieldCatalog
from rfp_intel.agents.llm import LLM, Usage
from rfp_intel.agents.outputs import EventsOut
from rfp_intel.agents.prompts import EVENTS_SYSTEM, events_user
from rfp_intel.agents.reconcile import ChangeEvent
from rfp_intel.agents.validate import norm
from rfp_intel.search.backend import SearchBackend

tracer = trace.get_tracer(__name__)


def addendum_items(backend: SearchBackend, doc_id: str) -> list[EvidenceItem]:
    """Every chunk of one addendum, in document order."""
    items = [
        EvidenceItem(
            evidence_id=p["chunk_id"],
            bid_id=p.get("bid_id", ""),
            file=p["file_name"],
            page_start=p["page_start"],
            page_end=p["page_end"],
            doc_type=p["doc_type"],
            addendum_number=p.get("addendum_number"),
            section=" > ".join(p.get("section_path", [])),
            text=p["text"],
        )
        for p in backend.scroll_document(doc_id)
    ]
    return sorted(items, key=lambda i: (i.page_start, i.evidence_id))


def extract_events(
    llm: LLM,
    model: str,
    catalog: FieldCatalog,
    *,
    doc_id: str,
    doc_date: date | None,
    items: list[EvidenceItem],
    cache_dir: Path | None,
) -> tuple[list[ChangeEvent], Usage, bool]:
    """Events for one addendum: (events, usage, from_cache). Quotes not verbatim are dropped."""
    cache = cache_dir / f"{doc_id}.json" if cache_dir else None
    if cache and cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        return [ChangeEvent.model_validate(e) for e in data], Usage(), True
    if not items:
        return [], Usage(), False

    fields = [f for f in catalog.fields if f.reconcile and f.type != "datetime"]
    first = items[0]
    with tracer.start_as_current_span("agent.addendum_events") as span:
        span.set_attribute("rfp.file", first.file)
        out, usage = llm.structured(
            system=EVENTS_SYSTEM,
            user=events_user(fields, items),
            schema=EventsOut,
            model=model,
            effort="medium",
        )
        by_page: dict[int, str] = {}
        for item in items:
            for page in range(item.page_start, item.page_end + 1):
                by_page[page] = by_page.get(page, "") + "\n" + norm(item.text)
        known = {f.key for f in fields}
        events: list[ChangeEvent] = []
        dropped = 0
        for seq, e in enumerate(out.events):
            quote = norm(e.quote)
            found_page = next((p for p, t in by_page.items() if quote in t), None)
            if e.field not in known or found_page is None:
                dropped += 1
                continue
            events.append(
                ChangeEvent(
                    bid_id=first.bid_id,
                    file_name=first.file,
                    page=e.page if quote in by_page.get(e.page, "") else found_page,
                    addendum_number=first.addendum_number,
                    doc_date=doc_date,
                    seq=seq,
                    field=e.field,
                    operation=e.operation,
                    new_text=e.new_text,
                    quote=e.quote,
                    origin="llm",
                )
            )
        span.set_attribute("agent.events", len(events))
        span.set_attribute("agent.events_dropped", dropped)
        span.set_attribute("llm.cost_usd", usage.cost_usd)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([e.model_dump(mode="json") for e in events]), encoding="utf-8")
    return events, usage, False
