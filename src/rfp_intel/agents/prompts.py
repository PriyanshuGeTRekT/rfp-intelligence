"""Prompts. The system prompts are constant per task so the API can cache them; everything
that varies (passages, candidates, field list) goes in the user turn."""

from collections.abc import Sequence

from rfp_intel.agents.evidence import EvidenceItem, FactCandidate
from rfp_intel.agents.fields import FieldSpec

EXTRACT_SYSTEM = """You extract fields from public procurement documents (RFPs, addenda, \
purchase-order solicitations, portal pages, quotes, affidavits) for a bid-tracking system.

Rules:
1. Use only the passages provided. Each passage starts with an [id] header giving its file, \
pages and document type. Never use outside knowledge about the agency or the products.
2. Every found value needs at least one quote: exact text copied from a passage, with that \
passage's id. Do not paraphrase inside a quote. Short quotes that contain the value are best.
3. If the passages do not state a field, return status "not_found" with a note. Do not guess \
and do not infer a value from a similar field (a questions deadline is not the due date; a \
vendor's credit terms are not the agency's payment terms; a bond-funded program is not a bid \
bond).
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
touch."""

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
2. Cite every fact in the answer: each citation is the passage id and an exact quote copied \
from it. Quotes must be verbatim.
3. Later addenda override earlier documents; say so when an addendum changed something. \
Portal pages corroborate but do not override documents.
4. Be concise and specific: dates with time and zone, amounts, identifiers as written. When a \
question compares bids, answer per bid."""


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


def field_block(spec: FieldSpec) -> str:
    kind = {
        "list": "list of items",
        "datetime": "date and time with zone",
        "identifier": "identifier",
    }.get(spec.type, "text")
    return f"- {spec.key} ({spec.name}; {kind}): {spec.description}"


def extraction_user(
    fields: Sequence[FieldSpec],
    passages: dict[str, list[EvidenceItem]],
    candidates: dict[str, list[FactCandidate]],
    retry_reasons: dict[str, str] | None = None,
) -> str:
    out = ["Fields to extract:", *[field_block(f) for f in fields], ""]
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


def qa_user(question: str, items: Sequence[EvidenceItem]) -> str:
    return f"Question: {question}\n\nPassages:\n\n{passages_block(items, with_bid=True)}"
