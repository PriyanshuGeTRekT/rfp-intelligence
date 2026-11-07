"""The Q&A agent: answers a question with citations, or says it is not in the documents.

Retrieval is planned from the question and uses what the system already knows:
- scope: the bid given, else the bids the question names ("Bid1"), else every bid when the
  question compares ("compare", "both", "each bid"), else the whole index;
- a comparison searches each bid separately, so one bid's passages cannot crowd out another's;
- a question about addenda also searches only addenda, so the change itself is in the evidence;
- the chunks holding facts with the labels the question routes to (a deadline question: every
  dated deadline statement, addenda included) are always added, as they are for extraction;
- when a bid has been extracted, its addendum-reconciled values for those fields are given as
  context ("Reconciled values"), so "after all addenda" is answered with the final value.

The model answers in statements, one sentence each with its own quoted citations. Every quote
is checked against the passage it cites (`validate.ground`) and replaced by the passage's
exact text; a citation that does not reproduce passage text is dropped, and a statement left
without a valid citation is removed, so no sentence in an answer is uncited. An answer with no
statement left becomes "Not found in documents." A failed model call returns an answer that
says so, with the error, instead of raising.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from rfp_intel.agents.evidence import EvidenceItem, EvidenceStore
from rfp_intel.agents.fields import FieldCatalog
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.llm import Usage, estimate_tokens
from rfp_intel.agents.outputs import AnswerOut
from rfp_intel.agents.prompts import QA_SYSTEM, fit_passages, qa_user
from rfp_intel.agents.schema import NOT_FOUND, BidResult
from rfp_intel.agents.validate import ground
from rfp_intel.facts.store import FactStore
from rfp_intel.search.backend import Filters
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.models import SearchConfig

COMPARE_WORDS = ("compare", "comparison", "both", "each bid", "all bids", "across", "versus", " vs")
ADDENDUM_WORDS = ("addendum", "addenda", "amendment", "changed", "extension", "extended")
PROMPT_OVERHEAD = 300  # headers, labels and the retry note, in tokens
RETRY_NOTE = (
    "\n\nYour previous citations were not exact text from the passages and were rejected. "
    "Quote verbatim, or set found to false."
)


class Citation(BaseModel):
    bid_id: str
    file: str
    page: str
    quote: str
    evidence_id: str


class Statement(BaseModel):
    text: str
    citations: list[int]  # indexes into QAResult.citations


class QAResult(BaseModel):
    question: str
    bid_id: str | None
    found: bool
    answer: str
    statements: list[Statement] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    passages_reviewed: int
    dropped_citations: int = 0
    removed_statements: int = 0  # sentences dropped because no citation supported them
    config: str
    model: str = ""
    scope: list[str] = Field(default_factory=list)
    error: str | None = None
    usage: dict[str, float | int] = Field(default_factory=dict)
    cached_from: str | None = None  # the earlier question whose answer the cache returned
    cache_similarity: float | None = None


@dataclass
class KnownContext:
    """What the system knows beyond search: typed facts, field definitions, extracted records."""

    facts: FactStore | None = None
    catalog: FieldCatalog | None = None
    records: dict[str, BidResult] = field(default_factory=dict)


FACT_CHUNKS_PER_BID = 4


def fact_chunk_ids(
    engine: SearchEngine, facts: FactStore, bids: Sequence[str], fact_types: Sequence[str]
) -> list[str]:
    """Chunks holding facts with the routed labels, per bid."""
    ids: list[str] = []
    for bid in bids:
        typed = facts.query(bid, fact_types=list(fact_types))
        ids += engine.backend.chunks_with_facts(
            [f.fact_id for f in typed], Filters(bid_id=bid), limit=FACT_CHUNKS_PER_BID
        )
    return ids


def reconciled_values(
    catalog: FieldCatalog,
    records: dict[str, BidResult],
    bids: Sequence[str],
    fact_types: Sequence[str],
) -> list[str]:
    """'Bid1 · Due Date: 2024-07-09 14:00 CDT (Extended by Addendum 2 ...)' for the fields the
    question routes to, from each bid's extraction record."""
    specs = [f for f in catalog.fields if set(f.fact_types) & set(fact_types)]
    lines: list[str] = []
    for bid in bids:
        record = records.get(bid)
        if record is None:
            continue
        for spec in specs:
            fr = next((f for f in record.fields.values() if f.key == spec.key), None)
            if fr is None or fr.status not in ("found", "conflict"):
                continue
            value = ", ".join(fr.value) if isinstance(fr.value, list) else fr.value
            note = f" ({fr.notes[:300]})" if fr.notes else ""
            lines.append(f"{bid} · {spec.name}: {value}{note}")
    return lines


class RetrievalPlan(BaseModel):
    """How the Q&A agent searches for one question."""

    bids: list[str | None]  # None: the whole index
    per_bid: int
    addenda: bool


def plan_retrieval(
    question: str, bid_id: str | None, known_bids: Sequence[str], k: int
) -> RetrievalPlan:
    q = question.casefold()
    named = [b for b in known_bids if re.search(rf"\b{re.escape(b.casefold())}\b", q)]
    compares = any(w in q for w in COMPARE_WORDS)
    bids: list[str | None]
    if bid_id:
        bids = [bid_id]
    elif named:
        bids = list(named)
    elif compares and known_bids:
        bids = list(known_bids)
    else:
        bids = [None]
    per_bid = max(3, k // len(bids)) if len(bids) > 1 else k
    return RetrievalPlan(bids=bids, per_bid=per_bid, addenda=any(w in q for w in ADDENDUM_WORDS))


def retrieve(
    engine: SearchEngine,
    store: EvidenceStore,
    question: str,
    plan: RetrievalPlan,
    config: SearchConfig | str,
) -> list[EvidenceItem]:
    ids: list[str] = []
    for bid in plan.bids:
        ids += [
            h.chunk_id
            for h in engine.search(question, bid_id=bid, k=plan.per_bid, config=config).hits
        ]
        if plan.addenda:
            hits = engine.search(
                question, bid_id=bid, doc_types=["addendum"], k=3, config=config
            ).hits
            ids += [h.chunk_id for h in hits]
    return store.many(list(dict.fromkeys(ids)))


@dataclass
class Checked:
    """An answer after verification: only statements with a grounded citation remain."""

    statements: list[Statement] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    dropped_citations: int = 0
    removed_statements: int = 0

    @property
    def text(self) -> str:
        return " ".join(st.text for st in self.statements)


def check_answer(out: AnswerOut, items: Sequence[EvidenceItem]) -> Checked:
    by_id = {i.evidence_id: i for i in items}
    checked = Checked()
    index: dict[tuple[str, str], int] = {}
    for st in out.statements if out.found else []:
        refs: list[int] = []
        for c in st.citations:
            # The cited passage first, then any other passage shown (a mixed-up id).
            candidates = [by_id[c.evidence_id]] if c.evidence_id in by_id else []
            candidates += [i for i in items if i.evidence_id != c.evidence_id]
            found = next(
                ((i, q) for i in candidates if (q := ground(c.quote, i.text)) is not None), None
            )
            if found is None:
                checked.dropped_citations += 1
                continue
            item, exact = found
            key = (item.evidence_id, exact)
            if key not in index:
                index[key] = len(checked.citations)
                checked.citations.append(
                    Citation(
                        bid_id=item.bid_id,
                        file=item.file,
                        page=item.pages,
                        quote=exact,
                        evidence_id=item.evidence_id,
                    )
                )
            refs.append(index[key])
        if refs and st.text.strip():
            checked.statements.append(Statement(text=st.text.strip(), citations=refs))
        else:
            checked.removed_statements += 1
    return checked


def answer(
    engine: SearchEngine,
    llm: GuardedLLM,
    model: str,
    question: str,
    *,
    bid_id: str | None = None,
    known_bids: Sequence[str] = (),
    k: int = 8,
    config: SearchConfig | str = "hybrid_facts",
    effort: str = "medium",
    budget_tokens: int = 24_000,
    known: KnownContext | None = None,
) -> QAResult:
    cfg_name = config if isinstance(config, str) else config.name
    plan = plan_retrieval(question, bid_id, known_bids, k)
    store = EvidenceStore(loader=engine.backend.fetch)
    items = retrieve(engine, store, question, plan, config)
    reconciled: list[str] = []
    fact_types = engine.analyze(question).fact_types
    if known is not None and fact_types:
        bids = [b for b in plan.bids if b] or list(known_bids)
        if known.facts is not None:
            first = store.many(fact_chunk_ids(engine, known.facts, bids, fact_types))
            seen = {i.evidence_id for i in first}
            items = first + [i for i in items if i.evidence_id not in seen]
        if known.catalog is not None:
            reconciled = reconciled_values(known.catalog, known.records, bids, fact_types)
    # The budget covers the whole prompt: passages get what the instructions leave.
    fixed = estimate_tokens(QA_SYSTEM + question + "\n".join(reconciled)) + PROMPT_OVERHEAD
    items = fit_passages({"q": items}, max(1_000, budget_tokens - fixed))["q"]
    scope = [b or "all" for b in plan.bids]
    usage = Usage()

    def result(text: str, checked: Checked | None = None, error: str | None = None) -> QAResult:
        checked = checked or Checked()
        return QAResult(
            question=question,
            bid_id=bid_id,
            found=bool(checked.statements),
            answer=text,
            statements=checked.statements,
            citations=checked.citations,
            passages_reviewed=len(items),
            dropped_citations=checked.dropped_citations,
            removed_statements=checked.removed_statements,
            config=cfg_name,
            model=model,
            scope=scope,
            error=error,
            usage=usage.as_dict(),
        )

    if not items:
        return result(NOT_FOUND)
    user = qa_user(question, items, reconciled)
    outcome = llm.call(system=QA_SYSTEM, user=user, schema=AnswerOut, model=model, effort=effort)
    usage.add(outcome.usage)
    if outcome.output is None:
        return result(
            "The question could not be answered: the model call failed.", error=outcome.error
        )
    out = outcome.output
    checked = check_answer(out, items)
    if out.found and not checked.statements:  # one more try, saying exactly what went wrong
        retry = llm.call(
            system=QA_SYSTEM, user=user + RETRY_NOTE, schema=AnswerOut, model=model, effort=effort
        )
        usage.add(retry.usage)
        if retry.output is not None:
            again = check_answer(retry.output, items)
            again.dropped_citations += checked.dropped_citations
            checked = again
    if not checked.statements:
        return result(NOT_FOUND, checked)
    return result(checked.text, checked)
