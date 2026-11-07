"""The extraction graph (LangGraph).

Roles from the brief and where they live:

- Orchestrator/Planner: `plan` checks the index, lists the documents and sets the plan; the
  conditional edges after `reconcile` and `validate` are the orchestration.
- Ingestion: `plan` indexes the folder when the manifest has nothing for it.
- Retrieval/Search: the search engine is a tool called by the extraction nodes (`gather`).
- Extraction: four `extract_group` nodes run in parallel (one `Send` per field group, one LLM
  call each); `extract_field` retries a single field with the validator's reason.
- Addendum Reconciliation: `reconcile` turns addenda into change events (dates from facts,
  the rest by one cached LLM call per addendum) and resolves the date fields; `finalize`
  applies the text events.
- Validator/Critic: `validate`, deterministic; failures loop back up to `max_retries`.
- Q&A/Report: `finalize` writes the JSON and the summary; Q&A is `agents/qa.py`.

State carries ids and small structures only; evidence text lives in an `EvidenceStore`.
Parallel branches write to dict keys with a merge reducer, so no branch overwrites another.
The graph is compiled with a SQLite checkpointer keyed by run id, so a crashed run resumes.
"""

import json
import operator
import re
import sqlite3
import threading
from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from opentelemetry import trace
from opentelemetry.trace import Span

from rfp_intel.agents.addenda import addendum_items, extract_events
from rfp_intel.agents.confidence import Evidence, score
from rfp_intel.agents.evidence import EvidenceStore, FieldEvidence, gather
from rfp_intel.agents.fields import FieldCatalog, FieldSpec
from rfp_intel.agents.llm import LLM, Usage
from rfp_intel.agents.outputs import GroupDraftOut, SummaryOut
from rfp_intel.agents.prompts import EXTRACT_SYSTEM, SUMMARY_SYSTEM, extraction_user, summary_user
from rfp_intel.agents.reconcile import (
    DATETIME_FIELDS,
    ChangeEvent,
    Resolution,
    apply_text_events,
    events_from_facts,
    resolve_datetime,
)
from rfp_intel.agents.schema import (
    AddendumChange,
    BidResult,
    DocumentInfo,
    FieldResult,
    Source,
    ValidationTally,
)
from rfp_intel.agents.validate import FieldDraft, ValidationResult, validate
from rfp_intel.config import Settings
from rfp_intel.facts.store import FactStore
from rfp_intel.ingestion.models import ParsedDocument
from rfp_intel.logs import get_logger
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.indexer import Indexer
from rfp_intel.search.manifest import Manifest
from rfp_intel.telemetry import new_run_id

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)

EXTRACT_EFFORT = "medium"
RETRY_CONFIG = "hybrid_facts_rerank"  # retries can afford the slow reranker


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {**a, **b}


def _add_usage(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    out = dict(a)
    for k, v in b.items():
        out[k] = round(out.get(k, 0) + v, 6)
    return out


class RunState(TypedDict, total=False):
    bid_id: str
    run_id: str
    plan: list[str]
    documents: list[dict[str, Any]]
    events: list[dict[str, Any]]
    resolved: Annotated[dict[str, dict[str, Any]], _merge]
    evidence: Annotated[dict[str, dict[str, Any]], _merge]
    drafts: Annotated[dict[str, dict[str, Any]], _merge]
    validations: Annotated[dict[str, dict[str, Any]], _merge]
    attempts: Annotated[dict[str, int], _merge]
    retries: list[dict[str, Any]]
    usage: Annotated[dict[str, float], _add_usage]
    log: Annotated[list[str], operator.add]
    result_path: str
    tally: dict[str, Any]
    # Send payloads
    group: str
    field: str
    reason: str
    attempt: int


@dataclass
class Services:
    settings: Settings
    engine: SearchEngine
    indexer: Indexer
    llm: LLM
    catalog: FieldCatalog
    store: EvidenceStore
    out_dir: Path
    max_retries: int = 2
    root_span: Span | None = None
    _lock: threading.Lock = dc_field(default_factory=threading.Lock)

    def span(self, name: str) -> Any:
        """A span under the run's root span, even from LangGraph's worker threads."""
        ctx = trace.set_span_in_context(self.root_span) if self.root_span is not None else None
        return tracer.start_as_current_span(name, context=ctx)

    def facts(self) -> FactStore:
        return FactStore(self.settings.db_path)


def _load_doc(settings: Settings, doc_id: str) -> ParsedDocument | None:
    path = settings.docs_dir / f"{doc_id}.json"
    if not path.exists():
        return None
    return ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# Nodes


def make_nodes(s: Services) -> dict[str, Any]:
    def plan(state: RunState) -> dict[str, Any]:
        bid_id = state["bid_id"]
        with s.span("agent.plan") as span:
            with Manifest(s.settings.db_path) as manifest:
                entries = manifest.entries(bid_id)
            notes: list[str] = []
            if not entries:
                folder = s.settings.data_dir / bid_id
                report = s.indexer.index_folder(folder)
                notes.append(f"indexed {len(report.added)} files")
                with Manifest(s.settings.db_path) as manifest:
                    entries = manifest.entries(bid_id)
            documents: list[dict[str, Any]] = []
            for rel, entry in sorted(entries.items()):
                doc = _load_doc(s.settings, entry.doc_id)
                documents.append(
                    DocumentInfo(
                        file=rel,
                        doc_type=entry.doc_type,
                        addendum_number=doc.addendum_number if doc else None,
                        doc_date=doc.doc_date if doc else None,
                        pages=doc.page_count if doc else 0,
                    ).model_dump(mode="json")
                    | {"doc_id": entry.doc_id}
                )
            groups = s.catalog.extraction_groups
            span.set_attribute("rfp.bid_id", bid_id)
            span.set_attribute("agent.documents", len(documents))
            span.set_attribute("agent.plan", groups)
            return {
                "plan": groups,
                "documents": documents,
                "log": [f"plan: {len(documents)} documents, groups {groups}", *notes],
            }

    def reconcile(state: RunState) -> dict[str, Any]:
        bid_id = state["bid_id"]
        with s.span("agent.reconcile") as span, s.facts() as facts:
            all_facts = facts.query(bid_id)
            events = events_from_facts(all_facts)
            usage = Usage()
            cache_dir = s.settings.state_dir / "events"
            for d in state["documents"]:
                if d["doc_type"] != "addendum":
                    continue
                items = addendum_items(s.engine.backend, d["doc_id"])
                found, u, cached = extract_events(
                    s.llm,
                    s.settings.cheap_model,
                    s.catalog,
                    doc_id=d["doc_id"],
                    doc_date=date.fromisoformat(d["doc_date"]) if d.get("doc_date") else None,
                    items=items,
                    cache_dir=cache_dir,
                )
                events.extend(found)
                usage.add(u)
                span.add_event(
                    "addendum", {"file": d["file"], "events": len(found), "cached": cached}
                )
            resolved: dict[str, dict[str, Any]] = {}
            for key in DATETIME_FIELDS:
                spec = s.catalog.by_key(key)
                if not spec.reconcile:
                    continue
                r = resolve_datetime(key, all_facts, events)
                if r.value is not None:
                    resolved[key] = r.model_dump(mode="json")
            span.set_attribute("agent.events", len(events))
            span.set_attribute("agent.resolved", sorted(resolved))
            return {
                "events": [e.model_dump(mode="json") for e in events],
                "resolved": resolved,
                "usage": usage.as_dict(),
                "log": [f"reconcile: {len(events)} events, resolved {sorted(resolved)}"],
            }

    def fan_out(state: RunState) -> Sequence[Send]:
        return [
            Send(
                "extract_group",
                {"bid_id": state["bid_id"], "group": g, "resolved": state.get("resolved", {})},
            )
            for g in state["plan"]
        ]

    def _extract(
        bid_id: str,
        fields: list[FieldSpec],
        *,
        attempt: int,
        reasons: dict[str, str] | None = None,
        config: str | None = None,
        span_name: str,
    ) -> dict[str, Any]:
        with s.span(span_name) as span, s.facts() as facts:
            span.set_attribute("agent.fields", [f.key for f in fields])
            span.set_attribute("agent.attempt", attempt)
            evidence: dict[str, FieldEvidence] = {}
            passages = {}
            candidates = {}
            for spec in fields:
                extra = [reasons[spec.key]] if reasons and spec.key in reasons else []
                kwargs: dict[str, Any] = {"extra_queries": extra}
                if config:
                    kwargs["config"] = config
                ev = gather(s.engine, facts, s.store, bid_id, spec, **kwargs)
                evidence[spec.key] = ev
                passages[spec.key] = s.store.many(ev.evidence_ids)
                candidates[spec.key] = ev.candidates
            user = extraction_user(fields, passages, candidates, reasons)
            out, usage = s.llm.structured(
                system=EXTRACT_SYSTEM,
                user=user,
                schema=GroupDraftOut,
                model=s.settings.extract_model,
                effort=EXTRACT_EFFORT,
            )
            drafts: dict[str, dict[str, Any]] = {}
            by_key = {f.key: f for f in fields}
            for d in out.drafts:
                target = by_key.get(d.field)
                if target is None:
                    continue
                drafts[d.field] = d.to_draft(target.type == "list").model_dump(mode="json")
            for key in by_key:
                if key not in drafts:
                    drafts[key] = FieldDraft(
                        field=key,
                        status="not_found",
                        notes="the model returned no draft for this field",
                    ).model_dump(mode="json")
            span.set_attribute("llm.input_tokens", usage.input_tokens)
            span.set_attribute("llm.output_tokens", usage.output_tokens)
            span.set_attribute("llm.cost_usd", usage.cost_usd)
            return {
                "evidence": {k: v.model_dump(mode="json") for k, v in evidence.items()},
                "drafts": drafts,
                "attempts": dict.fromkeys(by_key, attempt),
                "usage": usage.as_dict(),
                "log": [f"{span_name}: {sorted(by_key)} attempt {attempt}"],
            }

    def extract_group(state: RunState) -> dict[str, Any]:
        resolved = state.get("resolved", {})
        fields = [f for f in s.catalog.group(state["group"]) if f.key not in resolved]
        if not fields:
            return {"log": [f"extract_group {state['group']}: nothing to do"]}
        return _extract(
            state["bid_id"], fields, attempt=1, span_name=f"agent.extract.{state['group']}"
        )

    def extract_field(state: RunState) -> dict[str, Any]:
        spec = s.catalog.by_key(state["field"])
        return _extract(
            state["bid_id"],
            [spec],
            attempt=state["attempt"],
            reasons={spec.key: state["reason"]},
            config=RETRY_CONFIG,
            span_name=f"agent.retry.{spec.key}",
        )

    def validate_node(state: RunState) -> dict[str, Any]:
        with s.span("agent.validate") as span:
            validations: dict[str, dict[str, Any]] = {}
            retries: list[dict[str, Any]] = []
            for key, raw in state.get("drafts", {}).items():
                draft = FieldDraft.model_validate(raw)
                spec = s.catalog.by_key(key)
                ev = FieldEvidence.model_validate(state["evidence"][key])
                result = validate(draft, spec, s.store, ev)
                validations[key] = result.model_dump(mode="json")
                attempt = state.get("attempts", {}).get(key, 1)
                if not result.passed and attempt <= s.max_retries:
                    retries.append(
                        {
                            "field": key,
                            "reason": result.retry_reason or "rejected",
                            "attempt": attempt + 1,
                        }
                    )
            failed = [k for k, v in validations.items() if not v["passed"]]
            span.set_attribute("agent.failed", failed)
            span.set_attribute("agent.retrying", [r["field"] for r in retries])
            return {
                "validations": validations,
                "retries": retries,
                "log": [
                    f"validate: {len(failed)} failed, retrying {[r['field'] for r in retries]}"
                ],
            }

    def after_validate(state: RunState) -> Hashable | Sequence[Hashable]:
        retries = state.get("retries", [])
        if not retries:
            return "finalize"
        return [Send("extract_field", {"bid_id": state["bid_id"], **r}) for r in retries]

    def finalize(state: RunState) -> dict[str, Any]:
        with s.span("agent.finalize") as span:
            result, usage = _build_result(s, state)
            s.out_dir.mkdir(parents=True, exist_ok=True)
            path = s.out_dir / f"{state['bid_id']}.json"
            path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            span.set_attribute("agent.result_path", str(path))
            span.set_attribute("agent.validation", json.dumps(result.validation.model_dump()))
            return {
                "result_path": str(path),
                "tally": result.validation.model_dump(),
                "usage": usage.as_dict(),
                "log": [f"finalize: wrote {path}"],
            }

    return {
        "plan": plan,
        "reconcile": reconcile,
        "fan_out": fan_out,
        "extract_group": extract_group,
        "extract_field": extract_field,
        "validate": validate_node,
        "after_validate": after_validate,
        "finalize": finalize,
    }


# ---------------------------------------------------------------------------------------------
# Result assembly


def _sources_from_quotes(s: Services, draft: FieldDraft) -> list[Source]:
    out: list[Source] = []
    for q in draft.quotes:
        item = s.store.get(q.evidence_id)
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


def _field_from_resolution(r: Resolution) -> tuple[FieldResult, list[AddendumChange]]:
    t, conf = score(r.evidence)
    return (
        FieldResult(
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


def _field_from_draft(
    s: Services,
    spec: FieldSpec,
    draft: FieldDraft,
    validation: ValidationResult,
    evidence: FieldEvidence,
    events: list[ChangeEvent],
) -> tuple[FieldResult, list[AddendumChange]]:
    notes = [draft.notes] if draft.notes else []
    if not validation.passed:
        t, conf = score(Evidence(found=False, rejected=True))
        notes.append(f"Rejected by the validator: {validation.retry_reason}")
        return FieldResult(
            value=None, status="not_found", confidence=conf, tier=t, notes=" ".join(notes)
        ), []
    value = draft.value if draft.status == "found" else None
    changes: list[AddendumChange] = []
    sources = _sources_from_quotes(s, draft) if draft.status == "found" else []
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
        notes.append(evidence.coverage_note())
        return FieldResult(
            value=None, status="not_found", confidence=conf, tier=t, notes=" ".join(notes)
        ), changes

    ev = Evidence(
        found=True,
        distinct_documents=len({src.file for src in sources}),
        set_by_addendum=set_by_addendum,
        confirmed_by_addendum=any(c.operation == "confirm" for c in changes),
    )
    t, conf = score(ev)
    return (
        FieldResult(
            value=value,
            status="found",
            sources=sources,
            confidence=conf,
            tier=t,
            notes=" ".join(notes) or None,
        ),
        changes,
    )


_SENTENCE_RE = re.compile(r"[.!?](?:\s|$)")


def _summary(s: Services, fields: dict[str, FieldResult]) -> tuple[FieldResult, Usage]:
    values = {
        k: (", ".join(v.value) if isinstance(v.value, list) else v.value) or "not specified"
        for k, v in fields.items()
    }
    out, usage = s.llm.structured(
        system=SUMMARY_SYSTEM,
        user=summary_user(values),
        schema=SummaryOut,
        model=s.settings.cheap_model,
        effort="low",
    )
    text = out.summary.strip()
    sentences = len(_SENTENCE_RE.findall(text))
    numbers = set(re.findall(r"\d[\d,]*", text)) - set(
        re.findall(r"\d[\d,]*", " ".join(values.values()))
    )
    notes = []
    if not 3 <= sentences <= 6:
        notes.append(f"Summary has {sentences} sentences; 3 to 6 were requested.")
    if numbers:
        notes.append(f"Numbers not present in the extracted fields: {sorted(numbers)}.")
    sources = [
        src
        for key in ("due_date", "product", "company_name")
        for src in fields[key].sources[:1]
        if key in fields
    ]
    tier = "B" if not notes else "C"
    return (
        FieldResult(
            value=text,
            status="found",
            sources=sources,
            confidence=0.85 if tier == "B" else 0.70,
            tier=tier,
            notes=" ".join(notes) or "Generated from the extracted fields.",
        ),
        usage,
    )


def _build_result(s: Services, state: RunState) -> tuple[BidResult, Usage]:
    events = [ChangeEvent.model_validate(e) for e in state.get("events", [])]
    fields: dict[str, FieldResult] = {}
    changes: list[AddendumChange] = []
    attempts = state.get("attempts", {})
    tally = ValidationTally(
        fields=0, passed_first_time=0, passed_after_retry=0, failed=0, retries=0
    )
    for spec in s.catalog.fields:
        if spec.type == "summary":
            continue
        tally.fields += 1
        if spec.key in state.get("resolved", {}):
            fr, ch = _field_from_resolution(Resolution.model_validate(state["resolved"][spec.key]))
            tally.passed_first_time += 1
        else:
            draft = FieldDraft.model_validate(state["drafts"][spec.key])
            validation = ValidationResult.model_validate(state["validations"][spec.key])
            evidence = FieldEvidence.model_validate(state["evidence"][spec.key])
            fr, ch = _field_from_draft(s, spec, draft, validation, evidence, events)
            n = attempts.get(spec.key, 1)
            tally.retries += n - 1
            if validation.passed and n == 1:
                tally.passed_first_time += 1
            elif validation.passed:
                tally.passed_after_retry += 1
            else:
                tally.failed += 1
                for check in validation.checks:
                    if not check.passed:
                        tally.checks_failed[check.name] = tally.checks_failed.get(check.name, 0) + 1
        fields[spec.key] = fr
        changes.extend(ch)
    summary, usage = _summary(s, fields)
    fields["bid_summary"] = summary
    documents = [DocumentInfo.model_validate(d) for d in state.get("documents", [])]
    total = dict(state.get("usage", {}))
    for k, v in usage.as_dict().items():
        total[k] = round(total.get(k, 0) + v, 6)
    result = BidResult(
        bid_id=state["bid_id"],
        run_id=state["run_id"],
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        documents=documents,
        fields=fields,
        addendum_changes=_unique_changes(changes),
        validation=tally,
        usage=total,
    )
    return result, usage


def _unique_changes(changes: list[AddendumChange]) -> list[AddendumChange]:
    seen: set[str] = set()
    out: list[AddendumChange] = []
    for c in changes:
        key = c.model_dump_json()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


# ---------------------------------------------------------------------------------------------
# Graph


def build_graph(s: Services, checkpointer: SqliteSaver | None = None) -> Any:
    nodes = make_nodes(s)
    g: StateGraph[RunState] = StateGraph(RunState)
    g.add_node("plan", nodes["plan"])
    g.add_node("reconcile", nodes["reconcile"])
    g.add_node("extract_group", nodes["extract_group"])
    g.add_node("extract_field", nodes["extract_field"])
    g.add_node("validate", nodes["validate"])
    g.add_node("finalize", nodes["finalize"])
    g.add_edge(START, "plan")
    g.add_edge("plan", "reconcile")
    g.add_conditional_edges("reconcile", nodes["fan_out"], ["extract_group"])
    g.add_edge("extract_group", "validate")
    g.add_conditional_edges("validate", nodes["after_validate"], ["extract_field", "finalize"])
    g.add_edge("extract_field", "validate")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)


def run_extraction(
    s: Services,
    bid_id: str,
    *,
    run_id: str | None = None,
    resume: bool = False,
    checkpoint_path: Path | None = None,
) -> tuple[BidResult, RunState]:
    """Run (or resume) the graph for one bid and return the result and final state."""
    run_id = run_id or new_run_id()
    checkpointer = None
    conn = None
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    try:
        with tracer.start_as_current_span("agent.run") as root:
            root.set_attribute("rfp.bid_id", bid_id)
            root.set_attribute("rfp.run_id", run_id)
            s.root_span = root
            graph = build_graph(s, checkpointer)
            config = {"configurable": {"thread_id": run_id}}
            initial: RunState | None = None if resume else {"bid_id": bid_id, "run_id": run_id}
            final: RunState = graph.invoke(initial, config=config)
            path = Path(final["result_path"])
            result = BidResult.model_validate_json(path.read_text(encoding="utf-8"))
            root.set_attribute("llm.cost_usd", result.usage.get("cost_usd", 0.0))
            log.info(
                "extraction_done", bid_id=bid_id, run_id=run_id, path=str(path), usage=result.usage
            )
            return result, final
    finally:
        if conn is not None:
            conn.close()
