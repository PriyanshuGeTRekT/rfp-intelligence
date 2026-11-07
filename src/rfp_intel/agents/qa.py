"""Question answering with citations.

Retrieve, ask the model for an answer with quoted citations, then check every quote against
the passage it cites. Citations that are not verbatim are dropped; an answer left with no
valid citation is not an answer, so it becomes "Not found in documents" rather than an
unsupported claim.
"""

from collections.abc import Sequence

from opentelemetry import trace
from pydantic import BaseModel, Field

from rfp_intel.agents.evidence import EvidenceItem, EvidenceStore
from rfp_intel.agents.llm import LLM, Usage
from rfp_intel.agents.outputs import AnswerOut
from rfp_intel.agents.prompts import QA_SYSTEM, qa_user
from rfp_intel.agents.validate import norm
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.models import DEFAULT_CONFIG, SearchConfig

tracer = trace.get_tracer(__name__)
NOT_FOUND = "Not found in documents."


class Citation(BaseModel):
    bid_id: str
    file: str
    page: str
    quote: str
    evidence_id: str


class QAResult(BaseModel):
    question: str
    bid_id: str | None
    found: bool
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    passages_reviewed: int
    dropped_citations: int = 0
    config: str
    usage: dict[str, float | int] = Field(default_factory=dict)


def _check(out: AnswerOut, items: Sequence[EvidenceItem]) -> tuple[list[Citation], int]:
    by_id = {i.evidence_id: i for i in items}
    kept: list[Citation] = []
    dropped = 0
    for c in out.citations:
        item = by_id.get(c.evidence_id)
        if item is None or norm(c.quote) not in norm(item.text):
            dropped += 1
            continue
        kept.append(
            Citation(
                bid_id=item.bid_id,
                file=item.file,
                page=item.pages,
                quote=c.quote,
                evidence_id=item.evidence_id,
            )
        )
    return kept, dropped


def answer(
    engine: SearchEngine,
    llm: LLM,
    model: str,
    question: str,
    *,
    bid_id: str | None = None,
    k: int = 8,
    config: SearchConfig | str = DEFAULT_CONFIG,
    effort: str = "medium",
) -> QAResult:
    cfg_name = config if isinstance(config, str) else config.name
    with tracer.start_as_current_span("agent.qa") as span:
        span.set_attribute("qa.question", question)
        result = engine.search(question, bid_id=bid_id, k=k, config=config)
        store = EvidenceStore(loader=engine.backend.fetch)
        items = store.many([h.chunk_id for h in result.hits])
        usage = Usage()
        if not items:
            span.set_attribute("qa.found", False)
            return QAResult(
                question=question, bid_id=bid_id, found=False, answer=NOT_FOUND,
                passages_reviewed=0, config=cfg_name, usage=usage.as_dict(),
            )  # fmt: skip

        user = qa_user(question, items)
        out, u = llm.structured(
            system=QA_SYSTEM, user=user, schema=AnswerOut, model=model, effort=effort
        )
        usage.add(u)
        citations, dropped = _check(out, items)
        if out.found and not citations:
            # One more try, telling the model exactly what went wrong.
            note = (
                "\n\nYour previous citations were not exact text from the passages and were "
                "rejected. Quote verbatim, or set found to false."
            )
            out, u = llm.structured(
                system=QA_SYSTEM, user=user + note, schema=AnswerOut, model=model, effort=effort
            )
            usage.add(u)
            citations, dropped2 = _check(out, items)
            dropped += dropped2

        found = bool(out.found and citations)
        span.set_attribute("qa.found", found)
        span.set_attribute("qa.citations", len(citations))
        span.set_attribute("qa.dropped_citations", dropped)
        span.set_attribute("llm.cost_usd", usage.cost_usd)
        return QAResult(
            question=question,
            bid_id=bid_id,
            found=found,
            answer=out.answer if found else NOT_FOUND,
            citations=citations,
            passages_reviewed=len(items),
            dropped_citations=dropped,
            config=cfg_name,
            usage=usage.as_dict(),
        )
