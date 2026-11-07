"""Bid comparison agent: a side-by-side report of several bids' extraction records.

The table is built from the records alone, so every cell is an extracted value with its tier
and first citation. One call to the cheap model then writes the key differences; it sees only
the table, and a difference that names a field not in the table is dropped. With a company
profile, each bid's go / no-go recommendation is added. A failed model call leaves the table
and the recommendations intact and records the error.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from rfp_intel.agents.fields import FieldCatalog
from rfp_intel.agents.gonogo import Company, Recommendation, recommend
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.schema import BidResult, FieldResult

CELL_CHARS = 160

COMPARE_SYSTEM = """You compare public procurement bids for a sales team.
You get a table: one row per field, one column per bid, each cell an extracted value.
Write the differences that matter for deciding which bid to pursue and how to price it:
deadlines, products and quantities, specifications, warranty, bonds, delivery, terms,
required documents. Use only what the table says; never add facts. Name the bids by their ids.
A cell reading "(not found)" means the documents do not state it; say so rather than guess."""


class DifferenceOut(BaseModel):
    field: str = Field(description="The field key exactly as in the table's first column")
    statement: str = Field(description="One sentence comparing the bids on this field")


class ComparisonOut(BaseModel):
    summary: str = Field(description="Two to four sentences on how the bids differ overall")
    differences: list[DifferenceOut]


class Cell(BaseModel):
    value: str
    status: str
    tier: str
    source: str | None = None


class Row(BaseModel):
    key: str
    name: str
    cells: dict[str, Cell]


class Comparison(BaseModel):
    bids: list[str]
    rows: list[Row]
    summary: str | None = None
    differences: list[DifferenceOut] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    usage: dict[str, float | int] = Field(default_factory=dict)
    error: str | None = None


def load_records(outputs_dir: Path, bids: Sequence[str]) -> list[BidResult]:
    """The extraction records of `bids`; FileNotFoundError names the bids not extracted yet."""
    missing = [b for b in bids if not (outputs_dir / f"{b}.json").exists()]
    if missing:
        raise FileNotFoundError(f"no extraction record for {', '.join(missing)}; run rfp extract")
    return [
        BidResult.model_validate_json((outputs_dir / f"{b}.json").read_text(encoding="utf-8"))
        for b in bids
    ]


def _cell(f: FieldResult) -> Cell:
    text = "; ".join(f.value) if isinstance(f.value, list) else (f.value or "(not found)")
    if len(text) > CELL_CHARS:
        text = text[: CELL_CHARS - 3] + "..."
    source = f"{f.sources[0].file}, p. {f.sources[0].page}" if f.sources else None
    return Cell(value=text, status=f.status, tier=f.tier, source=source)


def build_rows(records: Sequence[BidResult], catalog: FieldCatalog) -> list[Row]:
    rows = []
    for spec in catalog.fields:
        cells = {r.bid_id: _cell(r.by_key(spec.key)) for r in records}
        rows.append(Row(key=spec.key, name=spec.name, cells=cells))
    return rows


def _table_prompt(bids: Sequence[str], rows: Sequence[Row]) -> str:
    lines = ["field | " + " | ".join(bids)]
    for row in rows:
        if row.key == "bid_summary":
            continue
        lines.append(f"{row.key} | " + " | ".join(row.cells[b].value for b in bids))
    return "\n".join(lines)


def compare(
    records: Sequence[BidResult],
    catalog: FieldCatalog,
    *,
    llm: GuardedLLM | None = None,
    model: str = "",
    company: Company | None = None,
    as_of: date | None = None,
) -> Comparison:
    """Compare two or more bids; `llm` None skips the written differences."""
    if len(records) < 2:
        raise ValueError("a comparison needs at least two bids")
    bids = [r.bid_id for r in records]
    rows = build_rows(records, catalog)
    out = Comparison(bids=bids, rows=rows)
    if company is not None:
        out.recommendations = [recommend(r, company, as_of) for r in records]
    if llm is None:
        return out
    outcome = llm.call(
        system=COMPARE_SYSTEM,
        user=_table_prompt(bids, rows),
        schema=ComparisonOut,
        model=model,
        effort="low",
    )
    out.usage = outcome.usage.as_dict()
    if outcome.output is None:
        out.error = outcome.error or "the model call failed"
        return out
    keys = {row.key for row in rows}
    out.summary = outcome.output.summary
    out.differences = [d for d in outcome.output.differences if d.field in keys]
    return out


def render_markdown(c: Comparison, catalog: FieldCatalog) -> str:
    lines = [f"# Bid comparison: {', '.join(c.bids)}", ""]
    if c.summary:
        lines += [c.summary, ""]
    if c.differences:
        names = {f.key: f.name for f in catalog.fields}
        lines += ["## Key differences", ""]
        lines += [f"- **{names.get(d.field, d.field)}**: {d.statement}" for d in c.differences]
        lines.append("")
    if c.error:
        lines += [f"_The written differences are missing: {c.error}_", ""]
    if c.recommendations:
        lines += [
            "## Go / no-go",
            "",
            "| Bid | Decision | Failed checks | To review |",
            "|---|---|---|---|",
        ]
        for rec in c.recommendations:
            failed = ", ".join(ch.name for ch in rec.checks if ch.verdict == "fail") or "-"
            review = ", ".join(ch.name for ch in rec.checks if ch.verdict == "review") or "-"
            lines.append(f"| {rec.bid_id} | **{rec.decision}** | {failed} | {review} |")
        lines += [
            "",
            f"_Checked against {c.recommendations[0].company} as of {c.recommendations[0].as_of}._",
            "",
        ]
    lines += ["## Side by side", "", "| Field | " + " | ".join(c.bids) + " |"]
    lines.append("|---" * (len(c.bids) + 1) + "|")
    for row in c.rows:
        cells = []
        for b in c.bids:
            cell = row.cells[b]
            text = cell.value.replace("|", "/").replace("\n", " ")
            src = f" <br>_{cell.source}_" if cell.source else ""
            cells.append(f"{text} ({cell.tier}){src}")
        lines.append(f"| {row.name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
