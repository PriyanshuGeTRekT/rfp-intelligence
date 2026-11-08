"""The extraction agent: fills one batch of fields from the evidence the retrieval agent
found, in one structured model call, with a verbatim quote and passage id per value.

Passages are fitted to the prompt budget first. Fields with no evidence at all skip the model
and are drafted "not found" (the validator still decides whether the search was thorough).
If the model call fails, every field in the batch gets a draft carrying the error, which the
validator rejects, so the orchestrator retries it instead of the run crashing.
"""

from typing import Any

from rfp_intel.agents.evidence import EvidenceItem, FactCandidate, FieldEvidence
from rfp_intel.agents.fields import FieldSpec
from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.llm import estimate_tokens
from rfp_intel.agents.outputs import GroupDraftOut
from rfp_intel.agents.prompts import (
    EXTRACT_SYSTEM,
    candidate_sections,
    candidates_block,
    extraction_user,
    field_block,
    fit_passages,
)
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import ExtractionTask, RunState
from rfp_intel.agents.validate import FieldDraft

PROMPT_OVERHEAD = 600  # instructions around the passages, in tokens
MIN_PASSAGE_TOKENS = 1_000  # kept for passages, however many candidate facts there are


def _fixed_tokens(fields: list[FieldSpec]) -> int:
    return (
        estimate_tokens(EXTRACT_SYSTEM)
        + PROMPT_OVERHEAD
        + sum(estimate_tokens(field_block(f)) for f in fields)
    )


def _fit_candidates(
    s: Services, fields: list[FieldSpec], candidates: dict[str, list[FactCandidate]]
) -> dict[str, list[FactCandidate]]:
    """Candidate facts that fit the prompt cap with MIN_PASSAGE_TOKENS left for passages,
    taken in turn (each field's first, then second, ...); a fact already kept for another field
    costs nothing, since shared lists are printed once. A product batch can have dozens of part
    numbers; sent whole, they pushed one Bid1 call past the provider's per-minute limit."""
    room = s.settings.llm_max_prompt_tokens - _fixed_tokens(fields) - MIN_PASSAGE_TOKENS
    kept: dict[str, list[FactCandidate]] = {key: [] for key in candidates}
    paid: set[str] = set()
    depth = max((len(c) for c in candidates.values()), default=0)
    for i in range(depth):
        for key, cands in candidates.items():
            if i >= len(cands):
                continue
            fact = cands[i]
            cost = 0 if fact.fact_id in paid else estimate_tokens(candidates_block([fact])) + 1
            if cost > room:
                return kept
            room -= cost
            paid.add(fact.fact_id)
            kept[key].append(fact)
    return kept


def _budget(
    s: Services, fields: list[FieldSpec], candidates: dict[str, list[FactCandidate]]
) -> int:
    """Tokens left for passages: the cap less everything else in the prompt."""
    sections = "\n".join(candidate_sections(fields, candidates))
    fixed = _fixed_tokens(fields) + estimate_tokens(sections)
    return max(MIN_PASSAGE_TOKENS, s.settings.llm_max_prompt_tokens - fixed)


def extract(s: Services, state: RunState) -> dict[str, Any]:
    task = ExtractionTask.model_validate(state["task"])
    evidence = {k: FieldEvidence.model_validate(v) for k, v in state["evidence"].items()}
    specs = [s.catalog.by_key(k) for k in task.fields]
    with s.span(f"agent.extract.{task.batch}") as span:
        span.set_attribute("agent.fields", task.fields)
        span.set_attribute("agent.attempt", task.attempt)
        candidates = _fit_candidates(s, specs, {k: ev.candidates for k, ev in evidence.items()})
        passages: dict[str, list[EvidenceItem]] = fit_passages(
            {k: s.store.many(ev.evidence_ids) for k, ev in evidence.items()},
            _budget(s, specs, candidates),
        )
        for key, items in passages.items():  # record what the model actually read
            evidence[key].evidence_ids = [i.evidence_id for i in items]

        empty = [f for f in specs if not passages.get(f.key) and not candidates.get(f.key)]
        asked = [f for f in specs if f not in empty]
        drafts = {
            f.key: FieldDraft(field=f.key, status="not_found", notes="No passages were retrieved.")
            for f in empty
        }
        usage: dict[str, float] = {}
        if asked:
            outcome = s.llm.call(
                system=EXTRACT_SYSTEM,
                user=extraction_user(asked, passages, candidates, task.reasons, task.hints),
                schema=GroupDraftOut,
                model=s.settings.extract_model,
                effort=s.settings.extract_effort,
            )
            usage = outcome.usage.as_dict()
            drafts |= _drafts(asked, outcome.output, outcome.error)
        span.set_attribute("agent.output", io_attribute({k: d.status for k, d in drafts.items()}))
    return {
        "evidence": {k: ev.model_dump(mode="json") for k, ev in evidence.items()},
        "drafts": {k: d.model_dump(mode="json") for k, d in drafts.items()},
        "attempts": dict.fromkeys(task.fields, task.attempt),
        "usage": usage,
        "errors": [f"extract {task.batch}: {d.error}" for d in drafts.values() if d.error][:1],
        "log": [f"extract {task.batch}: {task.fields} attempt {task.attempt}"],
    }


def _drafts(
    fields: list[FieldSpec], out: GroupDraftOut | None, error: str | None
) -> dict[str, FieldDraft]:
    if out is None:
        return {f.key: FieldDraft(field=f.key, status="not_found", error=error) for f in fields}
    by_key = {f.key: f for f in fields}
    drafts: dict[str, FieldDraft] = {}
    for d in out.drafts:
        spec = by_key.get(d.field)
        if spec is not None and d.field not in drafts:
            drafts[d.field] = d.to_draft(spec.type == "list")
    for key in by_key.keys() - drafts.keys():
        drafts[key] = FieldDraft(
            field=key, status="not_found", error="the model returned no draft for this field"
        )
    return drafts
