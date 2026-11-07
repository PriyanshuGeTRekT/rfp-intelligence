"""Structured outputs the model returns. Every agent-to-agent message is one of these.

They are deliberately flat (no unions of str and list) so they translate to a strict JSON
schema; `to_draft` converts to the validator's `FieldDraft`.
"""

from typing import Literal

from pydantic import BaseModel, Field

from rfp_intel.agents.validate import FieldDraft, Quote


class QuoteOut(BaseModel):
    evidence_id: str = Field(description="The [id] of the passage the quote comes from")
    text: str = Field(description="Exact text copied from that passage, unchanged")


class DraftOut(BaseModel):
    field: str = Field(description="The field key exactly as listed")
    status: Literal["found", "not_found"]
    value: str | None = Field(default=None, description="The value, for single-valued fields")
    items: list[str] | None = Field(default=None, description="The values, for list fields")
    quotes: list[QuoteOut] = Field(default_factory=list)
    notes: str | None = Field(
        default=None, description="Caveats, distractors you rejected, or why the field is absent"
    )

    def to_draft(self, list_field: bool) -> FieldDraft:
        value: str | list[str] | None
        if list_field:
            value = self.items if self.items is not None else ([self.value] if self.value else None)
        else:
            value = (
                self.value
                if self.value is not None
                else (", ".join(self.items) if self.items else None)
            )
        return FieldDraft(
            field=self.field,
            status=self.status,
            value=value,
            quotes=[Quote(evidence_id=q.evidence_id, text=q.text) for q in self.quotes],
            notes=self.notes,
        )


class GroupDraftOut(BaseModel):
    drafts: list[DraftOut]


class EventOut(BaseModel):
    field: str = Field(description="The field key this change affects")
    operation: Literal["replace", "amend", "confirm", "clarify", "add_requirement"]
    new_text: str | None = Field(
        default=None, description="The new or added value, in the addendum's words"
    )
    quote: str = Field(description="Exact text from the addendum that states the change")
    page: int


class EventsOut(BaseModel):
    events: list[EventOut]


class SummaryOut(BaseModel):
    summary: str = Field(description="Three to six sentences")


class CitationOut(BaseModel):
    evidence_id: str
    quote: str = Field(description="Exact text copied from the passage")


class StatementOut(BaseModel):
    text: str = Field(description="One sentence of the answer")
    citations: list[CitationOut] = Field(
        default_factory=list, description="Quotes from the passages that state this sentence"
    )


class AnswerOut(BaseModel):
    found: bool = Field(description="False when the passages do not answer the question")
    statements: list[StatementOut] = Field(
        default_factory=list,
        description="The answer, one sentence per statement, each with its own citations; "
        "empty when found is false",
    )
    note: str | None = Field(
        default=None, description="When found is false: what the documents do or do not say"
    )


class QueriesOut(BaseModel):
    queries: list[str] = Field(description="Two to four short search queries")
