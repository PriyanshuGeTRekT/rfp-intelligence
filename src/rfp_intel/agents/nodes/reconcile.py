"""The addendum reconciliation agent.

Change events come from two places: date facts inside addenda (no model), and one model call
per addendum over the passages search finds in it (`agents/addenda.py`). The date fields are
then resolved here by folding the events over the base documents (`agents/reconcile.py`);
text and list events are applied to the drafted values in the report. An addendum whose model
call fails is skipped with a note in the log and errors, not fatal to the run.
"""

from datetime import date
from typing import Any

from rfp_intel.agents.addenda import addendum_items, extract_events
from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.llm import Usage
from rfp_intel.agents.reconcile import (
    DATETIME_FIELDS,
    drop_restated_dates,
    events_from_facts,
    resolve_datetime,
)
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState


def reconcile(s: Services, state: RunState) -> dict[str, Any]:
    bid_id = str(state["bid_id"])
    log: list[str] = []
    errors: list[str] = []
    usage = Usage()
    with s.span("agent.reconcile") as span, s.facts() as facts:
        all_facts = facts.query(bid_id)
        date_events = events_from_facts(all_facts)
        events = list(date_events)
        for d in state.get("documents", []):
            if d["doc_type"] != "addendum":
                continue
            with s.span("agent.reconcile.addendum") as add_span:
                items = addendum_items(
                    s.engine, s.store, s.catalog, bid_id=bid_id, doc_id=d["doc_id"]
                )
                found, u, how = extract_events(
                    s.llm,
                    s.settings.cheap_model,
                    s.catalog,
                    doc_id=d["doc_id"],
                    doc_date=date.fromisoformat(d["doc_date"]) if d.get("doc_date") else None,
                    items=items,
                    cache_dir=s.settings.state_dir / "events",
                )
                add_span.set_attribute("rfp.file", d["file"])
                add_span.set_attribute("agent.passages", [i.evidence_id for i in items])
                add_span.set_attribute("agent.events", len(found))
                add_span.set_attribute("agent.how", how)
            kept = drop_restated_dates(found, date_events)
            events.extend(kept)
            usage.add(u)
            log.append(
                f"reconcile: {d['file']}: {len(kept)} events ({how}, {len(items)} passages, "
                f"{len(found) - len(kept)} restating a date dropped)"
            )
            if how.startswith("failed"):
                errors.append(f"addendum {d['file']}: {how}")

        resolved: dict[str, dict[str, Any]] = {}
        for key in DATETIME_FIELDS:
            if not s.catalog.by_key(key).reconcile:
                continue
            r = resolve_datetime(key, all_facts, events)
            if r.value is not None:
                resolved[key] = r.model_dump(mode="json")
        span.set_attribute("agent.events", len(events))
        span.set_attribute(
            "agent.output", io_attribute({k: v["value"] for k, v in resolved.items()})
        )
    return {
        "events": [e.model_dump(mode="json") for e in events],
        "resolved": resolved,
        "usage": usage.as_dict(),
        "errors": errors,
        "log": [*log, f"reconcile: {len(events)} events, resolved {sorted(resolved)}"],
    }
