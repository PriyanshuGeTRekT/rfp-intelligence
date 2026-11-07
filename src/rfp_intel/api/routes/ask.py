"""Questions: answered by the agent graph (the planner routes them to the Q&A agent)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rfp_intel.agents.graph import run_question
from rfp_intel.agents.qa import QAResult
from rfp_intel.api.context import AppContext, context
from rfp_intel.api.schemas import AskRequest

router = APIRouter(tags=["ask"])
Ctx = Annotated[AppContext, Depends(context)]


@router.post("/ask")
def ask(body: AskRequest, ctx: Ctx) -> QAResult:
    """Answer a question with verbatim citations, or "Not found in documents."."""
    result, _ = run_question(ctx.services(), body.question, bid_id=body.bid_id)
    return result
