"""The retrieval agent: for each field in a task it plans queries (the field's name, its
configured queries, and on a retry new queries a cheap model writes from the validator's
reason), searches the bid with the hybrid engine, adds a search filtered to the field's
preferred document types, pulls in every chunk holding a labelled fact, and reranks the pool
with the cross-encoder. It returns ranked evidence with citations and hands the task to the
extraction agent.
"""

from typing import Any

from langgraph.types import Command, Send

from rfp_intel.agents.evidence import FieldEvidence, gather
from rfp_intel.agents.fields import FieldSpec
from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.llm import Usage
from rfp_intel.agents.outputs import QueriesOut
from rfp_intel.agents.prompts import REWRITE_SYSTEM, rewrite_user
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import ExtractionTask, RunState
from rfp_intel.search.models import DEFAULT_CONFIG

MAX_REWRITES = 4


def rewrite_queries(s: Services, spec: FieldSpec, reason: str) -> tuple[list[str], Usage]:
    """New queries for a field the validator rejected. If the model call fails, the reason
    itself is searched, which is how retries worked before rewriting."""
    with s.span("agent.retrieve.rewrite"):
        outcome = s.llm.call(
            system=REWRITE_SYSTEM,
            user=rewrite_user(spec, reason, [spec.name, *spec.queries]),
            schema=QueriesOut,
            model=s.settings.cheap_model,
            effort="low",
        )
    if outcome.output is None:
        return [reason[:200]], outcome.usage
    queries = [q.strip() for q in outcome.output.queries if q.strip()]
    return queries[:MAX_REWRITES] or [reason[:200]], outcome.usage


def retrieve(s: Services, state: RunState) -> Command[Any]:
    task = ExtractionTask.model_validate(state["task"])
    bid_id = str(state["bid_id"])
    usage = Usage()
    evidence: dict[str, dict[str, Any]] = {}
    rerank = s.engine.reranker is not None and (s.settings.extract_rerank or task.attempt > 1)
    with s.span(f"agent.retrieve.{task.batch}") as span, s.facts() as facts:
        span.set_attribute("agent.input", task.model_dump_json())
        for key in task.fields:
            spec = s.catalog.by_key(key)
            extra: list[str] = []
            if key in task.reasons:
                extra, u = rewrite_queries(s, spec, task.reasons[key])
                usage.add(u)
            ev: FieldEvidence = gather(
                s.engine, facts, s.store, bid_id, spec,
                extra_queries=extra, config=DEFAULT_CONFIG, rerank=rerank,
            )  # fmt: skip
            evidence[key] = ev.model_dump(mode="json")
        span.set_attribute("agent.reranked", rerank)
        span.set_attribute(
            "agent.output", io_attribute({k: v["evidence_ids"] for k, v in evidence.items()})
        )
    payload = {"bid_id": bid_id, "task": task.model_dump(), "evidence": evidence}
    passages = sum(len(v["evidence_ids"]) for v in evidence.values())
    return Command(
        update={"usage": usage.as_dict(), "log": [f"retrieve {task.batch}: {passages} passages"]},
        goto=Send("extract", payload),
    )
