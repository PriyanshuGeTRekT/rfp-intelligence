"""Acceptance tests on the two provided bids: what ingestion must get right on real files."""

from datetime import date

import pytest

from rfp_intel.ingestion.loader import load_bid_folder
from rfp_intel.ingestion.models import BidFolder, BlockKind, DocType, PageStatus, ParsedDocument

from .conftest import BIDS_DIR, CUES_PATH


@pytest.fixture(scope="module")
def bid1() -> BidFolder:
    return load_bid_folder(BIDS_DIR / "Bid1", CUES_PATH)


@pytest.fixture(scope="module")
def bid2() -> BidFolder:
    return load_bid_folder(BIDS_DIR / "Bid2", CUES_PATH)


def _doc(folder: BidFolder, startswith: str) -> ParsedDocument:
    return next(d for d in folder.documents if d.file_name.startswith(startswith))


def test_bid1_types_numbers_and_dates(bid1: BidFolder) -> None:
    got = {(d.doc_type, d.addendum_number, d.doc_date) for d in bid1.documents}
    assert got == {
        (DocType.RFP, None, date(2024, 5, 26)),
        (DocType.ADDENDUM, 1, date(2024, 6, 13)),
        (DocType.ADDENDUM, 2, date(2024, 6, 27)),
        (DocType.BID_PAGE, None, date(2024, 5, 29)),
    }


def test_bid2_types(bid2: BidFolder) -> None:
    types = sorted(d.doc_type.value for d in bid2.documents)
    assert types == ["affidavit", "affidavit", "bid_page", "rfp", "specs"]


def test_bid1_w9_pages_are_flagged_for_ocr(bid1: BidFolder) -> None:
    rfp = _doc(bid1, "JA-207652")
    flagged = [p.number for p in rfp.pages if p.status is PageStatus.NO_TEXT_LAYER]
    assert flagged == [54, 55, 56, 57, 58, 59]
    assert {i.page for i in bid1.issues if i.file_name == rfp.file_name} == set(flagged)


def test_bid1_headers_removed_but_kept(bid1: BidFolder) -> None:
    rfp = _doc(bid1, "JA-207652")
    assert "Dallas ISD rev" not in rfp.text()
    assert not any("Page 12 of 40" in b.text for b in rfp.blocks)
    assert any("JA-207652" in t for t in rfp.running_text)


def test_bid1_key_dates_keep_label_and_value_together(bid1: BidFolder) -> None:
    rfp = _doc(bid1, "JA-207652")
    rows = rfp.page_text(2).splitlines()
    assert "Solicitation Due | 27-JUN-2024 14:00:00" in rows
    assert "Pre-Proposal Meeting | 10-JUN-2024 14:00:00" in rows


def test_bid1_price_schedule_quantities_stay_on_their_line(bid1: BidFolder) -> None:
    rfp = _doc(bid1, "JA-207652")
    assert "15.01 Tier 1 Small | 50,000 | Each" in rfp.page_text(35).splitlines()


def test_bid1_addendum_keeps_questions_with_answers(bid1: BidFolder) -> None:
    add2 = _doc(bid1, "Addendum 2")
    assert "July 9, 2024 at 2:00 PM CST" in add2.text()
    add1 = _doc(bid1, "Addendum 1")
    qa = next(b for b in add1.blocks if b.text.startswith("11."))
    assert "Answer:" in qa.text
    assert "does not anticipate extending" in qa.text


def test_bid1_portal_fields(bid1: BidFolder) -> None:
    page = _doc(bid1, "Student and Staff")
    kv = {b.label: b.value for b in page.blocks if b.kind is BlockKind.KV}
    assert kv["Closing Date"] == "07/09/2024 03:00 PM EDT"
    assert kv["Solicitation Number"] == "JA-207652"


def test_bid2_dell_table_has_clean_skus(bid2: BidFolder) -> None:
    specs = _doc(bid2, "Dell_Laptop_Specs")
    rows = [r for t in specs.tables for r in t.rows]
    by_sku = {r[-1]: r[0] for r in rows}
    assert by_sku["210-BLYZ"] == "Dell Latitude 5550 XCTO Base"
    assert by_sku["379-BFNZ"].startswith("Intel Core Ultra 5 125U processor")
    assert by_sku["379-BFNZ"].endswith("up to 4.3 GHz Turbo)")


def test_bid2_porfp_contacts_are_intact(bid2: BidFolder) -> None:
    porfp = _doc(bid2, "PORFP")
    text = porfp.text()
    assert "Agency POC Email Address: | thawkins@treasurer.state.md.us" in text
    assert "PORFP Number: | #E20P4600040 eMMA Project Number: BPM044557" in text
    assert "WD22TB4" in text


def test_no_parse_errors(bid1: BidFolder, bid2: BidFolder) -> None:
    assert not [i for i in bid1.issues + bid2.issues if i.severity == "error"]
    assert not bid1.skipped_files and not bid2.skipped_files
