"""Typed facts extracted from documents at ingest time."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FactKind(StrEnum):
    DATETIME = "datetime"
    DURATION = "duration"
    MONEY = "money"
    PERCENT = "percent"
    IDENTIFIER = "identifier"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    QUANTITY = "quantity"


class Fact(BaseModel):
    """One normalized value with exact provenance.

    `raw` is a verbatim substring of the block text at [start, end), so a fact can always be
    shown and re-checked against its source. `context` is the label-and-value or sentence the
    value sits in; `fact_types` are topic labels (deadline, delivery, ...) derived from it.
    """

    fact_id: str
    bid_id: str
    doc_id: str
    file_name: str
    doc_type: str
    addendum_number: int | None = None
    doc_date: str | None = None
    page: int
    block_index: int
    section: str | None = None
    kind: FactKind
    fact_types: list[str] = Field(default_factory=list)
    raw: str
    start: int
    end: int
    value: dict[str, Any]
    context: str
