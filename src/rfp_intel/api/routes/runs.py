"""Runs: extraction jobs and the trace each agent run leaves behind."""

import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from rfp_intel.api.context import AppContext, context
from rfp_intel.api.schemas import Job, TraceSpan

router = APIRouter(tags=["runs"])
Ctx = Annotated[AppContext, Depends(context)]
_RUN_ID_RE = re.compile(r"^[0-9A-Za-z-]{6,64}$")


@router.get("/jobs")
def list_jobs(ctx: Ctx) -> list[Job]:
    return ctx.jobs.all()


@router.get("/jobs/{job_id}")
def get_job(job_id: str, ctx: Ctx) -> Job:
    job = ctx.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return job


@router.get("/runs/{run_id}/trace")
def get_trace(run_id: str, ctx: Ctx) -> list[TraceSpan]:
    """Every span of one agent run, in start order (inputs, outputs, tokens, latency)."""
    if not _RUN_ID_RE.match(run_id):
        raise HTTPException(status_code=400, detail="invalid run id")
    path = ctx.settings.traces_dir / f"{run_id}.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no trace for this run")
    spans = [
        TraceSpan.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return sorted(spans, key=lambda sp: sp.start or "")
