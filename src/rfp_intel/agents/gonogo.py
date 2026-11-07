"""Go / no-go recommendation: an extraction record checked against the company's capabilities
(`config/company.yaml`).

Each check reads one or two extracted fields and returns pass, fail or review, with the value
it read and that value's citations, so every verdict can be traced to the documents. The
recommendation is "no-go" when any check fails, "review" when none fails but some could not be
decided (a field was not found, or its wording is not one the rule can read), and "go" otherwise.
The checks are rules, not a model call: a bid decision should be explainable and repeatable.
"""

import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from rfp_intel.agents.schema import BidResult, FieldResult, Source

Verdict = Literal["pass", "fail", "review"]
Decision = Literal["go", "no-go", "review"]


class Company(BaseModel):
    company: str
    authorized_manufacturers: list[str] = Field(default_factory=list)
    known_manufacturers: list[str] = Field(default_factory=list)
    product_keywords: list[str] = Field(default_factory=list)
    can_install: bool = True
    max_bid_bond_percent: float | None = None
    min_delivery_days: int | None = None
    cooperative_contracts: list[str] = Field(default_factory=list)
    unavailable_documents: list[str] = Field(default_factory=list)
    min_days_to_prepare: int = 0


def load_company(path: Path) -> Company:
    return Company.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class Check(BaseModel):
    name: str
    verdict: Verdict
    detail: str
    field: str | None = None
    value: str | None = None
    sources: list[Source] = Field(default_factory=list)


class Recommendation(BaseModel):
    bid_id: str
    company: str
    decision: Decision
    as_of: date
    checks: list[Check]

    @property
    def counts(self) -> dict[str, int]:
        return {v: sum(c.verdict == v for c in self.checks) for v in ("pass", "fail", "review")}


def _text(f: FieldResult) -> str:
    return "; ".join(f.value) if isinstance(f.value, list) else (f.value or "")


def _mentions(text: str, names: list[str]) -> list[str]:
    return [n for n in names if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text, re.I)]


def _check(name: str, verdict: Verdict, detail: str, f: FieldResult | None = None) -> Check:
    return Check(
        name=name,
        verdict=verdict,
        detail=detail,
        field=f.key if f else None,
        value=_text(f)[:300] if f else None,
        sources=f.sources[:2] if f else [],
    )


def _deadline(r: BidResult, c: Company, as_of: date) -> Check:
    f = r.by_key("due_date")
    utc = (f.normalized or {}).get("utc") or (f.normalized or {}).get("date")
    if f.status != "found" or not utc:
        return _check("Deadline", "review", "No due date was extracted.", f)
    due = datetime.fromisoformat(str(utc).replace("Z", "+00:00")).date()
    days = (due - as_of).days
    if days < 0:
        return _check("Deadline", "fail", f"The deadline passed {-days} days before {as_of}.", f)
    if days < c.min_days_to_prepare:
        need = c.min_days_to_prepare
        return _check("Deadline", "fail", f"{days} days left; we need {need} to prepare.", f)
    return _check("Deadline", "pass", f"{days} days left to prepare.", f)


def _manufacturer(r: BidResult, c: Company) -> Check:
    """The manufacturers the registration field names; when it names none (or says "OEM"),
    the ones the model numbers or products name. Any authorized one is enough."""
    for key in ("mfg_for_registration", "model_no", "product"):
        source = r.by_key(key)
        named = _mentions(_text(source), c.known_manufacturers) if source.status == "found" else []
        if named:
            break
    else:
        first = r.by_key("mfg_for_registration")
        return _check("Manufacturer", "review", "No manufacturer is named.", first)
    ours = _mentions(" ".join(named), c.authorized_manufacturers)
    if ours:
        return _check(
            "Manufacturer", "pass", f"Requires {', '.join(named)}; we are authorized.", source
        )
    return _check(
        "Manufacturer", "fail", f"Requires {', '.join(named)}; we are not authorized.", source
    )


def _products(r: BidResult, c: Company) -> Check:
    f = r.by_key("product")
    text = " ".join(_text(r.by_key(k)) for k in ("product", "product_specification", "title"))
    hits = [k for k in c.product_keywords if re.search(rf"\b{re.escape(k)}s?\b", text, re.I)]
    if hits:
        return _check("Products", "pass", f"We sell these: {', '.join(hits)}.", f)
    return _check("Products", "review", "The products are not among the ones we list.", f)


def _installation(r: BidResult, c: Company) -> Check:
    f = r.by_key("installation")
    if f.status != "found" or re.search(
        r"\bnot (required|specified|mentioned)\b|\bnone\b", _text(f), re.I
    ):
        return _check("Installation", "pass", "No installation services are required.", f)
    if c.can_install:
        return _check("Installation", "pass", "Services are required; we provide them.", f)
    return _check("Installation", "fail", "Services are required; we do not provide them.", f)


def _bid_bond(r: BidResult, c: Company) -> Check:
    f = r.by_key("bid_bond_requirement")
    text = _text(f)
    if f.status != "found" or re.search(
        r"\bnot (required|specified|stated)\b|\bnone\b", text, re.I
    ):
        return _check("Bid bond", "pass", "No bid bond is required.", f)
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if pct is None or c.max_bid_bond_percent is None:
        return _check("Bid bond", "review", "A bid bond is required; check the amount.", f)
    need = float(pct.group(1))
    if need > c.max_bid_bond_percent:
        cap = c.max_bid_bond_percent
        return _check("Bid bond", "fail", f"{need:g}% required; we can post {cap:g}%.", f)
    return _check(
        "Bid bond", "pass", f"{need:g}% required; within our {c.max_bid_bond_percent:g}%.", f
    )


def _delivery(r: BidResult, c: Company) -> Check:
    f = r.by_key("delivery_date")
    if f.status != "found":
        return _check("Delivery", "pass", "No delivery deadline is stated.", f)
    days = re.search(r"(\d+)\s*(?:calendar |business |working )?days?\b", _text(f), re.I)
    if days is None or c.min_delivery_days is None:
        return _check("Delivery", "review", "A delivery date is set; check it against stock.", f)
    n = int(days.group(1))
    if n < c.min_delivery_days:
        return _check(
            "Delivery", "fail", f"Delivery within {n} days; we need {c.min_delivery_days}.", f
        )
    return _check("Delivery", "pass", f"Delivery within {n} days is achievable.", f)


def _cooperative(r: BidResult, c: Company) -> Check:
    f = r.by_key("contract_or_cooperative")
    text = _text(f)
    if f.status != "found" or re.search(r"\bnot (specified|stated)\b|\bnone\b", text, re.I):
        return _check("Contract vehicle", "pass", "No contract vehicle is required.", f)
    held = _mentions(text, c.cooperative_contracts)
    if held:
        return _check("Contract vehicle", "pass", f"Uses {', '.join(held)}, which we hold.", f)
    return _check("Contract vehicle", "review", "Names a contract vehicle we do not list.", f)


def _documents(r: BidResult, c: Company) -> Check:
    f = r.by_key("additional_documentation")
    missing = _mentions(_text(f), c.unavailable_documents)
    if missing:
        return _check(
            "Documents", "fail", f"Requires {', '.join(missing)}, which we cannot supply.", f
        )
    if f.status != "found":
        return _check("Documents", "review", "The required documents were not extracted.", f)
    return _check("Documents", "pass", "We can supply every listed document.", f)


def recommend(record: BidResult, company: Company, as_of: date | None = None) -> Recommendation:
    as_of = as_of or datetime.now(UTC).date()
    checks = [
        _deadline(record, company, as_of),
        _manufacturer(record, company),
        _products(record, company),
        _installation(record, company),
        _bid_bond(record, company),
        _delivery(record, company),
        _cooperative(record, company),
        _documents(record, company),
    ]
    verdicts = {ch.verdict for ch in checks}
    decision: Decision = (
        "no-go" if "fail" in verdicts else "review" if "review" in verdicts else "go"
    )
    return Recommendation(
        bid_id=record.bid_id, company=company.company, decision=decision, as_of=as_of, checks=checks
    )


def render_markdown(rec: Recommendation) -> str:
    n = rec.counts
    lines = [
        f"# Go / no-go: {rec.bid_id}",
        "",
        f"**{rec.decision.upper()}** for {rec.company} as of {rec.as_of}: "
        f"{n['pass']} passed, {n['fail']} failed, {n['review']} to review.",
        "",
        "| Check | Verdict | Why | Extracted value | Source |",
        "|---|---|---|---|---|",
    ]
    for ch in rec.checks:
        src = f"{ch.sources[0].file}, p. {ch.sources[0].page}" if ch.sources else ""
        value = (ch.value or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(f"| {ch.name} | {ch.verdict} | {ch.detail} | {value} | {src} |")
    return "\n".join(lines) + "\n"
