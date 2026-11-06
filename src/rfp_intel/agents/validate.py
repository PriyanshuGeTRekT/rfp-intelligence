"""The validator: deterministic checks on each drafted field.

A draft passes only when:
1. cited: a found value has at least one quote;
2. quotes_verbatim: every quote is a substring of the passage it cites (case and whitespace
   ignored). A paraphrase is not evidence;
3. value_supported: the value can be read off the quotes, by field type: identifiers appear as
   tokens, dates parse to a date that a quote contains, every number in any value appears in a
   quote (no invented figures), list items and text are covered by the quotes' words;
4. not_found_justified: "not found" is allowed only after a thorough search found no
   labelled facts for the field.

A failed check produces a reason the extractor gets back on retry.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field

from rfp_intel.agents.evidence import EvidenceStore, FieldEvidence
from rfp_intel.agents.fields import FieldSpec
from rfp_intel.facts.datetimes import find_dates

_STOP = {
    "the", "and", "for", "with", "that", "this", "are", "must", "shall", "will", "from", "per",
    "any", "all", "not", "but", "may", "each", "into", "its", "their", "required", "require",
    "be", "of", "to", "in", "on", "or", "a", "an", "is", "by", "as", "at", "it", "no", "if",
}  # fmt: skip
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'/-]*")
_NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
COVERAGE_TEXT = 0.5  # share of a text value's content words that must appear in its quotes


class Quote(BaseModel):
    evidence_id: str
    text: str


class FieldDraft(BaseModel):
    """What an extraction agent proposes for one field."""

    field: str
    status: Literal["found", "not_found"]
    value: str | list[str] | None = None
    quotes: list[Quote] = Field(default_factory=list)
    notes: str | None = None


class Check(BaseModel):
    name: str
    passed: bool
    reason: str | None = None


class ValidationResult(BaseModel):
    field: str
    passed: bool
    checks: list[Check]

    @property
    def retry_reason(self) -> str | None:
        failed = [c.reason or c.name for c in self.checks if not c.passed]
        return "; ".join(failed) if failed else None


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.casefold()) if w not in _STOP and len(w) > 1}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


def _value_text(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    return " ; ".join(value) if isinstance(value, list) else value


def _supported(spec: FieldSpec, value: str | list[str] | None, quotes_text: str) -> str | None:
    """None when supported, else the reason."""
    text = _value_text(value)
    if not text.strip():
        return "value is empty"
    q = norm(quotes_text)
    missing_numbers = sorted(_numbers(text) - _numbers(quotes_text))
    if spec.type == "identifier":
        tokens = [t.strip("#").casefold() for t in re.split(r"[\s,;]+", text) if t.strip("#")]
        compact_q = q.replace("-", "")
        absent = [t for t in tokens if t not in q and t.replace("-", "") not in compact_q]
        return f"identifier {absent} does not appear in the quotes" if absent else None
    if spec.type == "datetime":
        value_dates = {m.value for m in find_dates(text)}
        if not value_dates:
            return "value has no recognisable date"
        quote_dates = {m.value for m in find_dates(quotes_text)}
        if not value_dates & quote_dates:
            return f"date {sorted(value_dates)} does not appear in the quotes"
        return None
    if missing_numbers:
        return f"numbers {missing_numbers} are not in the quotes"
    if spec.type == "summary":
        return None
    items = value if isinstance(value, list) else [text]
    quote_words = _words(quotes_text)
    for item in items:
        words = _words(item)
        if words and len(words & quote_words) / len(words) < COVERAGE_TEXT:
            return f"'{item[:60]}' is not supported by the quotes (too few of its words appear)"
    return None


def validate(
    draft: FieldDraft, spec: FieldSpec, store: EvidenceStore, evidence: FieldEvidence
) -> ValidationResult:
    checks: list[Check] = []
    if draft.status == "not_found":
        ok = evidence.coverage_met(spec)
        reason = None
        if not ok:
            reason = (
                f"'not found' needs a thorough search: {evidence.typed_fact_count} labelled facts "
                f"exist for this field; review them"
                if evidence.typed_fact_count
                else f"only {len(evidence.queries)} searches were run"
            )
        checks.append(Check(name="not_found_justified", passed=ok, reason=reason))
        return ValidationResult(field=draft.field, passed=ok, checks=checks)

    checks.append(
        Check(
            name="cited",
            passed=bool(draft.quotes),
            reason=None if draft.quotes else "no quotes given",
        )
    )
    bad_quotes: list[str] = []
    for quote in draft.quotes:
        item = store.get(quote.evidence_id)
        if item is None or norm(quote.text) not in norm(item.text):
            bad_quotes.append(quote.text[:60])
    checks.append(
        Check(
            name="quotes_verbatim",
            passed=not bad_quotes,
            reason=f"quotes not found verbatim in their passages: {bad_quotes}"
            if bad_quotes
            else None,
        )
    )
    reason = _supported(spec, draft.value, " \n".join(q.text for q in draft.quotes))
    checks.append(Check(name="value_supported", passed=reason is None, reason=reason))
    return ValidationResult(field=draft.field, passed=all(c.passed for c in checks), checks=checks)
