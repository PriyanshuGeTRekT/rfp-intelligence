"""Acceptance tests: the facts the extraction agents will rely on, from the two real bids."""

import pytest

from rfp_intel.facts.extract import extract_facts
from rfp_intel.facts.labels import load_fact_types
from rfp_intel.facts.models import Fact, FactKind
from rfp_intel.ingestion.models import BidFolder

from .conftest import REPO_ROOT


def _facts(folder: BidFolder) -> list[Fact]:
    config = load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")
    return [f for d in folder.documents for f in extract_facts(d, config)]


@pytest.fixture(scope="module")
def bid1(bid1_folder: BidFolder) -> list[Fact]:
    return _facts(bid1_folder)


@pytest.fixture(scope="module")
def bid2(bid2_folder: BidFolder) -> list[Fact]:
    return _facts(bid2_folder)


def _typed(facts: list[Fact], fact_type: str) -> list[Fact]:
    return [f for f in facts if fact_type in f.fact_types]


def test_bid1_deadline_candidates(bid1: list[Fact]) -> None:
    deadlines = {(f.doc_type, f.addendum_number, f.raw): f.value for f in _typed(bid1, "deadline")}
    assert set(deadlines) == {
        ("rfp", None, "27-JUN-2024 14:00:00"),
        ("addendum", 2, "July 9, 2024 at 2:00 PM CST"),
        ("bid_page", None, "07/09/2024 03:00 PM EDT"),
    }
    # the addendum and the portal agree on the instant, once CST in July is read as Central time
    assert (
        deadlines[("addendum", 2, "July 9, 2024 at 2:00 PM CST")]["utc"] == "2024-07-09T19:00:00Z"
    )
    assert deadlines[("bid_page", None, "07/09/2024 03:00 PM EDT")]["utc"] == "2024-07-09T19:00:00Z"


def test_bid1_pre_bid_meeting(bid1: list[Fact]) -> None:
    utc = {f.value["utc"] for f in _typed(bid1, "pre_bid") if f.value.get("utc")}
    assert utc == {"2024-06-10T19:00:00Z"}


def test_bid1_term_and_renewals(bid1: list[Fact]) -> None:
    terms = [f.value for f in _typed(bid1, "term_renewal") if f.kind is FactKind.DURATION]
    assert {"amount": 3, "unit": "year"}.items() <= next(
        v for v in terms if v["amount"] == 3
    ).items()
    assert any(v["amount"] == 1 and v["count"] == 2 for v in terms)


def test_bid1_identifiers(bid1: list[Fact]) -> None:
    ids = {f.value["id"] for f in bid1 if f.kind is FactKind.IDENTIFIER}
    assert {"JA-207652", "168884"} <= ids


def test_bid1_quantities_from_the_price_schedule(bid1: list[Fact]) -> None:
    items = {
        f.value["item"]: f.value["qty"]
        for f in bid1
        if f.kind is FactKind.QUANTITY and f.page == 35
    }
    assert items["Tier 1 Small Student Chromebook Laptop (Touch)"] == 50000


def test_bid2_deadline_candidates_skip_line_item_dates(bid2: list[Fact]) -> None:
    deadlines = {(f.file_name.split("_")[0], f.raw) for f in _typed(bid2, "deadline")}
    assert deadlines == {
        ("Dell Laptops w", "06/10/2024 02:00 PM EDT"),
        ("PORFP", "06/10/2024"),
    }


def test_bid2_delivery_and_warranty(bid2: list[Fact]) -> None:
    delivery = [f.value for f in _typed(bid2, "delivery") if f.kind is FactKind.DURATION]
    assert any(v["amount"] == 45 and v["unit"] == "day" for v in delivery)
    warranty = [f.value for f in _typed(bid2, "warranty") if f.kind is FactKind.DURATION]
    assert any(v["amount"] == 3 and v["unit"] == "year" for v in warranty)


def test_bid2_has_no_bond_or_insurance_facts(bid2: list[Fact]) -> None:
    """The evidence behind "Bid Bond: not specified" for Bid2."""
    assert _typed(bid2, "bond_insurance") == []


def test_bid2_credit_terms_are_not_payment_terms(bid2: list[Fact]) -> None:
    assert not [f for f in _typed(bid2, "payment_invoice") if "Minimum Payment" in f.context]


def test_bid2_identifiers_and_quantities(bid2: list[Fact]) -> None:
    ids = {f.value["id"] for f in bid2 if f.kind is FactKind.IDENTIFIER}
    assert {"BPM044557", "E20P4600040", "060B5400007", "WD22TB4", "379-BFNZ", "210-BLYZ"} <= ids
    qty = {f.value["item"]: f.value["qty"] for f in bid2 if f.kind is FactKind.QUANTITY}
    dock = f"Dell Thunderbolt 4 Dock {chr(0x2013)} WD22TB4"  # the PDF uses an en dash
    assert qty == {"SI# CC7802 Dell Latitude 5550": 30, dock: 30}


def test_bid2_contacts(bid2: list[Fact]) -> None:
    emails = {
        f.value["email"] for f in bid2 if f.kind is FactKind.EMAIL and "contact" in f.fact_types
    }
    assert "thawkins@treasurer.state.md.us" in emails


def test_every_fact_is_a_verbatim_substring(bid1: list[Fact], bid2: list[Fact]) -> None:
    for f in bid1 + bid2:
        assert f.raw
        assert f.kind is FactKind.QUANTITY or f.raw in f.context, f
