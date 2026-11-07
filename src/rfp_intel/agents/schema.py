"""The output contract: one JSON document per bid, in the brief's shape.

`fields` is keyed by the field names the brief uses ("Due Date", "Bid Bond Requirement", ...);
each entry also carries its snake_case `key`. Per field: value, status, sources
[{file, page, quote}], confidence with its tier, and notes. A field that is absent has value
null, status "not_found" and a note that starts "Not found in documents." and says what was
searched. A field the validator rejected after its retries, or that the model could not
produce, has status "failed". The top level carries the addendum changes that were applied and
a validation tally whose first three counts are the brief's passed / failed / not_found.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

FieldStatus = Literal["found", "not_found", "conflict", "failed"]
NOT_FOUND = "Not found in documents."


class Source(BaseModel):
    file: str
    page: int
    quote: str = Field(description="Verbatim text from the document that supports the value")
    doc_type: str | None = None
    addendum_number: int | None = None
    evidence_id: str | None = None


class FieldResult(BaseModel):
    key: str
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
    passed: int = 0  # found, or reconciled, and every check passed
    failed: int = 0  # rejected after the retries, or the model call failed
    not_found: int = 0  # absent after a search the validator accepted as thorough
    conflicts: int = 0  # sources disagree in a way no addendum explains
    fields: int = 0
    passed_first_time: int = 0
    passed_after_retry: int = 0
    retries: int = 0
    checks_failed: dict[str, int] = Field(default_factory=dict)
    consistency_issues: list[str] = Field(default_factory=list)


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
    models: dict[str, str] = Field(default_factory=dict)  # provider and models that made it
    errors: list[str] = Field(default_factory=list)

    def by_key(self, key: str) -> FieldResult:
        """A field by its snake_case key (`fields` is keyed by display name)."""
        return next(f for f in self.fields.values() if f.key == key)
