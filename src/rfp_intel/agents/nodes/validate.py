"""The validator / critic: deterministic checks on every new draft (cited, quotes grounded,
value supported by its quotes and well-formed for its type, "not found" justified by a
thorough search, the model call succeeded). A failed field is queued for another retrieval
and extraction round with the failure as its reason, until `max_retries`. Cross-field
consistency is checked in the report, once every field is final (`agents/consistency.py`).
"""

from typing import Any

from rfp_intel.agents.evidence import FieldEvidence
from rfp_intel.agents.guarded import io_attribute
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState
from rfp_intel.agents.validate import Check, FieldDraft, ValidationResult, ground_draft, validate


def validate_drafts(s: Services, state: RunState) -> dict[str, Any]:
    attempts = state.get("attempts", {})
    done = state.get("validations", {})
    resolved = state.get("resolved", {})
    with s.span("agent.validate") as span:
        validations: dict[str, dict[str, Any]] = {}
        grounded: dict[str, dict[str, Any]] = {}
        retries: list[dict[str, Any]] = []
        for key, raw in state.get("drafts", {}).items():
            attempt = attempts.get(key, 1)
            if key in done and done[key].get("attempt") == attempt:
                continue  # validated in an earlier round; unchanged since
            evidence = FieldEvidence.model_validate(state["evidence"][key])
            draft = ground_draft(FieldDraft.model_validate(raw), s.store, evidence.evidence_ids)
            grounded[key] = draft.model_dump(mode="json")
            if key in resolved and draft.status == "not_found" and not draft.error:
                # An enriched date: the reconciler's value stands; nothing more was found.
                check = Check(name="resolved_by_reconciler", passed=True)
                result = ValidationResult(field=key, passed=True, checks=[check])
            else:
                result = validate(draft, s.catalog.by_key(key), s.store, evidence)
            validations[key] = result.model_dump(mode="json") | {"attempt": attempt}
            if not result.passed and attempt <= s.settings.max_retries:
                retries.append(
                    {
                        "field": key,
                        "reason": result.retry_reason or "rejected",
                        "attempt": attempt + 1,
                    }
                )
        failed = sorted(k for k, v in validations.items() if not v["passed"])
        span.set_attribute("agent.checked", sorted(validations))
        span.set_attribute("agent.failed", failed)
        span.set_attribute("agent.output", io_attribute(retries))
    return {
        "drafts": grounded,  # quotes replaced by the exact source text they reproduce
        "validations": validations,
        "retries": retries,
        "log": [
            f"validate: {len(validations)} checked, {len(failed)} failed, "
            f"retrying {[r['field'] for r in retries]}"
        ],
    }
