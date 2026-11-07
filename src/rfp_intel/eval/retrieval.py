"""Retrieval evaluation: Recall@k, MRR and latency per search configuration.

Relevance is judged by locators (file, phrase, optional pages) rather than chunk ids, so the
gold set stays valid when chunking changes. A hit is relevant to a locator when its file name
contains the locator's file, its text contains the phrase (case and whitespace ignored) and,
if pages are given, its page range covers one of them.
"""

import json
import re
import statistics
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.models import NAMED_CONFIGS, Hit, SearchConfig

KS = (1, 3, 5, 10)
DEPTH = 10  # hits retrieved per question; MRR is MRR@10


class Locator(BaseModel):
    file: str
    must_contain: str
    pages: list[int] | None = None


class GoldQuestion(BaseModel):
    id: str
    bid: str
    question: str
    relevant: list[Locator]
    match: Literal["any", "all"] = "any"
    split: Literal["dev", "heldout", "unseen"] = "dev"


class GoldSet(BaseModel):
    questions: list[GoldQuestion]


def load_gold(path: Path) -> GoldSet:
    with path.open(encoding="utf-8") as fh:
        return GoldSet.model_validate(yaml.safe_load(fh))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def matches(locator: Locator, file_name: str, text: str, page_start: int, page_end: int) -> bool:
    if locator.file.casefold() not in file_name.casefold():
        return False
    if _norm(locator.must_contain) not in _norm(text):
        return False
    return not locator.pages or any(page_start <= p <= page_end for p in locator.pages)


class QuestionResult(BaseModel):
    id: str
    split: str
    question: str
    first_relevant_rank: int | None  # 1-based, within DEPTH
    recall: dict[int, float]  # k -> recall@k
    latency_ms: float
    top: list[str]  # "file pPAGES" of the top hits, for error analysis


class ConfigResult(BaseModel):
    config: str
    questions: list[QuestionResult]

    def metric(self, name: str, split: str | None = None) -> float:
        """`split`: one split, None for every question, or KNOWN for dev and held out."""
        qs = [
            q
            for q in self.questions
            if split is None or q.split == split or (split == KNOWN and q.split != "unseen")
        ]
        if not qs:
            return 0.0
        if name == "mrr":
            return statistics.fmean(
                1 / q.first_relevant_rank if q.first_relevant_rank else 0.0 for q in qs
            )
        if name == "latency_ms":
            return statistics.median(q.latency_ms for q in qs)
        k = int(name.removeprefix("recall@"))
        return statistics.fmean(q.recall[k] for q in qs)


class EvalRun(BaseModel):
    created_at: str
    git_commit: str | None
    gold_file: str
    question_count: int
    configs: list[ConfigResult]
    notes: dict[str, str] = Field(default_factory=dict)

    def config(self, name: str) -> ConfigResult:
        return next(c for c in self.configs if c.config == name)


def score_question(q: GoldQuestion, hits: Sequence[Hit], latency_ms: float) -> QuestionResult:
    found_at: list[int | None] = []  # per locator, the rank of its first matching hit
    for loc in q.relevant:
        rank = next(
            (h.rank for h in hits if matches(loc, h.file_name, h.text, h.page_start, h.page_end)),
            None,
        )
        found_at.append(rank)
    ranks = [r for r in found_at if r is not None]
    recall: dict[int, float] = {}
    for k in KS:
        within = [r is not None and r <= k for r in found_at]
        if q.match == "all":
            recall[k] = sum(within) / len(within)
        else:
            recall[k] = 1.0 if any(within) else 0.0
    return QuestionResult(
        id=q.id,
        split=q.split,
        question=q.question,
        first_relevant_rank=min(ranks) if ranks else None,
        recall=recall,
        latency_ms=round(latency_ms, 1),
        top=[f"{h.file_name} p{h.pages}" for h in hits[:3]],
    )


def evaluate(
    engine: SearchEngine,
    gold: GoldSet,
    configs: Sequence[SearchConfig | str] = tuple(NAMED_CONFIGS),
    *,
    gold_file: str = "",
    scope_to_bid: bool = True,
) -> EvalRun:
    results: list[ConfigResult] = []
    for cfg in configs:
        cfg_obj = NAMED_CONFIGS[cfg] if isinstance(cfg, str) else cfg
        engine.search("warm up", k=1, config=cfg_obj)  # load models before timing
        per_q: list[QuestionResult] = []
        for q in gold.questions:
            t = time.perf_counter()
            res = engine.search(
                q.question, bid_id=q.bid if scope_to_bid else None, k=DEPTH, config=cfg_obj
            )
            per_q.append(score_question(q, res.hits, (time.perf_counter() - t) * 1000))
        results.append(ConfigResult(config=cfg_obj.name, questions=per_q))
    return EvalRun(
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        git_commit=_git_commit(),
        gold_file=gold_file,
        question_count=len(gold.questions),
        configs=results,
        notes={
            "scope": "each question searched within its own bid" if scope_to_bid else "all bids"
        },
    )


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - fixed command, no user input
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


# ---------------------------------------------------------------------------------------------
# Report

METRICS = ("recall@1", "recall@3", "recall@5", "recall@10", "mrr")
KNOWN = "known"  # dev and held-out questions together


def _row(c: ConfigResult, split: str | None) -> str:
    cells = [f"{c.metric(m, split):.3f}" for m in METRICS]
    return f"| `{c.config}` | " + " | ".join(cells) + f" | {c.metric('latency_ms', split):.0f} |"


def render_markdown(run: EvalRun, descriptions: dict[str, str] | None = None) -> str:
    descriptions = descriptions or {}
    splits = [q.split for q in run.configs[0].questions]
    dev, held, unseen = (splits.count(s) for s in ("dev", "heldout", "unseen"))
    header = (
        "| Config | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | Median ms |\n"
        "|---|---|---|---|---|---|---|"
    )
    scope = run.notes.get("scope", "")
    lines = [
        "# Retrieval evaluation",
        "",
        f"Run {run.created_at} at commit `{run.git_commit or 'unknown'}` on `{run.gold_file}`: "
        f"{run.question_count} questions ({dev} dev, {held} held out"
        + (f", {unseen} on an unseen bid" if unseen else "")
        + f"), {scope}.",
        "Recall@k is the share of questions with a relevant passage in the top k (for `match: all` "
        "questions, the share of their passages found). MRR uses the first relevant hit within 10.",
        "",
        "## All questions",
        "",
        header,
        *[_row(c, None) for c in run.configs],
        "",
        "## Held-out questions only",
        "",
        header,
        *[_row(c, "heldout") for c in run.configs],
        "",
    ]
    if unseen:
        lines += [
            "## Unseen bid only",
            "",
            "Questions on a bid folder added after the system was built (a scanned RFP read by "
            "OCR, two addenda); nothing was tuned on it.",
            "",
            header,
            *[_row(c, "unseen") for c in run.configs],
            "",
        ]
    if descriptions:
        lines += ["## Configurations", ""]
        lines += [f"- `{name}`: {text}" for name, text in descriptions.items()]
        lines.append("")

    best = max(run.configs, key=lambda c: (c.metric("recall@5"), c.metric("mrr")))
    lines += [
        f"## Per question, `{best.config}`",
        "",
        "| Question | Split | First relevant rank | Top hit |",
        "|---|---|---|---|",
    ]
    for q in best.questions:
        rank = q.first_relevant_rank or "not in top 10"
        lines.append(
            f"| {q.id}: {q.question} | {q.split} | {rank} | {q.top[0] if q.top else '-'} |"
        )
    lines.append("")

    lines += ["## Misses at 5, by configuration", ""]
    for c in run.configs:
        misses = [q for q in c.questions if q.recall[5] < 1.0]
        names = ", ".join(f"{q.id} ({q.first_relevant_rank or '>10'})" for q in misses) or "none"
        lines.append(f"- `{c.config}`: {names}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# Baseline gate


class Baseline(BaseModel):
    config: str
    recall_at_5: float
    mrr: float
    git_commit: str | None


def baseline_from(run: EvalRun, config: str) -> Baseline:
    """The baseline covers the bids the system was built against (dev and held-out questions);
    the unseen bid is reported, not gated, so adding one never looks like a regression."""
    c = run.config(config)
    return Baseline(
        config=config,
        recall_at_5=round(c.metric("recall@5", KNOWN), 4),
        mrr=round(c.metric("mrr", KNOWN), 4),
        git_commit=run.git_commit,
    )


def check_regression(run: EvalRun, baseline: Baseline, tolerance: float = 0.05) -> list[str]:
    """Problems found: Recall@5 or MRR of the baseline's config dropped by more than tolerance."""
    c = run.config(baseline.config)
    problems = []
    for name, now, then in (
        ("recall@5", c.metric("recall@5", KNOWN), baseline.recall_at_5),
        ("mrr", c.metric("mrr", KNOWN), baseline.mrr),
    ):
        if now < then - tolerance:
            problems.append(f"{baseline.config} {name} fell from {then:.3f} to {now:.3f}")
    return problems


def save_run(
    run: EvalRun, json_path: Path, md_path: Path, descriptions: dict[str, str] | None = None
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(run, descriptions), encoding="utf-8")


def load_baseline(path: Path) -> Baseline:
    return Baseline.model_validate(json.loads(path.read_text(encoding="utf-8")))
