from pathlib import Path

import pytest

from rfp_intel.agents.fields import load_fields
from rfp_intel.agents.schema import BidResult, FieldResult, ValidationTally
from rfp_intel.eval.extraction import (
    Rule,
    evaluate_extraction,
    load_extraction_gold,
    render_extraction_markdown,
    score_field,
)

from .conftest import REPO_ROOT

GOLD = REPO_ROOT / "eval" / "extraction_gold.yaml"


def fr(
    value: str | list[str] | None, tier: str = "B", normalized: dict[str, str] | None = None
) -> FieldResult:
    return FieldResult(
        value=value,
        status="found" if value is not None else "not_found",
        confidence=0.85,
        tier=tier,
        normalized=normalized,
    )


def test_gold_covers_every_field_of_both_bids() -> None:
    gold = load_extraction_gold(GOLD)
    keys = {f.key for f in load_fields(REPO_ROOT / "config" / "fields.yaml").fields}
    assert set(gold.bids) == {"Bid1", "Bid2"}
    for rules in gold.bids.values():
        assert set(rules) == keys


@pytest.mark.parametrize(
    ("value", "rule", "passed"),
    [
        ("JA-207652", Rule(any_patterns=["JA-207652"]), True),
        ("168884", Rule(any_patterns=["JA-207652"]), False),
        ("3-year agreement with two 1-year renewals", Rule(patterns=["3|three", "renew"]), True),
        ("3-year agreement", Rule(patterns=["3|three", "renew"]), False),
        (None, Rule(absent=True), True),
        ("Not specified in the documents", Rule(absent=True, or_patterns=["not specified"]), True),
        ("5% bid bond", Rule(absent=True, or_patterns=["not specified"]), False),
        (None, Rule(patterns=["Dallas"]), False),
        (["Mercury Affidavit", "Contract Affidavit"], Rule(items=["Mercury", "Contract"]), True),
        (["Mercury Affidavit"], Rule(items=["Mercury", "Contract"]), False),
        ("Mercury Affidavit; Contract Affidavit", Rule(items=["Mercury", "Contract"]), True),
    ],
)
def test_rules(value: str | list[str] | None, rule: Rule, passed: bool) -> None:
    assert score_field("B", "f", fr(value), rule).passed is passed


def test_instant_rule_uses_normalized_then_date_then_text() -> None:
    rule = Rule(instant="2024-07-09T19:00:00Z")
    assert score_field("B", "due", fr("x", normalized={"utc": "2024-07-09T19:00:00Z"}), rule).passed
    assert not score_field(
        "B", "due", fr("x", normalized={"utc": "2024-07-09T20:00:00Z"}), rule
    ).passed
    assert score_field("B", "due", fr("x", normalized={"date": "2024-07-09"}), rule).passed
    assert score_field("B", "due", fr("Due July 9, 2024 at 2 PM"), rule).passed
    assert not score_field("B", "due", fr("Due June 27, 2024"), rule).passed


def _result(bid_id: str, fields: dict[str, FieldResult]) -> BidResult:
    return BidResult(
        bid_id=bid_id, run_id="r", generated_at="t", documents=[], fields=fields,
        validation=ValidationTally(fields=len(fields), passed_first_time=len(fields), passed_after_retry=0, failed=0, retries=0),
    )  # fmt: skip


def test_evaluate_and_calibration(tmp_path: Path) -> None:
    gold = load_extraction_gold(GOLD)
    fields = {k: fr(None, tier="NF-1") for k in gold.bids["Bid2"]}
    fields.update(
        {
            "bid_number": fr("BPM044557", tier="A"),
            "title": fr("Dell Laptops w/Extended Warranty", tier="A"),
            "delivery_date": fr("Within 30 days of award", tier="B"),  # wrong
            "part_no": fr(["379-BFNZ", "210-BLYZ"], tier="B"),
            "due_date": fr(
                "June 10, 2024, 2:00 PM EDT", tier="C", normalized={"utc": "2024-06-10T18:00:00Z"}
            ),
        }
    )
    (tmp_path / "Bid2.json").write_text(_result("Bid2", fields).model_dump_json(), encoding="utf-8")
    report = evaluate_extraction(tmp_path, gold, gold_file="g")
    assert report.missing_bids == ["Bid1"]
    rows = {r.tier: r for r in report.calibration()}
    assert (rows["A"].count, rows["A"].correct) == (2, 2)
    assert (rows["B"].count, rows["B"].correct) == (2, 1)
    assert rows["C"].accuracy == 1.0
    by_field = {s.field: s for s in report.scores}
    assert not by_field["delivery_date"].passed and "missing" in by_field["delivery_date"].reason
    assert by_field["bid_bond_requirement"].passed  # absent, as expected
    assert not by_field["product"].passed  # expected a value, got null
    md = render_extraction_markdown(report)
    assert (
        "## Calibration" in md
        and "| A | 2 | 2 | 100% |" in md
        and "Missing result files for: Bid1" in md
    )
