"""Extraction evaluation: field accuracy against the gold file, and calibration per tier.

Scores `outputs/<bid>.json` files written by `rfp extract`. The calibration table answers the
question the confidence tiers exist for: when the system says A, how often is it right? If a
tier is miscalibrated, its conditions change (in agents/confidence.py), not its number.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from rfp_intel.agents.schema import BidResult, FieldResult


class Rule(BaseModel):
    patterns: list[str] = Field(default_factory=list)
    any_patterns: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    instant: str | None = None
    absent: bool = False
    or_patterns: list[str] = Field(default_factory=list)


class ExtractionGold(BaseModel):
    bids: dict[str, dict[str, Rule]]


def load_extraction_gold(path: Path) -> ExtractionGold:
    with path.open(encoding="utf-8") as fh:
        return ExtractionGold.model_validate(yaml.safe_load(fh))


class FieldScore(BaseModel):
    bid_id: str
    field: str
    passed: bool
    tier: str
    confidence: float
    status: str
    value: str | None
    reason: str


def _text(value: str | list[str] | None) -> str:
    if value is None:
        return ""
    return " ; ".join(value) if isinstance(value, list) else value


def _match(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.I) is not None


def score_field(bid_id: str, key: str, fr: FieldResult, rule: Rule) -> FieldScore:
    text = _text(fr.value)
    passed, reason = _judge(fr, rule, text)
    return FieldScore(
        bid_id=bid_id,
        field=key,
        passed=passed,
        tier=fr.tier,
        confidence=fr.confidence,
        status=fr.status,
        value=text[:120] or None,
        reason=reason,
    )


def _judge(fr: FieldResult, rule: Rule, text: str) -> tuple[bool, str]:
    if rule.absent:
        if fr.value is None:
            return True, "absent, as expected"
        if any(_match(p, text) for p in rule.or_patterns):
            return True, "found, but states the absence"
        return False, "expected absent, got a value"
    if fr.value is None:
        return False, "expected a value, got null"
    if rule.instant:
        norm = fr.normalized or {}
        if norm.get("utc"):
            ok = norm["utc"] == rule.instant
            return ok, "instant matches" if ok else f"instant {norm['utc']} != {rule.instant}"
        if norm.get("date"):
            ok = norm["date"] == rule.instant[:10]
            return (
                ok,
                "date matches (no time)" if ok else f"date {norm['date']} != {rule.instant[:10]}",
            )
        ok = rule.instant[:10] in text or _match(_date_words(rule.instant[:10]), text)
        return ok, "date appears in text" if ok else "no normalized datetime and date not in text"
    if rule.items:
        items = fr.value if isinstance(fr.value, list) else [text]
        missing = [p for p in rule.items if not any(_match(p, it) for it in items)]
        return (not missing), "all items present" if not missing else f"missing items {missing}"
    if rule.patterns:
        missing = [p for p in rule.patterns if not _match(p, text)]
        return (not missing), "all patterns present" if not missing else f"missing {missing}"
    if rule.any_patterns:
        ok = any(_match(p, text) for p in rule.any_patterns)
        return ok, "a pattern matched" if ok else f"none of {rule.any_patterns} matched"
    return True, "no rule"


def _date_words(iso: str) -> str:
    y, m, d = iso.split("-")
    months = [
        "January", "February", "March", "April", "May", "June", "July", "August", "September",
        "October", "November", "December",
    ]  # fmt: skip
    return rf"{months[int(m) - 1]}\s+{int(d)},?\s+{y}"


class TierRow(BaseModel):
    tier: str
    count: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.count if self.count else 0.0


class ExtractionReport(BaseModel):
    results_dir: str
    gold_file: str
    scores: list[FieldScore]
    missing_bids: list[str] = Field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return sum(s.passed for s in self.scores) / len(self.scores) if self.scores else 0.0

    def by_bid(self) -> dict[str, float]:
        groups: dict[str, list[FieldScore]] = defaultdict(list)
        for s in self.scores:
            groups[s.bid_id].append(s)
        return {b: sum(x.passed for x in xs) / len(xs) for b, xs in groups.items()}

    def calibration(self) -> list[TierRow]:
        rows: dict[str, TierRow] = {}
        for s in self.scores:
            row = rows.setdefault(s.tier, TierRow(tier=s.tier, count=0, correct=0))
            row.count += 1
            row.correct += int(s.passed)
        order = ["A", "B", "C", "D", "E", "NF-1", "NF-2", "X"]
        return sorted(rows.values(), key=lambda r: order.index(r.tier) if r.tier in order else 99)


def evaluate_extraction(
    results_dir: Path, gold: ExtractionGold, gold_file: str = ""
) -> ExtractionReport:
    scores: list[FieldScore] = []
    missing: list[str] = []
    for bid_id, rules in gold.bids.items():
        path = results_dir / f"{bid_id}.json"
        if not path.exists():
            missing.append(bid_id)
            continue
        result = BidResult.model_validate_json(path.read_text(encoding="utf-8"))
        by_key = {f.key: f for f in result.fields.values()}
        for key, rule in rules.items():
            fr = by_key.get(key)
            if fr is None:
                scores.append(
                    FieldScore(
                        bid_id=bid_id,
                        field=key,
                        passed=False,
                        tier="-",
                        confidence=0.0,
                        status="missing",
                        value=None,
                        reason="field missing from the output",
                    )
                )
                continue
            scores.append(score_field(bid_id, key, fr, rule))
    return ExtractionReport(
        results_dir=str(results_dir), gold_file=gold_file, scores=scores, missing_bids=missing
    )


def render_extraction_markdown(report: ExtractionReport) -> str:
    lines = [
        "# Extraction evaluation",
        "",
        f"Results from `{report.results_dir}` scored against `{report.gold_file}`: "
        f"{len(report.scores)} fields, accuracy {report.accuracy:.1%}.",
    ]
    if report.missing_bids:
        lines.append(f"Missing result files for: {', '.join(report.missing_bids)}.")
    lines += ["", "| Bid | Accuracy |", "|---|---|"]
    lines += [f"| {b} | {a:.1%} |" for b, a in report.by_bid().items()]
    lines += [
        "",
        "## Calibration: accuracy per confidence tier",
        "",
        "A well-ordered table has accuracy falling as the tier falls. Tiers with few fields say "
        "little; the counts are shown for that reason.",
        "",
        "| Tier | Fields | Correct | Accuracy |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r.tier} | {r.count} | {r.correct} | {r.accuracy:.0%} |" for r in report.calibration()
    ]
    lines += [
        "",
        "## Per field",
        "",
        "| Bid | Field | Pass | Tier | Status | Value | Reason |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in report.scores:
        value = (s.value or "null").replace("|", "/")
        lines.append(
            f"| {s.bid_id} | {s.field} | {'yes' if s.passed else 'NO'} | {s.tier} | "
            f"{s.status} | {value[:60]} | {s.reason} |"
        )
    lines.append("")
    return "\n".join(lines)


def save_extraction_report(report: ExtractionReport, json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_extraction_markdown(report), encoding="utf-8")


def load_result(path: Path) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))
