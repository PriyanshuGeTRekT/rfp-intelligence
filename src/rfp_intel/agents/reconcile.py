"""Addendum reconciliation as ordered change events.

Every addendum is a list of typed change events. A field's final value is the result of
applying those events, in order, to the value in the base documents. The application is a pure
function, so the Dallas due-date story (RFP says June 27; Addendum 1 says no extension is
planned; Addendum 2 moves it to July 9) is a unit test, not a prompt.

Where events come from:
- date fields: facts labelled deadline or pre_bid inside an addendum become "replace" events,
  deterministically, with the fact's sentence as the quote;
- everything else: one structured LLM call per addendum (agents phase), validated so that every
  event's quote is verbatim addendum text.

Source precedence: addendum events, then the main solicitation, then other attachments, then
the portal page. The portal never overrides a document; it fills a missing time or zone and
corroborates. A difference that no event explains is reported as a conflict, not resolved.
"""

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, Field

from rfp_intel.agents.confidence import Evidence
from rfp_intel.agents.schema import AddendumChange, Source
from rfp_intel.facts.datetimes import TimeMatch, datetime_value
from rfp_intel.facts.models import Fact, FactKind

Operation = Literal["replace", "amend", "confirm", "clarify", "add_requirement"]

# Which date facts drive which field.
DATETIME_FIELDS: dict[str, str] = {"due_date": "deadline", "pre_bid_meeting": "pre_bid"}
_PRECEDENCE = {
    "addendum": 0,
    "rfp": 1,
    "specs": 2,
    "affidavit": 2,
    "form": 2,
    "other": 2,
    "bid_page": 3,
}


class ChangeEvent(BaseModel):
    bid_id: str
    file_name: str
    page: int
    addendum_number: int | None
    doc_date: date | None
    seq: int  # order within the addendum
    field: str
    operation: Operation
    attribute: Literal["value", "date", "time", "tz", "list_item"] = "value"
    new_text: str | None = None
    normalized: dict[str, Any] | None = None
    quote: str
    origin: Literal["facts", "llm"] = "facts"

    def sort_key(self) -> tuple[int, date, int]:
        # Numbered addenda in number order; unnumbered ones by date, after numbered ones.
        return (
            self.addendum_number if self.addendum_number is not None else 10**6,
            self.doc_date or date.max,
            self.seq,
        )

    def source(self) -> Source:
        return Source(
            file=self.file_name,
            page=self.page,
            quote=self.quote,
            doc_type="addendum",
            addendum_number=self.addendum_number,
        )


class Resolution(BaseModel):
    field: str
    value: str | None
    normalized: dict[str, Any] | None = None
    sources: list[Source] = Field(default_factory=list)
    changes: list[AddendumChange] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    conflict: bool = False
    evidence: Evidence


def _fact_source(f: Fact) -> Source:
    return Source(
        file=f.file_name,
        page=f.page,
        quote=f.context,
        doc_type=f.doc_type,
        addendum_number=f.addendum_number,
    )


def _date_of(f: Fact) -> date | None:
    return date.fromisoformat(f.value["date"]) if f.value.get("date") else None


def events_from_facts(facts: Sequence[Fact]) -> list[ChangeEvent]:
    """Date changes stated in addenda, one replace event per labelled date fact."""
    events: list[ChangeEvent] = []
    by_label = {label: key for key, label in DATETIME_FIELDS.items()}
    ordered = sorted(facts, key=lambda f: (f.file_name, f.block_index, f.start))
    for seq, f in enumerate(ordered):
        if (
            f.doc_type != "addendum"
            or f.kind is not FactKind.DATETIME
            or not f.value.get("has_date")
        ):
            continue
        for label in f.fact_types:
            key = by_label.get(label)
            if key is None:
                continue
            events.append(
                ChangeEvent(
                    bid_id=f.bid_id,
                    file_name=f.file_name,
                    page=f.page,
                    addendum_number=f.addendum_number,
                    doc_date=date.fromisoformat(f.doc_date) if f.doc_date else None,
                    seq=seq,
                    field=key,
                    operation="replace",
                    new_text=f.raw,
                    normalized=f.value,
                    quote=f.context,
                )
            )
    return events


def drop_restated_dates(
    model_events: Sequence[ChangeEvent], date_events: Sequence[ChangeEvent]
) -> list[ChangeEvent]:
    """Model events for statements that are already date events.

    A sentence such as "The new due date for this RFP will be July 9, 2024" belongs to the date
    field the fact layer resolved. A model reading the addendum may also file it under another
    field (seen live: as a change to the contract term), so a model event whose quote contains
    the date text of a date event from the same file is dropped."""

    def flat(text: str) -> str:
        return " ".join(text.split()).casefold()

    dated = [(e.file_name, flat(e.new_text or "")) for e in date_events if e.new_text]
    return [
        e
        for e in model_events
        if not any(f == e.file_name and raw and raw in flat(e.quote) for f, raw in dated)
    ]


# ---------------------------------------------------------------------------------------------
# Date fields


def format_datetime(v: dict[str, Any]) -> str:
    """The output format: "2024-07-09 14:00 CDT", or "2024-07-09" without a time."""
    out = v.get("date") or ""
    if v.get("time"):
        t = time.fromisoformat(v["time"])
        zone = v.get("tz_effective") or v.get("tz_text")
        out += f" {t:%H:%M}" + (f" {zone}" if zone else "")
    return out


def display_datetime(v: dict[str, Any]) -> str:
    """ "July 9, 2024, 2:00 PM CDT", for people (kept in `normalized.display`)."""
    parts: list[str] = []
    if v.get("date"):
        d = date.fromisoformat(v["date"])
        parts.append(f"{d:%B} {d.day}, {d.year}")
    if v.get("time"):
        t = time.fromisoformat(v["time"])
        hour = t.hour % 12 or 12
        clock = f"{hour}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"
        zone = v.get("tz_effective") or v.get("tz_text")
        parts.append(f"{clock} {zone}" if zone else clock)
    return ", ".join(parts)


def _same_moment(a: dict[str, Any], b: dict[str, Any]) -> bool | None:
    """True or False when both values pin a moment; None when one lacks a time."""
    if a.get("utc") and b.get("utc"):
        return bool(a["utc"] == b["utc"])
    if a.get("date") != b.get("date"):
        return False
    if a.get("time") and b.get("time"):
        return bool(a["time"] == b["time"]) if not (a.get("iana") and b.get("iana")) else None
    return None


def _is_later(new: dict[str, Any], old: dict[str, Any]) -> bool:
    if new.get("utc") and old.get("utc"):
        return bool(new["utc"] > old["utc"])
    return bool((new.get("date") or "") > (old.get("date") or ""))


def _assemble(base: dict[str, Any], filler: dict[str, Any]) -> dict[str, Any]:
    """Base date with the filler's time and zone, recomputed as one value."""
    tz = filler.get("tz_text")
    hh, mm = (int(x) for x in filler["time"].split(":"))
    tm = TimeMatch(time(hh, mm), 0, 0, tz)
    return datetime_value(date.fromisoformat(base["date"]), tm)


def _rank(f: Fact) -> tuple[int, bool, bool, int]:
    return (
        _PRECEDENCE.get(f.doc_type, 2),
        not f.value.get("has_time"),
        not f.value.get("has_tz"),
        f.block_index,
    )


def resolve_datetime(
    field: str, facts: Sequence[Fact], events: Sequence[ChangeEvent]
) -> Resolution:
    label = DATETIME_FIELDS[field]
    typed = [
        f for f in facts
        if f.kind is FactKind.DATETIME and label in f.fact_types and f.value.get("has_date")
    ]  # fmt: skip
    documents = sorted((f for f in typed if f.doc_type not in ("addendum", "bid_page")), key=_rank)
    portal = sorted((f for f in typed if f.doc_type == "bid_page"), key=_rank)
    notes: list[str] = []
    sources: list[Source] = []
    ev = Evidence(found=True)

    current: dict[str, Any] | None = None
    current_text: str | None = None
    if documents:
        base = documents[0]
        current, current_text = dict(base.value), base.raw
        sources.append(_fact_source(base))
        if not base.value.get("has_time"):
            filler = next(
                (
                    p
                    for p in portal
                    if p.value.get("date") == base.value["date"] and p.value.get("has_time")
                ),
                None,
            )
            if filler is not None:
                current = _assemble(base.value, filler.value)
                current_text = f"{base.raw} {filler.raw.split(' ', 1)[-1]}"
                sources.append(_fact_source(filler))
                ev.assembled = True
                notes.append(
                    f"Date from {base.file_name}; time and zone from {filler.file_name} "
                    f"({filler.raw})."
                )
    elif portal:
        current, current_text = dict(portal[0].value), portal[0].raw
        sources.append(_fact_source(portal[0]))
        notes.append("Only the portal page states this; no document does.")

    changes: list[AddendumChange] = []
    for e in sorted((e for e in events if e.field == field), key=ChangeEvent.sort_key):
        if e.normalized is None:
            continue
        same = current is not None and _same_moment(current, e.normalized)
        if same:
            ev.confirmed_by_addendum = True
            changes.append(_change(field, "confirm", e, current_text, e.new_text))
            sources.append(e.source())
            continue
        changes.append(_change(field, e.operation, e, current_text, e.new_text))
        if current is not None:
            verb = "Extended" if _is_later(e.normalized, current) else "Changed"
            notes.append(
                f"{verb} by Addendum {e.addendum_number or '(unnumbered)'} "
                f"(original date: {format_datetime(current)})."
            )
        current, current_text = dict(e.normalized), e.new_text
        sources = [e.source()]
        ev.set_by_addendum = True
        ev.assembled = False
        notes = [n for n in notes if not n.startswith("Date from")]

    if current is None:
        return Resolution(
            field=field,
            value=None,
            notes=[f"No date labelled '{label}' in any document."],
            evidence=Evidence(found=False),
        )

    if current.get("tz_note"):
        notes.append(current["tz_note"])

    # Corroborate against the portal and the other document dates.
    conflict = False
    for p in portal:
        verdict = _same_moment(current, p.value)
        if verdict:
            if all(s.file != p.file_name for s in sources):
                sources.append(_fact_source(p))
            notes.append(f"Matches the portal's {p.raw}.")
        elif verdict is False:
            if ev.set_by_addendum:
                ev.explained_difference = True
                notes.append(f"The portal shows {p.raw}; the addendum supersedes it.")
            else:
                conflict = True
                notes.append(f"The portal shows {p.raw}, which no document or addendum explains.")
    ev.unexplained_conflict = conflict
    ev.distinct_documents = len({s.file for s in sources})
    if ev.set_by_addendum and any("Matches the portal" in n for n in notes):
        ev.explained_difference = False

    return Resolution(
        field=field,
        value=format_datetime(current),
        normalized={**current, "display": display_datetime(current)},
        sources=_dedupe(sources),
        changes=changes,
        notes=_dedupe_notes(notes),
        conflict=conflict,
        evidence=ev,
    )


def _change(
    field: str, op: Operation, e: ChangeEvent, old: str | None, new: str | None
) -> AddendumChange:
    return AddendumChange(
        field=field,
        operation=op,
        addendum_number=e.addendum_number,
        doc_date=e.doc_date,
        old_value=old,
        new_value=new,
        source=e.source(),
    )


def _dedupe(sources: list[Source]) -> list[Source]:
    seen: set[tuple[str, int, str]] = set()
    out: list[Source] = []
    for s in sources:
        key = (s.file, s.page, s.quote)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def _dedupe_notes(notes: list[str]) -> list[str]:
    return list(dict.fromkeys(notes))


# ---------------------------------------------------------------------------------------------
# Text and list fields (events from the LLM pass over each addendum)


def apply_text_events(
    field: str,
    value: str | list[str] | None,
    events: Sequence[ChangeEvent],
) -> tuple[str | list[str] | None, list[AddendumChange], list[str]]:
    """Fold replace, amend, clarify, confirm and add_requirement events into a value."""
    changes: list[AddendumChange] = []
    notes: list[str] = []
    current = value
    for e in sorted((e for e in events if e.field == field), key=ChangeEvent.sort_key):
        old = ", ".join(current) if isinstance(current, list) else current
        if e.operation == "replace":
            current = e.new_text
        elif e.operation == "amend":
            current = f"{old}; {e.new_text}" if old else e.new_text
        elif e.operation == "add_requirement":
            items = list(current) if isinstance(current, list) else ([current] if current else [])
            if e.new_text and e.new_text not in items:
                items.append(e.new_text)
            current = items
        elif e.operation == "clarify":
            notes.append(f"Addendum {e.addendum_number}: {e.new_text or e.quote}")
        new = ", ".join(current) if isinstance(current, list) else current
        changes.append(
            _change(field, e.operation, e, old, new if e.operation != "clarify" else e.new_text)
        )
    return current, changes, notes


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
