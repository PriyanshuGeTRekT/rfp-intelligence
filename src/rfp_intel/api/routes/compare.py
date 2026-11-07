"""Decisions over extraction records: go / no-go for one bid, a comparison of several."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from rfp_intel.agents.compare import Comparison, compare, load_records
from rfp_intel.agents.fields import load_fields
from rfp_intel.agents.gonogo import Recommendation, load_company, recommend
from rfp_intel.agents.schema import BidResult
from rfp_intel.api.context import AppContext, context
from rfp_intel.security import PathNotAllowedError, resolve_within

router = APIRouter(tags=["decisions"])
Ctx = Annotated[AppContext, Depends(context)]


def _records(ctx: AppContext, bids: list[str]) -> list[BidResult]:
    for bid in bids:  # bid ids name files under outputs/: keep them inside it
        try:
            resolve_within(ctx.settings.outputs_dir, f"{bid}.json")
        except PathNotAllowedError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return load_records(ctx.settings.outputs_dir, bids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/bids/{bid_id}/go-no-go")
def go_no_go(bid_id: str, ctx: Ctx, as_of: date | None = None) -> Recommendation:
    """Check the bid's extraction record against config/company.yaml; no model call."""
    [record] = _records(ctx, [bid_id])
    return recommend(record, load_company(ctx.settings.config_dir / "company.yaml"), as_of)


@router.get("/compare")
def compare_bids(
    ctx: Ctx,
    bids: Annotated[list[str], Query(min_length=2, max_length=6)],
    summary: bool = False,
    as_of: date | None = None,
) -> Comparison:
    """Side-by-side fields and go / no-go per bid; with summary=true, the key differences
    written by the cheap model."""
    records = _records(ctx, bids)
    return compare(
        records,
        load_fields(ctx.settings.config_dir / "fields.yaml"),
        llm=ctx.services().llm if summary else None,
        model=ctx.settings.cheap_model,
        company=load_company(ctx.settings.config_dir / "company.yaml"),
        as_of=as_of,
    )
