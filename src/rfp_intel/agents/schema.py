"""The output contract: one JSON document per bid.

Per field: value, status, sources [{file, page, quote}], confidence with its tier, and notes.
A field that is absent has value null, status "not_found" and a note saying what was searched.
The top level carries the addendum changes that were applied and a validation tally.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["found", "not_found", "conflict"]


class Source(BaseModel):
    file: str
    page: int
    quote: str = Field(description="Verbatim text from the document that supports the value")
    doc_type: str | None = None
    addendum_number: int | None = None
    evidence_id: str | None = None


class FieldResult(BaseModel):
    value: str | list[str] | None
    status: FieldStatus
    sources: list[Source] = Field(default_factory=list)
    confidence: float
    tier: str
    normalized: dict[str, Any] | None = None
    notes: str | None = None


class AddendumChange(BaseModel):
    field: str
    operation: Literal["replace", "amend", "confirm", "clarify", "add_requirement"]
    addendum_number: int | None
    doc_date: date | None
    old_value: str | None
    new_value: str | None
    source: Source


class ValidationTally(BaseModel):
    fields: int
    passed_first_time: int
    passed_after_retry: int
    failed: int
    retries: int
    checks_failed: dict[str, int] = Field(default_factory=dict)


class DocumentInfo(BaseModel):
    file: str
    doc_type: str
    addendum_number: int | None = None
    doc_date: date | None = None
    pages: int


class BidResult(BaseModel):
    bid_id: str
    run_id: str
    generated_at: str
    documents: list[DocumentInfo]
    fields: dict[str, FieldResult]
    addendum_changes: list[AddendumChange] = Field(default_factory=list)
    validation: ValidationTally
    usage: dict[str, Any] = Field(default_factory=dict)
