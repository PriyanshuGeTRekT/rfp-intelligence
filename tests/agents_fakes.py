"""A scripted model that behaves like a careful extractor: it reads the prompt, finds the
passage that contains each scripted quote and cites that passage's id. One field fails on
its first attempt on purpose, to exercise the validator's retry loop."""

import re
from dataclasses import dataclass, field

from pydantic import BaseModel

from rfp_intel.agents.llm import ScriptedLLM
from rfp_intel.agents.outputs import (
    AnswerOut,
    CitationOut,
    DraftOut,
    EventOut,
    EventsOut,
    GroupDraftOut,
    QuoteOut,
    SummaryOut,
)
from rfp_intel.agents.validate import norm

ADDENDUM = """# ADDENDUM No. 2

The purpose of this addendum is to extend the due date of this RFQ.

The new due date for this RFQ will be July 16, 2024 at 2:00 PM CST.

Bidders must submit a signed copy of this addendum with their quote.
"""

# field -> (value, quote). Quotes are exact text from the sample documents.
SCRIPT: dict[str, tuple[str | list[str], str | list[str]]] = {
    "bid_number": ("RFQ-117", "Solicitation Number: RFQ-117"),
    "title": ("Student Laptops", "RFQ-117 - Student Laptops"),
    "bid_bond_requirement": ("Not required", "Bid Bond: Not required"),
    "delivery_date": ("Within 45 days of award", "within 45 days of award."),
    "product": ("Laptop, 30", "Laptop | 30"),
    "part_no": (["379-BFNZ", "WD22TB4"], ["Laptop 15 inch | 379-BFNZ", "Dock | WD22TB4"]),
    "installation": ("Deliver to the central warehouse", "Deliver to the central warehouse."),
    "contact_info": ("buyer@example.gov", "buyer@example.gov"),
}
BAD_FIRST_ATTEMPT = {"delivery_date": "equipment delivered inside 45 days"}  # a paraphrase


def passages(user: str) -> dict[str, str]:
    body = user.split("Passages:\n\n", 1)[1] if "Passages:\n\n" in user else ""
    out: dict[str, str] = {}
    for block in body.split("\n\n---\n\n"):
        m = re.match(r"\[(\w+)\]", block)
        if m:
            out[m.group(1)] = block
    return out


def requested_fields(user: str) -> list[str]:
    return re.findall(r"^- (\w+) \(", user, re.M)


def _find(quote: str, blocks: dict[str, str]) -> str | None:
    return next((eid for eid, text in blocks.items() if norm(quote) in norm(text)), None)


@dataclass
class Extractor:
    attempts: dict[str, int] = field(default_factory=dict)

    def __call__(self, system: str, user: str) -> BaseModel:
        blocks = passages(user)
        drafts: list[DraftOut] = []
        for key in requested_fields(user):
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if key not in SCRIPT:
                drafts.append(
                    DraftOut(field=key, status="not_found", notes="not stated in the passages")
                )
                continue
            value, quotes = SCRIPT[key]
            quote_list = quotes if isinstance(quotes, list) else [quotes]
            if key in BAD_FIRST_ATTEMPT and self.attempts[key] == 1:
                quote_list = [BAD_FIRST_ATTEMPT[key]]
            found: list[QuoteOut] = []
            for q in quote_list:
                eid = _find(q, blocks)
                if eid is None and key in BAD_FIRST_ATTEMPT and self.attempts[key] == 1:
                    eid = next(iter(blocks), "none")  # cite something, with a paraphrased quote
                if eid is not None:
                    found.append(QuoteOut(evidence_id=eid, text=q))
            if not found:
                drafts.append(
                    DraftOut(field=key, status="not_found", notes="quote not in passages")
                )
            elif isinstance(value, list):
                drafts.append(DraftOut(field=key, status="found", items=value, quotes=found))
            else:
                drafts.append(DraftOut(field=key, status="found", value=value, quotes=found))
        return GroupDraftOut(drafts=drafts)


def events(system: str, user: str) -> BaseModel:
    return EventsOut(
        events=[
            EventOut(
                field="additional_documentation",
                operation="add_requirement",
                new_text="A signed copy of Addendum 2",
                quote="Bidders must submit a signed copy of this addendum with their quote.",
                page=1,
            ),
            EventOut(  # not verbatim: must be dropped
                field="installation",
                operation="clarify",
                new_text="x",
                quote="installation is handled by the vendor",
                page=1,
            ),
        ]
    )


def summary(system: str, user: str) -> BaseModel:
    return SummaryOut(
        summary="Riverside County is buying 30 laptops. Quotes are due July 16, 2024 after "
        "Addendum 2 moved the date. Delivery is within 45 days of award. No bid bond is required."
    )


def make_llm() -> ScriptedLLM:
    return ScriptedLLM({"GroupDraftOut": Extractor(), "EventsOut": events, "SummaryOut": summary})


def answering(verbatim: bool) -> ScriptedLLM:
    def respond(system: str, user: str) -> BaseModel:
        blocks = passages(user)
        quote = "within 45 days of award." if verbatim else "delivered inside 45 days"
        eid = _find(quote, blocks) or next(iter(blocks))
        return AnswerOut(
            found=True,
            answer="Delivery is required within 45 days of award.",
            citations=[CitationOut(evidence_id=eid, quote=quote)],
        )

    return ScriptedLLM({"AnswerOut": respond})
