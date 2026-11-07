"""The Q&A agent node: answers the question in the state (see `agents/qa.py`)."""

from typing import Any

from rfp_intel.agents import qa
from rfp_intel.agents.schema import BidResult
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState
from rfp_intel.search.manifest import Manifest


def _records(s: Services, bids: list[str]) -> dict[str, BidResult]:
    """The latest extraction record of each bid that has one (unreadable ones are skipped)."""
    out: dict[str, BidResult] = {}
    for bid in bids:
        path = s.settings.outputs_dir / f"{bid}.json"
        try:
            out[bid] = BidResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return out


def answer(s: Services, state: RunState) -> dict[str, Any]:
    with Manifest(s.settings.db_path) as manifest:
        known = manifest.bids()
    with s.span("agent.answer") as span, s.facts() as facts:
        context = qa.KnownContext(facts=facts, catalog=s.catalog, records=_records(s, known))
        result = qa.answer(
            s.engine,
            s.llm,
            s.settings.qa_model or s.settings.extract_model,
            state["question"],
            bid_id=state.get("bid_id"),
            known_bids=known,
            k=s.settings.qa_passages,
            config=s.settings.qa_search_config if s.engine.reranker else "hybrid_facts",
            budget_tokens=s.settings.llm_max_prompt_tokens,
            known=context,
        )
        span.set_attribute("qa.question", result.question)
        span.set_attribute("qa.scope", result.scope)
        span.set_attribute("qa.found", result.found)
        span.set_attribute("qa.citations", len(result.citations))
        span.set_attribute("agent.output", result.answer[:2000])
    return {
        "final_output": result.model_dump(mode="json"),
        "usage": result.usage,
        "errors": [result.error] if result.error else [],
        "log": [f"answer: found={result.found}, {len(result.citations)} citations"],
    }
