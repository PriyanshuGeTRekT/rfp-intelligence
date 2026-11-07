"""Turning the graph's state into the output record: one `FieldResult` per field, the
addendum change log and the validation tally. Pure functions of the state plus the evidence
store; the only model call is the bid summary, made by the report node.
"""

import re
from dataclasses import dataclass, field

from rfp_intel.agents.confidence import Evidence, score
from rfp_intel.agents.evidence import EvidenceStore, FieldEvidence
from rfp_intel.agents.fields import FieldCatalog, FieldSpec
from rfp_intel.agents.reconcile import ChangeEvent, Resolution, apply_text_events
from rfp_intel.agents.schema import NOT_FOUND, AddendumChange, FieldResult, Source, ValidationTally
from rfp_intel.agents.state import RunState
from rfp_intel.agents.validate import FieldDraft, ValidationResult
from rfp_intel.facts.datetimes import find_dates

_SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")
_NUMBER_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
SUMMARY_SOURCES = ("due_date", "product", "company_name")


@dataclass
class Assembled:
    fields: dict[str, FieldResult]  # by key, in catalog order
    changes: list[AddendumChange]
    tally: ValidationTally
    errors: list[str] = field(default_factory=list)


def assemble(catalog: FieldCatalog, store: EvidenceStore, state: RunState) -> Assembled:
    """Every field except the summary, which needs the others first."""
    events = [ChangeEvent.model_validate(e) for e in state.get("events", [])]
    resolved = state.get("resolved", {})
    drafts = state.get("drafts", {})
    attempts = state.get("attempts", {})
    out = Assembled(fields={}, changes=[], tally=ValidationTally())
    for spec in catalog.fields:
        if spec.type == "summary":
            continue
        resolution = Resolution.model_validate(resolved[spec.key]) if spec.key in resolved else None
        validation: ValidationResult | None = None
        if spec.key in drafts:
            draft = FieldDraft.model_validate(drafts[spec.key])
            validation = ValidationResult.model_validate(state["validations"][spec.key])
            evidence = FieldEvidence.model_validate(state["evidence"][spec.key])
            fr, ch = from_draft(spec, draft, validation, evidence, events, store)
            if draft.error:
                out.errors.append(f"{spec.key}: {draft.error}")
            if resolution is not None:
                fr, ch = enrich(spec, resolution, fr), resolution.changes
        elif resolution is not None:
            fr, ch = from_resolution(spec, resolution)
        else:  # never dispatched: only possible if the run was cut short
            t, conf = score(Evidence(found=False, rejected=True))
            fr = FieldResult(
                key=spec.key, value=None, status="failed", confidence=conf, tier=t,
                notes="Extraction failed: the field was not processed in this run.",
            )  # fmt: skip
            ch = []
        _count(out.tally, fr, validation, attempts.get(spec.key, 1))
        out.fields[spec.key] = fr
        out.changes.extend(ch)
    out.changes = _unique(out.changes)
    return out


def _count(
    tally: ValidationTally, fr: FieldResult, v: ValidationResult | None, attempts: int
) -> None:
    tally.fields += 1
    tally.retries += attempts - 1
    if fr.status == "failed":
        tally.failed += 1
        for check in v.checks if v else []:
            if not check.passed:
                tally.checks_failed[check.name] = tally.checks_failed.get(check.name, 0) + 1
        return
    if fr.status == "not_found":
        tally.not_found += 1
    elif fr.status == "conflict":
        tally.conflicts += 1
    else:
        tally.passed += 1
    if attempts > 1:
        tally.passed_after_retry += 1
    else:
        tally.passed_first_time += 1


def from_resolution(spec: FieldSpec, r: Resolution) -> tuple[FieldResult, list[AddendumChange]]:
    t, conf = score(r.evidence)
    return (
        FieldResult(
            key=spec.key,
            value=r.value,
            status="conflict" if r.conflict else "found",
            sources=r.sources,
            confidence=conf,
            tier=t,
            normalized=r.normalized,
            notes=" ".join(r.notes) or None,
        ),
        r.changes,
    )


def enrich(spec: FieldSpec, r: Resolution, drafted: FieldResult) -> FieldResult:
    """A resolved date plus what the model read around it (place, attendance). The drafted
    value is used only when it passed validation and names the resolved date."""
    base, _ = from_resolution(spec, r)
    resolved_date = (r.normalized or {}).get("date")
    names_date = isinstance(drafted.value, str) and any(
        m.value.isoformat() == resolved_date for m in find_dates(drafted.value)
    )
    if drafted.status != "found" or not names_date:
        return base
    base.value = drafted.value
    base.sources = _unique_sources([*drafted.sources, *base.sources])
    base.notes = " ".join(n for n in (base.notes, drafted.notes) if n) or None
    return base


def from_draft(
    spec: FieldSpec,
    draft: FieldDraft,
    validation: ValidationResult,
    evidence: FieldEvidence,
    events: list[ChangeEvent],
    store: EvidenceStore,
) -> tuple[FieldResult, list[AddendumChange]]:
    notes = [draft.notes] if draft.notes else []
    if _absent_after_review(draft, validation):
        # Every attempt said "not found" with the labelled facts in front of it: the facts
        # carry the field's label but do not state it (a reporting period labelled as a term,
        # say). That is an unverified absence (NF-2), not a failed extraction.
        t, conf = score(Evidence(found=False, coverage_met=False))
        notes.insert(0, NOT_FOUND)
        notes.append(
            f"{evidence.typed_fact_count} labelled facts were reviewed on every attempt and "
            f"judged not to state this field. {evidence.coverage_note()}"
        )
        return FieldResult(
            key=spec.key, value=None, status="not_found", confidence=conf, tier=t,
            notes=" ".join(notes),
        ), []  # fmt: skip
    if not validation.passed:
        t, conf = score(Evidence(found=False, rejected=True))
        reason = validation.retry_reason or "rejected"
        prefix = "Extraction failed" if draft.error else "Rejected by the validator"
        notes.insert(0, f"{prefix}: {reason}.")
        return FieldResult(
            key=spec.key, value=None, status="failed", confidence=conf, tier=t,
            notes=" ".join(notes),
        ), []  # fmt: skip

    value = draft.value if draft.status == "found" else None
    sources = sources_from_quotes(store, draft) if draft.status == "found" else []
    changes: list[AddendumChange] = []
    set_by_addendum = False
    if spec.reconcile:
        # An addendum can set or add to a field the base documents never mention, so events
        # are applied even when the draft found nothing.
        value, changes, event_notes = apply_text_events(spec.key, value, events)
        notes.extend(event_notes)
        for c in changes:
            if c.operation in ("replace", "amend", "add_requirement"):
                set_by_addendum = True
                sources.append(c.source)
    if value is None:
        t, conf = score(Evidence(found=False, coverage_met=evidence.coverage_met(spec)))
        notes.insert(0, NOT_FOUND)
        notes.append(evidence.coverage_note())
        return FieldResult(
            key=spec.key, value=None, status="not_found", confidence=conf, tier=t,
            notes=" ".join(notes),
        ), changes  # fmt: skip

    from_ocr = any(
        (item := store.get(q.evidence_id)) is not None and item.ocr for q in draft.quotes
    )
    t, conf = score(
        Evidence(
            found=True,
            ocr=from_ocr,
            distinct_documents=len({src.file for src in sources}),
            set_by_addendum=set_by_addendum,
            confirmed_by_addendum=any(c.operation == "confirm" for c in changes),
        )
    )
    return (
        FieldResult(
            key=spec.key, value=value, status="found", sources=_unique_sources(sources),
            confidence=conf, tier=t, notes=" ".join(notes) or None,
        ),
        changes,
    )  # fmt: skip


def _absent_after_review(draft: FieldDraft, validation: ValidationResult) -> bool:
    failed = [c.name for c in validation.checks if not c.passed]
    return draft.status == "not_found" and not draft.error and failed == ["not_found_justified"]


def sources_from_quotes(store: EvidenceStore, draft: FieldDraft) -> list[Source]:
    out: list[Source] = []
    for q in draft.quotes:
        item = store.get(q.evidence_id)
        if item is None:
            continue
        out.append(
            Source(
                file=item.file,
                page=item.page_start,
                quote=q.text,
                doc_type=item.doc_type,
                addendum_number=item.addendum_number,
                evidence_id=item.evidence_id,
            )
        )
    return out


def summary_inputs(fields: dict[str, FieldResult]) -> dict[str, str]:
    """Field values as the summary writer sees them (dates in their readable form)."""
    out: dict[str, str] = {}
    for k, v in fields.items():
        display = (v.normalized or {}).get("display")
        text = ", ".join(v.value) if isinstance(v.value, list) else v.value
        out[k] = (display if display and text == v.value else text) or "not specified"
    return out


def _numbers(text: str) -> set[str]:
    """Numbers in a text, compared as numbers: "07" and "7" match, "1,000" and "1000" match."""
    return {n.replace(",", "").lstrip("0") or "0" for n in _NUMBER_RE.findall(text)}


def summary_field(
    spec: FieldSpec, text: str | None, error: str | None, fields: dict[str, FieldResult]
) -> FieldResult:
    """The generated summary, checked: 3 to 6 sentences, and no number that is not in the
    extracted fields (a number from nowhere is a hallucination)."""
    if text is None:
        t, conf = score(Evidence(found=False, rejected=True))
        return FieldResult(
            key=spec.key, value=None, status="failed", confidence=conf, tier=t,
            notes=f"The summary could not be generated: {error}.",
        )  # fmt: skip
    text = text.strip()
    sentences = len(_SENTENCE_RE.findall(text))
    known = " ".join([*summary_inputs(fields).values(), *(str(f.value) for f in fields.values())])
    invented = _numbers(text) - _numbers(known)
    notes: list[str] = []
    if not 3 <= sentences <= 6:
        notes.append(f"Summary has {sentences} sentences; 3 to 6 were requested.")
    if invented:
        notes.append(f"Numbers not present in the extracted fields: {sorted(invented)}.")
    sources = [src for key in SUMMARY_SOURCES if key in fields for src in fields[key].sources[:1]]
    return FieldResult(
        key=spec.key,
        value=text,
        status="found",
        sources=sources,
        confidence=0.85 if not notes else 0.70,
        tier="B" if not notes else "C",
        notes=" ".join(notes) or "Generated from the extracted fields.",
    )


def _unique(changes: list[AddendumChange]) -> list[AddendumChange]:
    seen: set[str] = set()
    out: list[AddendumChange] = []
    for c in changes:
        key = c.model_dump_json()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _unique_sources(sources: list[Source]) -> list[Source]:
    seen: set[tuple[str, int, str]] = set()
    out: list[Source] = []
    for s in sources:
        key = (s.file, s.page, s.quote)
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out
