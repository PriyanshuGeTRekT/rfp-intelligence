"""Quote grounding: model quotes that differ from the source only in punctuation are mapped
back to the exact source text; anything else is rejected. Cases come from a live run."""

import pytest

from rfp_intel.agents.evidence import EvidenceItem, EvidenceStore
from rfp_intel.agents.validate import FieldDraft, Quote, ground, ground_draft

ROW = (
    "Bid Information\nSolicitation Number | JA-207652\nTitle | Student and Staff Computing Devices"
)


@pytest.mark.parametrize(
    ("quote", "exact"),
    [
        ("Solicitation Number: JA-207652", "Solicitation Number | JA-207652"),
        (
            "**Title:** Student and Staff Computing Devices",
            "Title | Student and Staff Computing Devices",
        ),
        ("solicitation  number | ja-207652", "Solicitation Number | JA-207652"),
        ("Computing Devices", "Computing Devices"),
    ],
)
def test_punctuation_differences_ground_to_the_source_text(quote: str, exact: str) -> None:
    assert ground(quote, ROW) == exact


@pytest.mark.parametrize(
    "quote",
    [
        "Solicitation No. JA-207652",  # a different word
        "Number JA-207652 Solicitation",  # different order
        "ation Numb",  # not whole words
        "JA",  # too short to mean anything
        "Student and Staff Laptops",  # paraphrase
    ],
)
def test_anything_but_punctuation_is_rejected(quote: str) -> None:
    assert ground(quote, ROW) is None


def test_trailing_punctuation_is_kept_when_the_source_has_it() -> None:
    text = "Delivery is required within 45 days of award. Late delivery incurs penalties."
    assert ground("within 45 days of award.", text) == "within 45 days of award."
    assert ground("within 45 days of award!", text) == "within 45 days of award"


def test_drafts_are_rewritten_with_exact_quotes_only_where_they_ground() -> None:
    store = EvidenceStore()
    store.add(EvidenceItem(evidence_id="e1", file="rfp.pdf", page_start=1, page_end=1,
                           doc_type="rfp", text=ROW))  # fmt: skip
    draft = FieldDraft(
        field="bid_number",
        status="found",
        value="JA-207652",
        quotes=[
            Quote(evidence_id="e1", text="Solicitation Number: JA-207652"),
            Quote(evidence_id="e1", text="Solicitation No. JA-207652"),
            Quote(evidence_id="missing", text="Solicitation Number: JA-207652"),
        ],
    )
    grounded = ground_draft(draft, store)
    assert [q.text for q in grounded.quotes] == [
        "Solicitation Number | JA-207652",
        "Solicitation No. JA-207652",  # left as is: the validator rejects it
        "Solicitation Number: JA-207652",
    ]


TERM = (
    "4.2 Term. The term of this proposal shall be for a three (3) year agreement, with the "
    "option to renew for two (2) additional one (1) year periods upon mutual agreement."
)


def test_elided_quotes_ground_fragment_by_fragment_in_order() -> None:
    quote = (
        "The term of this proposal shall be for a three (3) year agreement ... renew for two (2)"
    )
    assert ground(quote, TERM) == (
        "The term of this proposal shall be for a three (3) year agreement … renew for two (2)"
    )
    assert ground("term of this proposal … upon mutual agreement.", TERM) == (
        "term of this proposal … upon mutual agreement."
    )


def test_elision_cannot_reorder_or_invent_fragments() -> None:
    assert ground("renew for two (2) ... The term of this proposal", TERM) is None  # order
    assert ground("The term of this proposal ... five (5) year extension", TERM) is None


def test_a_quote_cited_to_the_wrong_passage_is_pointed_at_the_right_one() -> None:
    store = EvidenceStore()
    for eid, text in (("e1", "Delivery within 45 days of Award."), ("e2", ROW)):
        store.add(EvidenceItem(evidence_id=eid, file="f.pdf", page_start=1, page_end=1,
                               doc_type="rfp", text=text))  # fmt: skip
    draft = FieldDraft(
        field="delivery_date", status="found", value="Within 45 days of award",
        quotes=[Quote(evidence_id="e2", text="Delivery within 45 days of Award.")],
    )  # fmt: skip
    fixed = ground_draft(draft, store, shown=["e1", "e2"])
    assert fixed.quotes == [Quote(evidence_id="e1", text="Delivery within 45 days of Award.")]
    assert ground_draft(draft, store, shown=["e2"]).quotes == draft.quotes  # e1 was not shown


def test_a_form_can_be_cited_by_its_document_title() -> None:
    # The Maryland Contract Affidavit's name is only in the PDF's metadata title, not in its
    # text: the title is shown with the passage and a quote of it grounds.
    store = EvidenceStore()
    store.add(EvidenceItem(evidence_id="e1", file="Contract_Affidavit.pdf", page_start=1,
                           page_end=1, doc_type="affidavit", text="A. AUTHORITY I hereby affirm",
                           title="Attachment N - Contract Affidavit"))  # fmt: skip
    item = store.get("e1")
    assert item is not None and '"Attachment N - Contract Affidavit"' in item.header()
    draft = FieldDraft(field="additional_documentation", status="found",
                       value=["Contract Affidavit"],
                       quotes=[Quote(evidence_id="e1", text="Contract Affidavit"),
                               # copied with the header's label, as gpt-oss-120b did
                               Quote(evidence_id="e1",
                                     text='document title "Attachment N - Contract Affidavit"'),
                               Quote(evidence_id="e1", text="title A. AUTHORITY")])  # fmt: skip
    assert [q.text for q in ground_draft(draft, store).quotes] == [
        "Contract Affidavit",
        "Attachment N - Contract Affidavit",
        "title A. AUTHORITY",  # only "document title" is a label; this one is rejected
    ]


def test_a_copied_passage_header_grounds_as_its_title() -> None:
    # gpt-oss-120b cited a form by copying the whole header line the passage starts with.
    store = EvidenceStore()
    store.add(EvidenceItem(evidence_id="e1", file="Contract_Affidavit.pdf", page_start=1,
                           page_end=1, doc_type="affidavit", text="A. AUTHORITY I hereby affirm",
                           title="Attachment N - Contract Affidavit"))  # fmt: skip
    header = '[e1] Contract_Affidavit.pdf p1 (affidavit; document title "Attachment N - Contract Affidavit")'
    draft = FieldDraft(field="additional_documentation", status="found",
                       value=["Contract Affidavit"], quotes=[Quote(evidence_id="e1", text=header)])  # fmt: skip
    assert [q.text for q in ground_draft(draft, store).quotes] == [
        "Attachment N - Contract Affidavit"
    ]
