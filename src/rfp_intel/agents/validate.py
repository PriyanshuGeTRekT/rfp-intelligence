"""The validator: deterministic checks on each drafted field.

A draft passes only when:
1. cited: a found value has at least one quote;
2. quotes_verbatim: every quote reproduces text of the passage it cites: the same words in
   the same order, case and punctuation between words aside (`ground`). A paraphrase is not
   evidence. Grounded quotes are replaced by the passage's exact text before output;
3. value_supported: the value can be read off the quotes, by field type: identifiers appear as
   tokens, dates parse to a date that a quote contains, every number in any value appears in a
   quote (no invented figures), list items and text are covered by the quotes' words;
4. not_found_justified: "not found" is allowed only after a thorough search found no
   labelled facts for the field.

A draft that carries an `error` (the model call failed: timeout, invalid JSON after repair,
refusal) fails the `model_call` check, so the orchestrator retries it like any rejected field.

A failed check produces a reason the extractor gets back on retry.
"""

import re
from collections.abc import Sequence
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
    error: str | None = None  # set when no model answer was obtained


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


MIN_GROUNDED_CHARS = 4


def _alnum_view(text: str) -> tuple[str, list[int]]:
    """Lowercase letters and digits, with every other run of characters as one space, plus
    the index in `text` of each kept character."""
    chars: list[str] = []
    index: list[int] = []
    gap = True  # drop leading separators
    for i, ch in enumerate(text):
        low = ch.lower() if len(ch.lower()) == 1 else ch
        if low.isalnum():
            chars.append(low)
            index.append(i)
            gap = False
        elif not gap:
            chars.append(" ")
            index.append(i)
            gap = True
    if chars and chars[-1] == " ":
        chars.pop()
        index.pop()
    return "".join(chars), index


def ground(quote: str, passage: str) -> str | None:
    """The exact passage text a quote reproduces, or None.

    Models copy words faithfully but often not the punctuation around them: a table row
    "Solicitation Number | JA-207652" comes back as "Solicitation Number: JA-207652", or with
    markdown asterisks. The quote is accepted when its letters and digits appear in the
    passage in the same order with only separators between them, and it is then replaced by
    the passage's own text, so every citation in the output is verbatim source text.

    An elided quote ("The term shall be three (3) years ... renewed for two one-year
    periods") is accepted when every fragment grounds, in order, in the same passage; the
    result joins the exact fragments with " … "."""
    fragments = [f for f in _ELLIPSIS_RE.split(quote) if f.strip()]
    if len(fragments) > 1:
        view, index = _alnum_view(passage)
        parts: list[str] = []
        offset = 0
        for fragment in fragments:
            found = _find(fragment, passage, view, index, offset)
            if found is None:
                return None
            start, end, offset = found
            parts.append(passage[start:end])
        return " … ".join(parts)
    view, index = _alnum_view(passage)
    found = _find(quote, passage, view, index, 0)
    return passage[found[0] : found[1]] if found else None


_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3,}|…|\[\.\.\.\])\s*")


def _find(
    quote: str, passage: str, view: str, index: list[int], from_pos: int
) -> tuple[int, int, int] | None:
    """(start, end) of the quote in `passage`, and where in `view` the match ended."""
    wanted, _ = _alnum_view(quote)
    if len(wanted) < MIN_GROUNDED_CHARS:
        return None
    pattern = re.compile(rf"(?<![^\W_]){re.escape(wanted)}(?![^\W_])")  # whole words only
    match = pattern.search(view, from_pos)
    if match is None:
        return None
    pos = match.start()
    start, end = index[pos], index[pos + len(wanted) - 1] + 1
    # Keep punctuation the quote itself starts or ends with, when the passage has it too.
    q = quote.strip()
    if q and not q[-1].isalnum() and passage[end : end + 1] == q[-1]:
        end += 1
    if q and not q[0].isalnum() and start > 0 and passage[start - 1] == q[0]:
        start -= 1
    return start, end, match.end()


def ground_in(
    quote: str, cited: str, store: EvidenceStore, shown: Sequence[str]
) -> tuple[str, str] | None:
    """(evidence id, exact text) for a quote: in the passage it cites, or else in another
    passage the model was shown. Models copy the text faithfully but sometimes attach the id
    of the passage next to it; the quote is still verbatim source text, so the citation is
    pointed at the passage that holds it.

    A quote of a document's title often keeps the header's label (`document title "MERCURY
    AFFIDAVIT"`) or copies the whole passage header; it grounds as the title alone when the
    quote as given does not."""
    titled = _QUOTED_TITLE_RE.search(quote)
    variants = dict.fromkeys(
        [quote, _TITLE_LABEL_RE.sub("", quote, count=1), *([titled.group(1)] if titled else [])]
    )
    for evidence_id in dict.fromkeys([cited, *shown]):
        item = store.get(evidence_id)
        if item is None:
            continue
        for variant in variants:
            if (exact := ground(variant, item.quotable)) is not None:
                return evidence_id, exact
    return None


_TITLE_LABEL_RE = re.compile(r"^\W*document\s+title\b\W*", re.IGNORECASE)
_QUOTED_TITLE_RE = re.compile(r'document\s+title\s+"([^"]+)"', re.IGNORECASE)


def ground_draft(
    draft: "FieldDraft", store: EvidenceStore, shown: Sequence[str] = ()
) -> "FieldDraft":
    """The draft with each quote replaced by the exact text it reproduces, and pointed at the
    passage that holds it, where one does (`shown`: the passages the model was given)."""
    quotes = []
    for q in draft.quotes:
        found = ground_in(q.text, q.evidence_id, store, shown)
        quotes.append(q if found is None else Quote(evidence_id=found[0], text=found[1]))
    return draft.model_copy(update={"quotes": quotes})


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.casefold()) if w not in _STOP and len(w) > 1}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text)}


def _value_text(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    return " ; ".join(value) if isinstance(value, list) else value


# A list item labelled with its product or tier, as the field definitions ask for when several
# are specified: "Dell Latitude 5550 - 16 GB DDR5", "Tier 3: Intel i5".
_LABEL_SEPARATORS = (" - ", " " + chr(0x2013) + " ", " " + chr(0x2014) + " ", ": ")  # -, en, em
MAX_LABEL_CHARS = 60


def _split_label(item: str) -> tuple[str, str] | None:
    """(label, rest) of a labelled list item, or None. The label is the text before the first
    separator, if that comes within MAX_LABEL_CHARS."""
    cuts = [(i, sep) for sep in _LABEL_SEPARATORS if 0 < (i := item.find(sep)) <= MAX_LABEL_CHARS]
    if not cuts:
        return None
    i, sep = min(cuts)
    return item[:i], item[i + len(sep) :]


def _unquoted_numbers(value: str | list[str] | None, quotes_text: str, shown_text: str) -> set[str]:
    """Numbers in the value that its quotes do not contain. A list item's product or tier label
    is a name, not a claim, and is often not inside the quoted spec: its numbers ("5550" in a
    model name) need only appear in the passages the model was shown. Every other number must
    be in the quotes."""
    quoted = _numbers(quotes_text)
    if not isinstance(value, list):
        return _numbers(_value_text(value)) - quoted
    missing: set[str] = set()
    for item in value:
        labelled = _split_label(item)
        if labelled is None:
            missing |= _numbers(item) - quoted
            continue
        label, rest = labelled
        missing |= _numbers(rest) - quoted
        missing |= _numbers(label) - quoted - _numbers(shown_text)
    return missing


def _supported(
    spec: FieldSpec, value: str | list[str] | None, quotes_text: str, shown_text: str = ""
) -> str | None:
    """None when supported, else the reason. `shown_text`: the passages the model read."""
    text = _value_text(value)
    if not text.strip():
        return "value is empty"
    q = norm(quotes_text)
    missing_numbers = sorted(_unquoted_numbers(value, quotes_text, shown_text))
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
    # OCR can set words without the space between them ("RFP2025-003ComputerEquipment"); a
    # longer value word found inside the quotes' run-together letters still counts.
    run_together = re.sub(r"[^0-9a-z]", "", quotes_text.casefold())
    for item in items:
        words = _words(item)
        present = {w for w in words if w in quote_words or (len(w) >= 5 and w in run_together)}
        if words and len(present) / len(words) < COVERAGE_TEXT:
            return f"'{item[:60]}' is not supported by the quotes (too few of its words appear)"
    return None


def validate(
    draft: FieldDraft, spec: FieldSpec, store: EvidenceStore, evidence: FieldEvidence
) -> ValidationResult:
    checks: list[Check] = []
    if draft.error:
        failure = f"the model call failed: {draft.error}"
        checks.append(Check(name="model_call", passed=False, reason=failure))
        return ValidationResult(field=draft.field, passed=False, checks=checks)
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
        if item is None or ground(quote.text, item.quotable) is None:
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
    shown = [item.quotable for e in evidence.evidence_ids if (item := store.get(e)) is not None]
    reason = _supported(
        spec, draft.value, " \n".join(q.text for q in draft.quotes), " \n".join(shown)
    )
    checks.append(Check(name="value_supported", passed=reason is None, reason=reason))
    return ValidationResult(field=draft.field, passed=all(c.passed for c in checks), checks=checks)
