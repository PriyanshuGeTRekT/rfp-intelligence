"""Evidence reach: does each expected value reach the extraction prompt?

Runs the extraction graph on the real index with a scripted model that records every prompt
and answers "not found", so no API is called. For each gold rule it reports whether the rule's
expected text appears in the first prompt that asks for the field. A value that never reaches
the prompt cannot be extracted by any model, so this separates retrieval and prompt-budget
problems from model mistakes, and measures a retrieval change in a minute without spending
quota. Fields the model is not asked for (dates resolved from facts, the summary) are skipped.
"""

import re
import tempfile
from pathlib import Path

from pydantic import BaseModel

from rfp_intel.agents.graph import run_extraction
from rfp_intel.agents.llm import ScriptedLLM, estimate_tokens
from rfp_intel.agents.outputs import DraftOut, EventsOut, GroupDraftOut, QueriesOut, SummaryOut
from rfp_intel.agents.services import Services
from rfp_intel.config import Settings
from rfp_intel.eval.extraction import ExtractionGold, Rule
from rfp_intel.search.runtime import Runtime

_FIELD_LINE = re.compile(r"^- (\w+) \(", re.MULTILINE)
_PASSAGE_ID = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)


class FieldReach(BaseModel):
    bid_id: str
    field: str
    asked: bool  # False when no extraction prompt asks for the field
    missing: list[str] = []  # expected patterns not found in the prompt
    passages: int = 0
    prompt_tokens: int = 0

    @property
    def reached(self) -> bool:
        return self.asked and not self.missing


def evidence_text(prompt: str) -> str:
    """The part of an extraction prompt that is document text: candidate facts and passages,
    without the field definitions before them or the passage header lines (a document title in
    a header, such as a bid named "... w/Extended Warranty", would otherwise satisfy a search
    for a warranty requirement)."""
    starts = [i for i in (prompt.find("Candidate facts"), prompt.find("Passages:")) if i >= 0]
    body = prompt[min(starts) :] if starts else prompt
    return "\n".join(line for line in body.splitlines() if not _PASSAGE_ID.match(line))


def missing_patterns(rule: Rule, prompt: str) -> list[str]:
    """The rule's expected text that the prompt lacks: every `patterns` and `items` regex must
    occur; of `any_patterns`, one. Absence rules expect nothing."""
    found = [p for p in [*rule.patterns, *rule.items] if not re.search(p, prompt, re.IGNORECASE)]
    if rule.any_patterns and not any(re.search(p, prompt, re.I) for p in rule.any_patterns):
        found += rule.any_patterns
    return found


def _scripted() -> ScriptedLLM:
    def drafts(system: str, user: str) -> GroupDraftOut:
        keys = _FIELD_LINE.findall(user)
        return GroupDraftOut(
            drafts=[DraftOut(field=k, status="not_found", notes="-") for k in keys]
        )

    return ScriptedLLM(
        {
            "GroupDraftOut": drafts,
            "EventsOut": lambda s, u: EventsOut(events=[]),
            "SummaryOut": lambda s, u: SummaryOut(summary="-"),
            "QueriesOut": lambda s, u: QueriesOut(queries=["-"]),
        }
    )


def evidence_reach(
    settings: Settings, runtime: Runtime, gold: ExtractionGold, bids: list[str]
) -> list[FieldReach]:
    results: list[FieldReach] = []
    for bid_id in bids:
        llm = _scripted()
        with tempfile.TemporaryDirectory() as out:
            run_extraction(Services.build(settings, runtime, llm, Path(out)), bid_id)
        prompts = [c.user for c in llm.calls if c.schema == "GroupDraftOut"]
        for key, rule in gold.bids.get(bid_id, {}).items():
            prompt = next((p for p in prompts if key in _FIELD_LINE.findall(p)), None)
            if prompt is None:
                results.append(FieldReach(bid_id=bid_id, field=key, asked=False))
                continue
            results.append(
                FieldReach(
                    bid_id=bid_id,
                    field=key,
                    asked=True,
                    missing=missing_patterns(rule, evidence_text(prompt)),
                    passages=len(_PASSAGE_ID.findall(prompt)),
                    prompt_tokens=estimate_tokens(prompt),
                )
            )
    return results


def render_reach_markdown(results: list[FieldReach]) -> str:
    asked = [r for r in results if r.asked]
    reached = sum(r.reached for r in asked)
    lines = [
        "# Evidence reach",
        "",
        "Whether each expected value (from `eval/extraction_gold.yaml`) reaches the extraction",
        "prompt that asks for its field, with a scripted model and no API calls",
        "(`uv run rfp eval evidence`). A value that is missing here cannot be extracted by any",
        "model: the cause is retrieval or the prompt budget, not the model.",
        "",
        f"**{reached} of {len(asked)}** fields asked of the model have their expected text in the "
        "prompt.",
        "",
        "| Bid | Field | Reached | Missing | Passages | Prompt tokens |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r.asked:
            lines.append(f"| {r.bid_id} | {r.field} | not asked | | | |")
            continue
        missing = ", ".join(f"`{p}`" for p in r.missing).replace("|", r"\|")
        lines.append(
            f"| {r.bid_id} | {r.field} | {'yes' if r.reached else '**no**'} | {missing} "
            f"| {r.passages} | {r.prompt_tokens} |"
        )
    return "\n".join(lines) + "\n"
