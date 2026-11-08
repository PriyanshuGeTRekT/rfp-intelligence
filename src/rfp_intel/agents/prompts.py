"""Prompts. The system prompts are constant per task so the API can cache them; everything
that varies (passages, candidates, field list) goes in the user turn.

Design, in short: each prompt states the task, the rules that make the output checkable
(quote verbatim, cite the passage id, say "not found" rather than guess), and the traps seen
in procurement documents (a questions deadline is not the due date). Inputs are labelled
blocks with [id] headers so citations can be checked by code. Evidence is fitted to a token
budget, so a small context window or a free-tier quota still works.
"""

from collections.abc import Sequence

from rfp_intel.agents.evidence import EvidenceItem, FactCandidate
from rfp_intel.agents.fields import FieldSpec
from rfp_intel.agents.llm import estimate_tokens

EXTRACT_SYSTEM = """You extract fields from public procurement documents (RFPs, addenda, \
purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking system.

Rules:
1. Use only the passages provided. Each passage starts with an [id] header giving its file, \
pages, document type and the document's title; a quote may come from that title. Never use \
outside knowledge about the agency or the products.
2. Every found value needs at least one quote: exact text copied from a passage, with that \
passage's id. Do not paraphrase inside a quote. Short quotes that contain the value are best.
3. If the passages do not state a field, return status "not_found" with a note. Do not guess \
and do not infer a value from a similar field (a questions deadline is not the due date; a \
vendor's credit terms are not the agency's payment terms; a bond-funded program is not a bid \
bond; terms printed in a vendor's own quote or product sheet are not the solicitation's \
requirements).
4. Later addenda override earlier documents. Portal pages corroborate documents but do not \
override them. If sources disagree, give the controlling value and explain the difference in \
notes.
5. Candidate facts, when given, are values parsed from the documents with their source \
sentence. Prefer choosing among them to re-reading raw text, but check the sentence fits the \
field.
6. Values are concise and faithful: dates with their time and zone as written, identifiers \
exactly as written, lists as separate items. Do not add commentary to values; use notes."""

RETRY_NOTE = """The previous attempt for field "{field}" was rejected by the validator: \
{reason}. Fix exactly that: quote text that appears verbatim in a passage, make the value follow \
from the quotes, or return not_found with a note if the passages do not support a value."""

EVENTS_SYSTEM = """You read one addendum (or amendment) to a procurement solicitation and list \
the changes it makes, as structured events.

For each statement that changes, adds to, confirms or clarifies one of the listed fields, \
return an event with:
- field: the field key it affects;
- operation: "replace" when a value is superseded (a new due date), "amend" when part of a \
value changes, "add_requirement" when something new must be submitted or done (a signed \
addendum acknowledgement, a new form), "confirm" when the addendum restates an existing value \
unchanged, "clarify" when it explains a requirement without changing the value;
- new_text: the new or added value in the addendum's own words (omit for clarify and confirm);
- quote: the exact sentence from the addendum, copied unchanged;
- page: the page the quote is on.

Only list events supported by an exact quote. Questions and answers count: an answer that \
sets or changes a requirement is an event. Do not list events for fields the addendum does not \
touch. Changes to dates (the due date, the questions deadline, the pre-bid meeting) are recorded \
separately: do not list them under any field."""

REWRITE_SYSTEM = """You write search queries for a hybrid (keyword and semantic) search engine \
over procurement documents. A field could not be extracted from the passages found so far; \
the reason is given. Write two to four short, different queries (three to eight words each) \
that would find the passage stating this field: use the words such documents use (synonyms, \
section names, form names), not the same words again. Return only the queries."""

SUMMARY_SYSTEM = """You write a short summary of a procurement bid for a sales team, from the \
extracted fields given. Three to six plain sentences: who is buying what (with quantities when \
known), the final due date after addenda, how to submit, the main requirements (warranty, \
delivery, documentation), and anything notable such as eligibility limits or missing \
information. Use only the given field values; every number and date you write must appear in \
them. No bullet points, no headings."""

QA_SYSTEM = """You answer questions about procurement bids using only the passages provided. \
Each passage starts with an [id] header giving its bid, file, pages and document type.

Rules:
1. Answer from the passages alone. If they do not contain the answer, set found to false and \
say that the documents do not state it. Never guess.
2. Answer as statements, one sentence each, and give every statement its own citations: the \
passage id and an exact quote copied from it that states what the sentence says. Quotes must \
be verbatim. A statement whose citations do not check out is removed from the answer.
3. Later addenda override earlier documents; say so when an addendum changed something. \
Portal pages corroborate but do not override documents.
4. Be concise and specific: dates with time and zone, amounts, identifiers as written. When a \
question compares bids, answer per bid.
5. A "Reconciled values" block, when present, lists values the system extracted with every \
addendum applied. Use it to tell which statement is final (for example, which due date \
stands), and still cite the passages that state the facts.
6. State requirements only as the passages state them. A reference to requirements "noted \
elsewhere" or "if applicable" is not itself a requirement: say what the passage says, not \
more.
7. When the passages come from more than one bid, name the bid in every statement ("In Bid3, \
..."), and never present one bid's facts as the answer for the bids as a whole. If only some \
bids state the answer, say which do and that the others' documents do not."""


def passages_block(items: Sequence[EvidenceItem], *, with_bid: bool = False) -> str:
    parts = []
    for item in items:
        section = f"\nSection: {item.section}" if item.section else ""
        parts.append(f"{item.header(with_bid=with_bid)}{section}\n{item.text}")
    return "\n\n---\n\n".join(parts)


def candidates_block(candidates: Sequence[FactCandidate]) -> str:
    lines = []
    for c in candidates:
        v = c.value
        shown = (
            v.get("utc")
            or v.get("local")
            or v.get("date")
            or v.get("id")
            or v.get("email")
            or v.get("phone")
            or v.get("amount")
            or v.get("qty")
            or v.get("url")
            or ""
        )
        where = f"{c.file} p{c.page}, {c.doc_type}" + (
            f" {c.addendum_number}" if c.addendum_number else ""
        )
        lines.append(f'- {c.kind} "{c.raw}" = {shown} ({where}): "{c.context[:200]}"')
    return "\n".join(lines)


def field_block(spec: FieldSpec, hint: str | None = None) -> str:
    kind = {
        "list": "list of items",
        "datetime": "date and time with zone",
        "identifier": "identifier",
    }.get(spec.type, "text")
    line = f"- {spec.key} ({spec.name}; {kind}): {spec.description}"
    if hint:
        line += (
            f" Already resolved from the documents and addenda: {hint}. Keep that date and "
            "time; add what the passages say about place and attendance."
        )
    return line


MIN_PASSAGE_TOKENS = 60  # passage text cut shorter than this is too little to quote from


def _overhead(item: EvidenceItem) -> int:
    """Tokens a passage costs besides its text: the [id] header, section line, separator."""
    return estimate_tokens(item.header(with_bid=True)) + estimate_tokens(item.section) + 5


def passage_tokens(item: EvidenceItem) -> int:
    """What a passage costs in a prompt (a high estimate)."""
    return estimate_tokens(item.text) + _overhead(item)


def _trim(item: EvidenceItem, tokens: int) -> EvidenceItem:
    """The start of a passage, cut at a word boundary so it costs at most `tokens`."""
    chars = int((tokens - _overhead(item) - 3) * 3.5)  # 3 tokens of slack for the marker
    head = item.text[:chars].rsplit(maxsplit=1)[0]
    return item.model_copy(update={"text": f"{head} […]"})


def fit_passages(
    passages: dict[str, list[EvidenceItem]], budget_tokens: int
) -> dict[str, list[EvidenceItem]]:
    """Keep each field's best passages within a token budget.

    First every field gets its best passage, cut short when it would not fit whole, so no
    field reaches the model with nothing to read: each field is guaranteed an equal share of
    the budget for it. Then the rest are taken in turn (second best of every field, then third,
    ...) while the budget lasts. A passage shared by several fields is paid for once."""
    kept: dict[str, list[EvidenceItem]] = {key: [] for key in passages}
    chosen: dict[str, EvidenceItem] = {}  # evidence id -> the version that goes in the prompt
    used = 0

    fields = [key for key, items in passages.items() if items]
    share = budget_tokens // max(1, len(fields))
    for n, key in enumerate(fields, start=1):
        best = passages[key][0]
        if best.evidence_id not in chosen:
            room = budget_tokens - used - (len(fields) - n) * share  # later fields keep a share
            if passage_tokens(best) > room:
                if room - _overhead(best) < MIN_PASSAGE_TOKENS:
                    continue
                best = _trim(best, room)
            used += passage_tokens(best)
            chosen[best.evidence_id] = best
        kept[key].append(chosen[best.evidence_id])

    depth = max((len(items) for items in passages.values()), default=0)
    for i in range(1, depth):
        for key, items in passages.items():
            if i >= len(items):
                continue
            item = items[i]
            if item.evidence_id not in chosen:
                if used + passage_tokens(item) > budget_tokens:
                    continue
                used += passage_tokens(item)
                chosen[item.evidence_id] = item
            kept[key].append(chosen[item.evidence_id])
    return kept


def rewrite_user(spec: FieldSpec, reason: str, tried: Sequence[str]) -> str:
    return (
        f"Field: {spec.name}: {spec.description}\n"
        f"Why the last attempt failed: {reason}\n"
        f"Queries already tried: {'; '.join(tried)}"
    )


def extraction_user(
    fields: Sequence[FieldSpec],
    passages: dict[str, list[EvidenceItem]],
    candidates: dict[str, list[FactCandidate]],
    retry_reasons: dict[str, str] | None = None,
    hints: dict[str, str] | None = None,
) -> str:
    hints = hints or {}
    out = ["Fields to extract:", *[field_block(f, hints.get(f.key)) for f in fields], ""]
    if retry_reasons:
        out += [RETRY_NOTE.format(field=k, reason=v) for k, v in retry_reasons.items()] + [""]
    seen: dict[str, EvidenceItem] = {}
    for spec in fields:
        cands = candidates.get(spec.key, [])
        if cands:
            out += [f"Candidate facts for {spec.key}:", candidates_block(cands), ""]
        for item in passages.get(spec.key, []):
            seen.setdefault(item.evidence_id, item)
    out += ["Passages:", "", passages_block(list(seen.values()))]
    out += ["", "Return one draft per field listed, in the given order."]
    return "\n".join(out)


def events_user(fields: Sequence[FieldSpec], items: Sequence[EvidenceItem]) -> str:
    return "\n".join(
        [
            "Fields that an addendum may change:",
            *[field_block(f) for f in fields],
            "",
            "Addendum, in order:",
            "",
            passages_block(items),
        ]
    )


def summary_user(values: dict[str, str]) -> str:
    return "Extracted fields:\n" + "\n".join(f"- {k}: {v}" for k, v in values.items())


def qa_user(question: str, items: Sequence[EvidenceItem], reconciled: Sequence[str] = ()) -> str:
    known = ""
    if reconciled:
        known = "Reconciled values:\n" + "\n".join(f"- {r}" for r in reconciled) + "\n\n"
    return f"Question: {question}\n\n{known}Passages:\n\n{passages_block(items, with_bid=True)}"
