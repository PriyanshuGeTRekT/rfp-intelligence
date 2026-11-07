"""Go / no-go recommendations and the bid comparison agent, over hand-made records."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from rfp_intel.agents.compare import ComparisonOut, DifferenceOut, compare, render_markdown
from rfp_intel.agents.fields import load_fields
from rfp_intel.agents.gonogo import Company, load_company, recommend
from rfp_intel.agents.gonogo import render_markdown as render_gonogo
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.llm import LLMError, ScriptedLLM
from rfp_intel.agents.schema import BidResult, FieldResult, Source, ValidationTally
from rfp_intel.api.app import create_app
from rfp_intel.config import Settings

from .conftest import REPO_ROOT, fake_runtime

CATALOG = load_fields(REPO_ROOT / "config" / "fields.yaml")
COMPANY = Company(
    company="Acme",
    authorized_manufacturers=["Dell", "HP"],
    known_manufacturers=["Dell", "HP", "Apple", "Lenovo"],
    product_keywords=["laptop", "chromebook"],
    can_install=False,
    max_bid_bond_percent=5,
    min_delivery_days=30,
    cooperative_contracts=["NASPO ValuePoint"],
    unavailable_documents=["performance bond"],
    min_days_to_prepare=7,
)


def record(bid: str, **values: Any) -> BidResult:
    """A record where every field is not found except those given (key=value)."""
    fields = {}
    for spec in CATALOG.fields:
        v = values.get(spec.key)
        normalized = None
        if spec.key == "due_date" and v:
            v, utc = v
            normalized = {"utc": utc}
        fields[spec.name] = FieldResult(
            key=spec.key,
            value=v,
            status="found" if v else "not_found",
            sources=[Source(file=f"{bid}.pdf", page=2, quote=str(v))] if v else [],
            confidence=0.85 if v else 0.8,
            tier="B" if v else "NF-1",
            normalized=normalized,
        )
    return BidResult(bid_id=bid, run_id="r", generated_at="t", documents=[], fields=fields,
                     validation=ValidationTally())  # fmt: skip


GOOD = {
    "due_date": ("2024-07-09 14:00 CDT", "2024-07-09T19:00:00Z"),
    "mfg_for_registration": "Dell",
    "product": "Dell Latitude laptops (30)",
    "delivery_date": "within 45 days of award",
    "bid_bond_requirement": "Not required",
}


def verdicts(rec: Any) -> dict[str, str]:
    return {c.name: c.verdict for c in rec.checks}


def test_a_bid_we_can_serve_is_a_go_and_cites_its_values() -> None:
    rec = recommend(record("A", **GOOD), COMPANY, as_of=date(2024, 6, 1))
    assert rec.decision == "review"  # documents were not extracted, so that one is open
    assert verdicts(rec)["Documents"] == "review"
    rec = recommend(
        record("A", **GOOD, additional_documentation=["W-9", "Affidavit"]),
        COMPANY,
        date(2024, 6, 1),
    )
    assert rec.decision == "go" and set(verdicts(rec).values()) == {"pass"}
    deadline = rec.checks[0]
    assert deadline.detail == "38 days left to prepare." and deadline.sources[0].file == "A.pdf"
    assert "**GO** for Acme" in render_gonogo(rec)


@pytest.mark.parametrize(
    ("change", "check", "detail"),
    [
        ({"bid_bond_requirement": "10% bid security"}, "Bid bond", "10% required; we can post 5%."),
        (
            {"mfg_for_registration": "Apple"},
            "Manufacturer",
            "Requires Apple; we are not authorized.",
        ),
        ({"installation": "Imaging and deployment required"}, "Installation", "we do not provide"),
        ({"delivery_date": "within 10 days of award"}, "Delivery", "we need 30"),
        ({"additional_documentation": ["Performance bond"]}, "Documents", "cannot supply"),
    ],
)
def test_each_capability_gap_is_a_no_go(change: dict[str, Any], check: str, detail: str) -> None:
    rec = recommend(record("A", **{**GOOD, **change}), COMPANY, as_of=date(2024, 6, 1))
    assert rec.decision == "no-go"
    failed = next(c for c in rec.checks if c.name == check)
    assert failed.verdict == "fail" and detail in failed.detail


def test_a_passed_deadline_and_an_unknown_vehicle() -> None:
    rec = recommend(
        record("A", **GOOD, contract_or_cooperative="Texas DIR contract"), COMPANY, date(2024, 8, 1)
    )
    assert verdicts(rec)["Deadline"] == "fail" and "passed 23 days" in rec.checks[0].detail
    assert verdicts(rec)["Contract vehicle"] == "review"


def test_the_shipped_company_profile_loads() -> None:
    assert load_company(REPO_ROOT / "config" / "company.yaml").authorized_manufacturers


def _differ(system: str, user: str) -> BaseModel:
    assert "due_date | 2024-07-09 14:00 CDT | (not found)" in user  # the model sees the table
    return ComparisonOut(
        summary="A has a deadline; B states none.",
        differences=[
            DifferenceOut(field="due_date", statement="A is due July 9; B states no date."),
            DifferenceOut(field="not_a_field", statement="Invented."),
        ],
    )


def test_comparison_table_differences_and_recommendations() -> None:
    a, b = record("A", **GOOD), record("B", product="Chromebooks (500)")
    llm = ScriptedLLM({"ComparisonOut": _differ})
    out = compare([a, b], CATALOG, llm=GuardedLLM(llm), model="cheap", company=COMPANY,
                  as_of=date(2024, 6, 1))  # fmt: skip
    assert len(out.rows) == len(CATALOG.fields) and out.bids == ["A", "B"]
    due = next(r for r in out.rows if r.key == "due_date")
    assert due.cells["A"].source == "A.pdf, p. 2" and due.cells["B"].value == "(not found)"
    assert [d.field for d in out.differences] == ["due_date"]  # the unknown field is dropped
    assert [r.decision for r in out.recommendations] == ["review", "review"]
    md = render_markdown(out, CATALOG)
    assert "## Key differences" in md and "| Due Date | 2024-07-09 14:00 CDT (B)" in md
    assert len(llm.calls) == 1 and llm.calls[0].model == "cheap"


def test_a_failed_model_call_keeps_the_table() -> None:
    def broken(system: str, user: str) -> BaseModel:
        raise LLMError("rate limited")

    out = compare([record("A"), record("B")], CATALOG,
                  llm=GuardedLLM(ScriptedLLM({"ComparisonOut": broken})), model="m")  # fmt: skip
    assert out.error and "rate limited" in out.error and out.rows and out.summary is None
    with pytest.raises(ValueError):
        compare([record("A")], CATALOG)


def test_decision_endpoints(settings: Settings) -> None:
    settings.outputs_dir.mkdir(parents=True)
    for bid, values in (("A", GOOD), ("B", {"product": "laptops"})):
        path = settings.outputs_dir / f"{bid}.json"
        path.write_text(record(bid, **values).model_dump_json(), encoding="utf-8")
    client = TestClient(create_app(settings, runtime_factory=fake_runtime))
    r = client.get("/api/bids/A/go-no-go", params={"as_of": "2024-06-01"})
    assert r.status_code == 200 and r.json()["bid_id"] == "A" and len(r.json()["checks"]) == 8
    r = client.get("/api/compare", params=[("bids", "A"), ("bids", "B")])
    assert r.status_code == 200 and r.json()["bids"] == ["A", "B"] and r.json()["summary"] is None
    assert client.get("/api/compare", params=[("bids", "A"), ("bids", "C")]).status_code == 404
    assert client.get("/api/compare", params={"bids": "A"}).status_code == 422
    traversal = [("bids", "A"), ("bids", "../../etc/passwd")]
    assert client.get("/api/compare", params=traversal).status_code == 400
