"""The agent graph (LangGraph): one graph for both modes.

    START -> plan --(ask)-----> answer -> END
             plan --(extract)-> ingest -> reconcile --(dispatch)--> retrieve x N (parallel)
                                -> extract x N -> validate
             validate --(rejected fields)--> retrieve (retry, with the reason) -> ...
             validate --(all settled)------> report -> END

Why LangGraph: the brief's flow is a graph with a loop (validator back to retrieval), a
fan-out (field batches in parallel) and a router (extract vs ask). LangGraph gives those as
first-class edges (`Send` for fan-out with per-branch payloads, conditional edges for the
loop), typed shared state with reducers for parallel writes, and a SQLite checkpointer so a
crashed run resumes where it stopped. The agents stay plain functions over that state, so
they are unit-testable without the framework.

State carries ids and small structures only; evidence text lives in an `EvidenceStore`.
"""

import sqlite3
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace

from rfp_intel.agents.nodes import (
    answer,
    extract,
    ingest,
    orchestrator,
    reconcile,
    report,
    retrieve,
    validate,
)
from rfp_intel.agents.qa import QAResult
from rfp_intel.agents.schema import BidResult
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState
from rfp_intel.logs import get_logger
from rfp_intel.telemetry import new_run_id

log = get_logger(__name__)
if TYPE_CHECKING:
    from rfp_intel.agents.qa_cache import SemanticCache

tracer = trace.get_tracer(__name__)


def _nodes(s: Services) -> dict[str, Any]:
    return {
        "plan": partial(orchestrator.plan, s),
        "route": orchestrator.route,
        "ingest": partial(ingest.ingest, s),
        "reconcile": partial(reconcile.reconcile, s),
        "dispatch": partial(orchestrator.dispatch, s),
        "retrieve": partial(retrieve.retrieve, s),
        "extract": partial(extract.extract, s),
        "validate": partial(validate.validate_drafts, s),
        "after_validate": partial(orchestrator.after_validate, s),
        "report": partial(report.report, s),
        "answer": partial(answer.answer, s),
    }


def _wire(nodes: dict[str, Any]) -> StateGraph[RunState]:
    g: StateGraph[RunState] = StateGraph(RunState)
    for name in ("plan", "ingest", "reconcile", "extract", "validate", "report", "answer"):
        g.add_node(name, nodes[name])
    g.add_node("retrieve", nodes["retrieve"], destinations=("extract",))
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", nodes["route"], ["ingest", "answer"])
    g.add_edge("answer", END)
    g.add_edge("ingest", "reconcile")
    g.add_conditional_edges("reconcile", nodes["dispatch"], ["retrieve", "validate"])
    g.add_edge("extract", "validate")
    g.add_conditional_edges("validate", nodes["after_validate"], ["retrieve", "report"])
    g.add_edge("report", END)
    return g


def build_graph(s: Services, checkpointer: SqliteSaver | None = None) -> Any:
    return _wire(_nodes(s)).compile(checkpointer=checkpointer)


def graph_mermaid() -> str:
    """The graph's topology as a Mermaid diagram, for the architecture document."""

    def noop(state: RunState) -> dict[str, Any]:
        return {}

    stub: dict[str, Any] = dict.fromkeys(
        ("plan", "ingest", "reconcile", "retrieve", "extract", "validate", "report", "answer"),
        noop,
    )
    stub["route"] = orchestrator.route
    stub["dispatch"] = stub["after_validate"] = lambda state: []
    mermaid: str = _wire(stub).compile().get_graph().draw_mermaid()
    return mermaid


def _invoke(
    s: Services, initial: RunState | None, run_id: str, checkpointer: SqliteSaver | None
) -> RunState:
    graph = build_graph(s, checkpointer)
    config: dict[str, Any] = {
        "configurable": {"thread_id": run_id},
        "max_concurrency": s.settings.llm_max_concurrency,
        "recursion_limit": 100,
    }
    final: RunState = graph.invoke(initial, config=config)
    return final


def run_extraction(
    s: Services,
    folder: Path | str,
    *,
    run_id: str | None = None,
    resume: bool = False,
    checkpoint_path: Path | None = None,
) -> tuple[BidResult, RunState]:
    """Run (or resume) extraction for one bid folder. A bare name means a folder under the
    data directory, or a bid that is already indexed; the folder's name is the bid id."""
    path = Path(folder)
    if not path.is_dir() and not path.is_absolute() and len(path.parts) == 1:
        path = s.settings.data_dir / path
    path = _relative_if_inside(path, Path.cwd())  # keeps local home paths out of traces
    run_id = run_id or new_run_id()
    conn = None
    checkpointer = None
    if checkpoint_path is not None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(checkpoint_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    try:
        attributes = {"rfp.run_id": run_id, "rfp.bid_id": path.name, "agent.mode": "extract"}
        with tracer.start_as_current_span("agent.run", attributes=attributes) as root:
            s.root_span = root
            initial: RunState | None = (
                None if resume else {"bid_id": path.name, "folder": str(path), "run_id": run_id}
            )
            final = _invoke(s, initial, run_id, checkpointer)
            result = BidResult.model_validate(final["final_output"])
            root.set_attribute("llm.cost_usd", result.usage.get("cost_usd", 0.0))
            log.info("extraction_done", bid_id=path.name, run_id=run_id, path=final["result_path"])
            return result, final
    finally:
        if conn is not None:
            conn.close()


def _relative_if_inside(path: Path, base: Path) -> Path:
    try:
        return path.resolve().relative_to(base.resolve())
    except ValueError:
        return path


def run_question(
    s: Services, question: str, *, bid_id: str | None = None, run_id: str | None = None
) -> tuple[QAResult, RunState]:
    """Answer one question through the same graph (plan routes it to the Q&A agent), unless
    the semantic cache holds the answer to an equivalent question over the same documents."""
    run_id = run_id or new_run_id()
    attributes = {"rfp.run_id": run_id, "agent.mode": "ask", "qa.question": question}
    with tracer.start_as_current_span("agent.run", attributes=attributes) as root:
        s.root_span = root
        cache, scope, fp = _qa_cache(s, bid_id)
        if cache is not None:
            with tracer.start_as_current_span("qa.cache") as span:
                hit = cache.lookup(question, scope, fp)
                span.set_attribute("qa.cache.hit", hit is not None)
                if hit is not None:
                    span.set_attribute("qa.cache.question", hit.question)
                    span.set_attribute("qa.cache.similarity", hit.similarity)
            if hit is not None:
                cache.close()
                result = hit.result.model_copy(
                    update={"question": question, "cached_from": hit.question,
                            "cache_similarity": hit.similarity, "usage": {}}
                )  # fmt: skip
                return result, RunState(question=question, final_output=result.model_dump())
        final = _invoke(s, {"question": question, "bid_id": bid_id, "run_id": run_id}, run_id, None)
        result = QAResult.model_validate(final["final_output"])
        if cache is not None:
            if result.error is None:
                cache.store(question, scope, fp, result)
            cache.close()
        return result, final


def _qa_cache(s: Services, bid_id: str | None) -> tuple["SemanticCache | None", str, str]:
    from rfp_intel.agents.qa_cache import SemanticCache, fingerprint

    if s.settings.qa_cache_threshold <= 0:
        return None, "", ""
    model = s.settings.qa_model or s.settings.extract_model
    scope = bid_id or "*"
    fp = fingerprint(s.settings.db_path, s.out_dir, [bid_id] if bid_id else [], model)
    cache = SemanticCache(
        s.settings.state_dir / "qa_cache.sqlite",
        s.engine.dense.embed_query,
        s.settings.qa_cache_threshold,
    )
    return cache, scope, fp
