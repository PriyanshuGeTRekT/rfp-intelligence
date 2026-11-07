"""Request and response models for the REST API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from rfp_intel.agents.schema import DocumentInfo, ValidationTally


class IndexRequest(BaseModel):
    path: str = Field(description="Bid folder, relative to the data directory")


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    bid_id: str | None = None


class Health(BaseModel):
    status: str
    version: str
    llm_provider: str
    extract_model: str
    reranker: bool | None  # None until the search stack is first used


class SearchConfigInfo(BaseModel):
    name: str
    description: str
    default: bool


class ResultSummary(BaseModel):
    run_id: str
    generated_at: str
    validation: ValidationTally
    due_date: str | None = None
    title: str | None = None
    cost_usd: float = 0.0


class BidSummary(BaseModel):
    bid_id: str
    indexed: bool
    documents: int
    doc_types: dict[str, int] = Field(default_factory=dict)
    indexed_at: str | None = None
    result: ResultSummary | None = None


class BidDetail(BidSummary):
    files: list[DocumentInfo] = Field(default_factory=list)


JobStatus = Literal["queued", "running", "succeeded", "failed"]


class Job(BaseModel):
    job_id: str
    kind: Literal["extract"] = "extract"
    bid_id: str
    run_id: str
    status: JobStatus = "queued"
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    validation: ValidationTally | None = None


class TraceSpan(BaseModel):
    span_id: str | None
    parent_span_id: str | None
    name: str
    start: str | None
    duration_ms: float | None
    status: str
    attributes: dict[str, Any] = Field(default_factory=dict)
