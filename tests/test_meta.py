from collections.abc import Callable
from datetime import date

import pytest

from rfp_intel.ingestion.meta import (
    CueConfig,
    classify,
    find_addendum_number,
    find_dates,
    find_doc_date,
)
from rfp_intel.ingestion.models import DocType, ParsedDocument

MakeDoc = Callable[..., ParsedDocument]


@pytest.mark.parametrize(
    ("title", "text", "file_name", "expected"),
    [
        (
            "AMENDMENT No. 3",
            "The purpose of this amendment is to extend the closing date. Offerors must acknowledge receipt of this amendment.",
            "doc1.pdf",
            DocType.ADDENDUM,
        ),
        (
            "Invitation for Bid 25-004",
            "The County invites sealed bids. Bids must be received by the due date. Scope of work: road salt.",
            "ifb.pdf",
            DocType.RFP,
        ),
        (
            "Non-Collusion Affidavit",
            "I hereby affirm that I am the affiant and duly authorized. Subscribed and sworn before a notary.",
            "nc.pdf",
            DocType.AFFIDAVIT,
        ),
        (
            "Quote 778812",
            "SKU 210-BLYZ processor memory storage. Part number 379-BFNZ. Configuration summary.",
            "q.pdf",
            DocType.SPECS,
        ),
        (
            "Form W-9",
            "Request for Taxpayer Identification Number and Certification",
            "x.pdf",
            DocType.FORM,
        ),
        ("Meeting minutes", "The board met on Tuesday.", "minutes.pdf", DocType.OTHER),
    ],
)
def test_classify_by_content(
    make_doc: MakeDoc, cues: CueConfig, title: str, text: str, file_name: str, expected: DocType
) -> None:
    doc_type, reason = classify(make_doc(text, title=title, file_name=file_name), cues)
    assert doc_type is expected, reason


def test_content_beats_a_misleading_file_name(make_doc: MakeDoc, cues: CueConfig) -> None:
    doc = make_doc(
        "I hereby affirm that the affiant is authorized. This affidavit is made under penalty of perjury.",
        title="Affidavit of Compliance",
        file_name="RFP_attachment_specs.pdf",
    )
    assert classify(doc, cues)[0] is DocType.AFFIDAVIT


def test_running_header_counts_as_head_text(make_doc: MakeDoc, cues: CueConfig) -> None:
    doc = make_doc("1. Will you accept 3.2 USB? Answer: Yes.", running_text=["ADDENDUM No. 1"])
    assert classify(doc, cues)[0] is DocType.ADDENDUM


def test_html_with_fields_is_a_bid_page(make_doc: MakeDoc, cues: CueConfig) -> None:
    doc = make_doc(
        media_type="html",
        kv=[("Solicitation Number", "X1"), ("Closing Date", "07/09/2024"), ("Title", "Laptops")],
    )
    assert classify(doc, cues)[0] is DocType.BID_PAGE


@pytest.mark.parametrize(
    ("head", "file_name", "expected"),
    [
        ("ADDENDUM No. 2", "a.pdf", 2),
        ("Amendment #3 to Solicitation", "a.pdf", 3),
        ("Addendum Number: IV", "a.pdf", 4),
        ("Second Addendum", "a.pdf", 2),
        ("Addendum Two", "a.pdf", 2),
        ("Clarifications", "Addendum_5.pdf", 5),
        ("Clarifications", "notes.pdf", None),
    ],
)
def test_addendum_number(
    make_doc: MakeDoc, head: str, file_name: str, expected: int | None
) -> None:
    assert find_addendum_number(make_doc("Body text.", title=head, file_name=file_name)) == expected


def test_find_dates_formats() -> None:
    text = "Due July 9, 2024; meeting 10-JUN-2024 14:00; posted 05/29/2024; iso 2024-06-13; bad 13/45/2024"
    assert [d for d, _, _ in find_dates(text)] == [
        date(2024, 7, 9),
        date(2024, 6, 10),
        date(2024, 5, 29),
        date(2024, 6, 13),
    ]


def test_doc_date_from_labelled_text(make_doc: MakeDoc) -> None:
    doc = make_doc("ADDENDUM No. 1", "Issue Date: June 13, 2024", "Proposals due July 9, 2024.")
    assert find_doc_date(doc) == (date(2024, 6, 13), "text")


def test_a_new_due_date_is_not_the_document_date(make_doc: MakeDoc) -> None:
    doc = make_doc(
        "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.",
        metadata={"creationDate": "D:20240627132029-05'00'"},
    )
    assert find_doc_date(doc) == (date(2024, 6, 27), "pdf_metadata")


def test_no_date_at_all(make_doc: MakeDoc) -> None:
    assert find_doc_date(make_doc("Nothing dated here.")) == (None, None)
