"""The orchestrator / planner: it receives the goal (extract a bid, or answer a question),
writes the execution plan, routes to the right agents, and decides when the job is done:
after validation it either sends rejected fields back for another retrieval and extraction
round (up to the retry limit) or moves on to the report.
"""

from collections.abc import Sequence
from typing import Any

from langgraph.types import Send

from rfp_intel.agents.fields import FieldCatalog
from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import ExtractionTask, PlanStep, RunState


def extraction_tasks(
    catalog: FieldCatalog, resolved: dict[str, dict[str, Any]], batch_size: int
) -> list[ExtractionTask]:
    """One task per batch of fields in each group. Dates the reconciler resolved are left out,
    except fields marked `enrich`, which are extracted with the resolved value as a hint."""
    tasks: list[ExtractionTask] = []
    for group in catalog.extraction_groups:
        fields = [f for f in catalog.group(group) if f.key not in resolved or f.enrich]
        for i in range(0, len(fields), batch_size):
            batch = fields[i : i + batch_size]
            name = group if i == 0 else f"{group}/{i // batch_size + 1}"
            tasks.append(
                ExtractionTask(
                    batch=name,
                    fields=[f.key for f in batch],
                    hints=_hints([f.key for f in batch], resolved),
                )
            )
    return tasks


def _hints(keys: Sequence[str], resolved: dict[str, dict[str, Any]]) -> dict[str, str]:
    return {
        k: str(resolved[k]["value"]) for k in keys if k in resolved and resolved[k].get("value")
    }


def _steps(state: RunState, tasks: list[ExtractionTask]) -> list[PlanStep]:
    if state.get("question"):
        scope = state.get("bid_id") or "all indexed bids"
        return [
            PlanStep(agent="answer", task=f"retrieve evidence in {scope} and answer with citations")
        ]
    return [
        PlanStep(agent="ingest", task=f"index {state.get('folder')} (new or changed files only)"),
        PlanStep(agent="reconcile", task="read addenda into change events; resolve date fields"),
        *(
            PlanStep(agent="retrieve+extract", task=f"{t.batch}: {', '.join(t.fields)}")
            for t in tasks
        ),
        PlanStep(agent="validate", task="check every draft; retry rejected fields with reasons"),
        PlanStep(agent="report", task="cross-field checks, summary, JSON record"),
    ]


def plan(s: Services, state: RunState) -> dict[str, Any]:
    mode = "ask" if state.get("question") else "extract"
    with s.span("agent.plan") as span:
        tasks = (
            extraction_tasks(s.catalog, {}, s.settings.extract_batch_size)
            if mode == "extract"
            else []
        )
        steps = _steps(state, tasks)
        span.set_attribute("agent.mode", mode)
        span.set_attribute(
            "agent.input", io_attribute({k: state.get(k) for k in ("bid_id", "folder", "question")})
        )
        span.set_attribute("agent.output", io_attribute([st.model_dump() for st in steps]))
    return {
        "mode": mode,
        "plan": [st.model_dump() for st in steps],
        "log": [f"plan ({mode}): " + "; ".join(f"{st.agent}: {st.task}" for st in steps)],
    }


def route(state: RunState) -> str:
    return "answer" if state.get("mode") == "ask" else "ingest"


def dispatch(s: Services, state: RunState) -> list[Send] | str:
    """Fan out: one retrieval-and-extraction branch per batch, all in parallel."""
    tasks = extraction_tasks(s.catalog, state.get("resolved", {}), s.settings.extract_batch_size)
    if not tasks:
        return "validate"
    return [Send("retrieve", {"bid_id": state["bid_id"], "task": t.model_dump()}) for t in tasks]


def after_validate(s: Services, state: RunState) -> list[Send] | str:
    """Rejected fields go back to retrieval with the validator's reason, one branch each."""
    retries = state.get("retries", [])
    if not retries:
        return "report"
    resolved = state.get("resolved", {})
    return [
        Send(
            "retrieve",
            {
                "bid_id": state["bid_id"],
                "task": ExtractionTask(
                    batch=f"retry:{r['field']}",
                    fields=[r["field"]],
                    attempt=r["attempt"],
                    reasons={r["field"]: r["reason"]},
                    hints=_hints([r["field"]], resolved),
                ).model_dump(),
            },
        )
        for r in retries
    ]
