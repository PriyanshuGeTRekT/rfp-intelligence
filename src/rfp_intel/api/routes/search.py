"""Search: the retrieval engine on its own, with filters and a choice of configuration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from rfp_intel.api.context import AppContext, context
from rfp_intel.api.schemas import SearchConfigInfo
from rfp_intel.search.models import CONFIG_DESCRIPTIONS, DEFAULT_CONFIG, NAMED_CONFIGS, SearchResult

router = APIRouter(tags=["search"])
Ctx = Annotated[AppContext, Depends(context)]


@router.get("/search")
def search(
    ctx: Ctx,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    bid_id: str | None = None,
    doc_type: Annotated[list[str] | None, Query()] = None,
    addendum_number: int | None = None,
    top_k: Annotated[int | None, Query(ge=1, le=50)] = None,
    k: Annotated[int | None, Query(ge=1, le=50, description="Alias of top_k")] = None,
    config: str = DEFAULT_CONFIG,
) -> SearchResult:
    """Hybrid search. Every hit carries file, pages, chunk text and per-list ranks."""
    if config not in NAMED_CONFIGS:
        raise HTTPException(
            status_code=422, detail=f"config must be one of {sorted(NAMED_CONFIGS)}"
        )
    runtime = ctx.runtime()
    if NAMED_CONFIGS[config].rerank and runtime.reranker is None:
        raise HTTPException(status_code=422, detail="this server was started without a reranker")
    runtime.indexer().index_new_bids(ctx.settings.data_dir, [bid_id] if bid_id else None)
    return runtime.engine().search(
        q,
        bid_id=bid_id,
        doc_types=doc_type,
        addendum_number=addendum_number,
        k=top_k or k or 5,
        config=config,
    )


@router.get("/search/configs")
def configs(ctx: Ctx) -> list[SearchConfigInfo]:
    """Retrieval configurations this server can run."""
    has_reranker = ctx.runtime().reranker is not None
    return [
        SearchConfigInfo(
            name=name,
            description=CONFIG_DESCRIPTIONS.get(name, ""),
            default=name == DEFAULT_CONFIG,
        )
        for name, cfg in NAMED_CONFIGS.items()
        if has_reranker or not cfg.rerank
    ]
