from typing import Any

import pytest

from rfp_intel.facts.models import FactKind
from rfp_intel.facts.patterns import (
    find_contacts,
    find_durations,
    find_identifiers,
    find_money,
    find_percents,
    find_prose_quantities,
    number_value,
)


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("45", 45),
        ("1,000", 1000),
        ("three", 3),
        ("ninety", 90),
        ("forty-five", 45),
        ("one hundred twenty", 120),
        ("lots", None),
    ],
)
def test_number_words(token: str, expected: int | None) -> None:
    assert number_value(token) == expected


def _one(text: str) -> tuple[str, dict[str, Any]]:
    (m,) = find_durations(text)
    return text[m.start : m.end], m.value


def test_delivery_window_with_anchor() -> None:
    raw, v = _one("9. Delivery within 45 days of Award.")
    assert raw == "within 45 days of Award"
    assert (v["amount"], v["unit"], v["relation"], v["anchor"]) == (
        45,
        "day",
        "within ... of",
        "award",
    )


def test_word_number_with_digits_in_parentheses() -> None:
    raw, v = _one("must give notice no fewer than ninety (90) days prior to the expiration")
    assert v["amount"] == 90
    assert v["anchor"] == "expiration"
    assert raw.startswith("no fewer than ninety (90) days")


def test_renewal_count() -> None:
    text = "a three (3) year agreement with two (2) successive one (1) year extensions"
    found = find_durations(text)
    assert [(m.value["amount"], m.value["unit"], m.value["count"]) for m in found] == [
        (3, "year", None),
        (1, "year", 2),
    ]


def test_warranty_term_from_delivery() -> None:
    raw, v = _one("3 years following the date of delivery")
    assert (v["amount"], v["unit"], v["anchor"], v["days"]) == (3, "year", "delivery", 1095)
    assert raw == "3 years following the date of delivery"


def test_business_days_and_years_s() -> None:
    _, v = _one("repairs within five (5) business days")
    assert v["qualifier"] == "business"
    _, v = _one("not to exceed a total of 5 years(s)")
    assert (v["amount"], v["unit"]) == (5, "year")


def test_net_terms() -> None:
    (m,) = find_durations("Payment terms: Net 30")
    assert m.value["net_terms"] is True and m.value["days"] == 30


def test_money_and_percent() -> None:
    text = "the greater of either $20 or 3% of the New Balance; contracts over $250,000 or $1.5 million"
    assert [m.value["amount"] for m in find_money(text)] == [20.0, 250000.0, 1500000.0]
    assert [m.value["percent"] for m in find_percents(text)] == [3.0]
    assert [m.value["amount"] for m in find_money("a fee of 500 dollars")] == [500.0]


def test_contacts() -> None:
    text = "Buyer JALZATE@dallasisd.org, (972)925-4100 or 972.925.4140 ext. 12; see www.dallasisd.org/mwbe."
    found = {m.kind: m.value for m in find_contacts(text)}
    assert found[FactKind.EMAIL] == {"email": "jalzate@dallasisd.org"}
    phones = [m.value for m in find_contacts(text) if m.kind is FactKind.PHONE]
    assert phones == [{"phone": "+19729254100"}, {"phone": "+19729254140", "ext": "12"}]
    assert found[FactKind.URL] == {"url": "https://www.dallasisd.org/mwbe"}


def _ids(text: str, taken: list[tuple[int, int]] | None = None) -> list[str]:
    return [m.value["id"] for m in find_identifiers(text, taken or [])]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Solicitation Number: JA-207652", ["JA-207652"]),
        ("Request For Proposal 168884", ["168884"]),
        ("eMMA Project Number: BPM044557", ["BPM044557"]),
        ("PORFP Number: #E20P4600040", ["E20P4600040"]),
        ("Master Contract, 060B5400007, are eligible", ["060B5400007"]),
        ("Description | SKU 379-BFNZ", ["379-BFNZ"]),
        ("Dell Thunderbolt 4 Dock - WD22TB4", ["WD22TB4"]),
        ("Reference Number: 00004079100", ["00004079100"]),
    ],
)
def test_identifiers(text: str, expected: list[str]) -> None:
    assert _ids(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Dallas, TX 75231",
        "Latitude 5550 laptops",
        "In 2024 the district",
        "DDR5 memory",
        "1920x1080 802.11ax",
        "Wi-Fi 6E",
        "PT-BR",
    ],
)
def test_not_identifiers(text: str) -> None:
    assert _ids(text) == []


def test_identifiers_skip_spans_taken_by_other_facts() -> None:
    text = "Call 410-260-7533 about RFQ-2024117"
    phone = next(m for m in find_contacts(text) if m.kind is FactKind.PHONE)
    assert _ids(text, [(phone.start, phone.end)]) == ["RFQ-2024117"]


def test_sku_family_and_compact_form() -> None:
    (m,) = find_identifiers("SKU 379-BFNZ", [])
    assert m.value["family"] == "sku" and m.value["compact"] == "379BFNZ"


def test_prose_quantities() -> None:
    assert [
        m.value["qty"] for m in find_prose_quantities("Qty: 30 laptops and 1,200 units of docks")
    ] == [30, 1200]
