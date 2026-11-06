from collections.abc import Callable
from pathlib import Path

import pytest

from rfp_intel.facts.extract import extract_facts, split_sentences
from rfp_intel.facts.labels import FactTypeConfig, label, load_fact_types
from rfp_intel.facts.models import Fact, FactKind
from rfp_intel.facts.store import FactStore
from rfp_intel.ingestion.models import Block, BlockKind, ParsedDocument, Table

from .conftest import REPO_ROOT

MakeDoc = Callable[..., ParsedDocument]


@pytest.fixture(scope="module")
def config() -> FactTypeConfig:
    return load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ("Solicitation Due | 27-JUN-2024 14:00:00", ["deadline"]),
        ("Closing Date: 07/09/2024 03:00 PM EDT", ["deadline"]),
        ("The new due date for this RFP will be July 9, 2024 at 2:00 PM CST.", ["deadline"]),
        ("Questions Deadline | 11-JUN-2024 16:00:00", ["questions"]),
        ("Pre-Proposal Meeting | 10-JUN-2024 14:00:00", ["pre_bid"]),
        ("PORFP Issue Date: | 05/24/2024", ["issue_date"]),
        ("Anticipated Approval/Award | 22-AUG-2024 18:00:00", ["award"]),
    ],
)
def test_datetime_labels(config: FactTypeConfig, context: str, expected: list[str]) -> None:
    assert label(config, FactKind.DATETIME, context) == expected


def test_line_item_due_date_is_not_a_deadline(config: FactTypeConfig) -> None:
    labels = label(
        config,
        FactKind.DATETIME,
        "Due Date mm/dd/yyyy | 06/10/2024",
        scope_extra="Product Name | Product Description Model # | Qty | Due Date mm/dd/yyyy",
    )
    assert "deadline" not in labels


def test_section_heading_is_the_fallback(config: FactTypeConfig) -> None:
    assert label(config, FactKind.DATETIME, "06/10/2024", section="Pre-Bidding Events") == [
        "pre_bid"
    ]
    assert label(config, FactKind.DATETIME, "Due 06/10/2024", section="Pre-Bidding Events") == [
        "deadline"
    ]


def test_neighbouring_fields_name_a_generic_one(config: FactTypeConfig) -> None:
    labels = label(
        config,
        FactKind.DATETIME,
        "Event date: 06/11/2024 05:00 PM EDT",
        neighbours="Event Type: Questions Due By | Attendance: N/A",
        section="Pre-Bidding Events",
    )
    assert labels == ["questions"]


def test_minimum_payment_on_a_credit_statement_is_not_payment_terms(config: FactTypeConfig) -> None:
    ctx = "The Total Minimum Payment Due is the greater of either $20 or 3% of the New Balance"
    assert "payment_invoice" not in label(config, FactKind.MONEY, ctx)


def test_bond_funding_is_not_a_bid_bond(config: FactTypeConfig) -> None:
    assert (
        label(
            config, FactKind.PERCENT, "goal for bond funded professional service contracts is 35%"
        )
        == []
    )
    assert label(config, FactKind.MONEY, "A bid bond of 5% or $5,000 is required") == [
        "bond_insurance"
    ]


def test_always_labels(config: FactTypeConfig) -> None:
    assert label(config, FactKind.IDENTIFIER, "SKU | 379-BFNZ") == ["identifier"]


def test_sentence_split_keeps_abbreviations_and_list_numbers() -> None:
    text = "Submit No. 2 by 2:00 p.m. CST today. 1. Bring forms. Deadline is June 10, 2024. Thanks."
    assert [s for _, s in split_sentences(text)] == [
        "Submit No. 2 by 2:00 p.m. CST today.",
        "1. Bring forms.",
        "Deadline is June 10, 2024.",
        "Thanks.",
    ]


def _doc_with(
    blocks: list[Block], make_doc: MakeDoc, tables: list[Table] | None = None
) -> ParsedDocument:
    doc = make_doc()
    doc.blocks = blocks
    doc.tables = tables or []
    return doc


def test_facts_carry_verbatim_raw_and_offsets(make_doc: MakeDoc, config: FactTypeConfig) -> None:
    block = Block(
        kind=BlockKind.PARAGRAPH,
        text="Buyer JALZATE, JASMINE | Email JALZATE@dallasisd.org\nSolicitation Due | 27-JUN-2024 14:00:00",
        page=2,
        section_path=["1 Header Information", "1.1 General Information"],
    )
    facts = extract_facts(_doc_with([block], make_doc), config)
    for f in facts:
        assert block.text[f.start : f.end] == f.raw
    due = next(f for f in facts if f.kind is FactKind.DATETIME)
    assert due.fact_types == ["deadline"]
    assert due.context == "Solicitation Due | 27-JUN-2024 14:00:00"
    assert due.section == "1.1 General Information"
    email = next(f for f in facts if f.kind is FactKind.EMAIL)
    assert "contact" in email.fact_types


def test_left_label_wins_in_a_row_with_two_dates(make_doc: MakeDoc, config: FactTypeConfig) -> None:
    rows = [["PORFP Issue Date:", "05/24/2024", "PROPOSAL DUE", "06/10/2024"]]
    table = Table(
        table_id=0,
        page=1,
        rows=[["Section 1 - General Information", "", "", ""], *rows],
        method="t",
    )
    block = Block(kind=BlockKind.TABLE, text=table.to_text(), page=1, table_id=0)
    facts = extract_facts(_doc_with([block], make_doc, [table]), config)
    labels = {f.raw: f.fact_types for f in facts if f.kind is FactKind.DATETIME}
    assert labels == {"05/24/2024": ["issue_date"], "06/10/2024": ["deadline"]}
    for f in facts:
        assert block.text[f.start : f.end] == f.raw


def test_table_header_gives_context_and_quantities(
    make_doc: MakeDoc, config: FactTypeConfig
) -> None:
    table = Table(
        table_id=0,
        page=3,
        rows=[
            ["Product Name", "Product Description Model #", "Qty", "Due Date mm/dd/yyyy"],
            ["1. SI# CC7802 Dell Latitude 5550", "Dell Latitude 5550", "30", "06/10/2024"],
        ],
        method="t",
    )
    block = Block(kind=BlockKind.TABLE, text=table.to_text(), page=3, table_id=0)
    facts = extract_facts(_doc_with([block], make_doc, [table]), config)
    qty = next(f for f in facts if f.kind is FactKind.QUANTITY)
    assert qty.value == {"qty": 30, "item": "SI# CC7802 Dell Latitude 5550"}
    due = next(f for f in facts if f.kind is FactKind.DATETIME)
    assert due.context == "Due Date mm/dd/yyyy | 06/10/2024"
    assert "deadline" not in due.fact_types


def test_row_quantities_take_wrapped_item_names(make_doc: MakeDoc, config: FactTypeConfig) -> None:
    block = Block(
        kind=BlockKind.PARAGRAPH,
        text="15.01 Tier 1 Small | 50,000 | Each\nStudent Chromebook Laptop (Touch)\n15.02 Tier 2 Large | 50,000 | Each",
        page=35,
    )
    qty = [
        f.value
        for f in extract_facts(_doc_with([block], make_doc), config)
        if f.kind is FactKind.QUANTITY
    ]
    assert qty[0] == {
        "qty": 50000,
        "unit": "each",
        "item": "Tier 1 Small Student Chromebook Laptop (Touch)",
    }
    assert qty[1]["item"] == "Tier 2 Large"


def test_year_inferred_from_document_date(make_doc: MakeDoc, config: FactTypeConfig) -> None:
    doc = make_doc("Proposals are due June 27 at 2:00 PM CT.", metadata={})
    from datetime import date

    doc.doc_date = date(2024, 5, 24)
    (f,) = [f for f in extract_facts(doc, config) if f.kind is FactKind.DATETIME]
    assert f.value["date"] == "2024-06-27" and f.value["year_inferred"]
    assert f.value["utc"] == "2024-06-27T19:00:00Z"


def test_headings_produce_no_facts(make_doc: MakeDoc, config: FactTypeConfig) -> None:
    block = Block(
        kind=BlockKind.HEADING, text="Section 2 - Due July 9, 2024", page=1, heading_level=1
    )
    assert extract_facts(_doc_with([block], make_doc), config) == []


# ---------------------------------------------------------------------------------------------
# Store


def _fact(fid: str, doc_id: str, kind: FactKind, types: list[str], bid: str = "BidA") -> Fact:
    return Fact(
        fact_id=fid, bid_id=bid, doc_id=doc_id, file_name=f"{doc_id}.pdf", doc_type="rfp", page=1,
        block_index=0, kind=kind, fact_types=types, raw="x", start=0, end=1, value={"v": fid}, context="x",
    )  # fmt: skip


def test_store_replace_query_delete(tmp_path: Path) -> None:
    with FactStore(tmp_path / "s.sqlite") as store:
        store.replace_document(
            "d1",
            [
                _fact("a", "d1", FactKind.DATETIME, ["deadline"]),
                _fact("b", "d1", FactKind.EMAIL, ["contact"]),
            ],
        )
        store.replace_document("d2", [_fact("c", "d2", FactKind.DATETIME, ["pre_bid"])])
        store.replace_document(
            "d9", [_fact("z", "d9", FactKind.DATETIME, ["deadline"], bid="BidB")]
        )

        assert [f.fact_id for f in store.query("BidA", fact_types=["deadline"])] == ["a"]
        assert [f.fact_id for f in store.query("BidA", kinds=[FactKind.DATETIME])] == ["a", "c"]
        assert store.query("BidA", fact_types=["deadline"])[0].value == {"v": "a"}
        assert store.count_by_type("BidA") == {"contact": 1, "deadline": 1, "pre_bid": 1}

        # re-indexing a changed document swaps its facts and leaves the others alone
        store.replace_document("d1", [_fact("a2", "d1", FactKind.DATETIME, ["deadline"])])
        assert sorted(f.fact_id for f in store.query("BidA")) == ["a2", "c"]

        assert store.delete_document("d2") == 1
        assert [f.fact_id for f in store.query("BidA")] == ["a2"]
        assert [f.fact_id for f in store.query("BidB")] == ["z"]


def test_store_persists_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "s.sqlite"
    with FactStore(path) as store:
        store.replace_document("d1", [_fact("a", "d1", FactKind.MONEY, ["pricing"])])
    with FactStore(path) as store:
        assert [f.fact_id for f in store.query()] == ["a"]
