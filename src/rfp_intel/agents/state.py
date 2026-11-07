"""The shared state of the agent graph, and the messages agents send each other.

`RunState` holds the plan, the documents, the change events, retrieved evidence (ids and the
record of what was searched; the text lives in an `EvidenceStore`), draft fields, validation
results and the final output. Parallel branches write to dict keys through a merge reducer,
so no branch overwrites another's fields.

Messages between agents are Pydantic models: a `PlanStep` per sub-task in the plan, and an
`ExtractionTask` sent to the retrieval agent and passed on to the extraction agent.
"""

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

Mode = Literal["extract", "ask"]


def merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {**a, **b}


def add_usage(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    out = dict(a)
    for k, v in b.items():
        out[k] = round(out.get(k, 0) + v, 6)
    return out


class PlanStep(BaseModel):
    agent: str
    task: str


class ExtractionTask(BaseModel):
    """One batch of fields to retrieve evidence for and extract in one model call."""

    batch: str  # e.g. "identity_dates" or "identity_dates/2", or "retry:due_date"
    fields: list[str]
    attempt: int = 1
    reasons: dict[str, str] = Field(default_factory=dict)  # validator feedback, on retries
    hints: dict[str, str] = Field(default_factory=dict)  # resolved values the model builds on


class RunState(TypedDict, total=False):
    mode: Mode
    bid_id: str | None
    folder: str
    run_id: str
    question: str
    plan: list[dict[str, Any]]
    documents: list[dict[str, Any]]
    events: list[dict[str, Any]]
    resolved: Annotated[dict[str, dict[str, Any]], merge]
    evidence: Annotated[dict[str, dict[str, Any]], merge]
    drafts: Annotated[dict[str, dict[str, Any]], merge]
    validations: Annotated[dict[str, dict[str, Any]], merge]
    attempts: Annotated[dict[str, int], merge]
    retries: list[dict[str, Any]]
    usage: Annotated[dict[str, float], add_usage]
    log: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    result_path: str
    final_output: dict[str, Any]
    # Send payload of the retrieval and extraction branches
    task: dict[str, Any]
