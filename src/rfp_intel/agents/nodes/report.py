"""The report agent: assembles the record from the state, runs the cross-field consistency
checks, writes the bid summary (the one model call here; a failure leaves the summary marked
failed, not the run), and writes one JSON file per bid. The record is also kept in the state
as `final_output`.
"""

from datetime import UTC, datetime
from typing import Any

from rfp_intel.agents import consistency
from rfp_intel.agents.assemble import assemble, summary_field, summary_inputs
from rfp_intel.agents.outputs import SummaryOut
from rfp_intel.agents.prompts import SUMMARY_SYSTEM, summary_user
from rfp_intel.agents.schema import BidResult, DocumentInfo
from rfp_intel.agents.services import Services
from rfp_intel.agents.state import RunState, add_usage


def report(s: Services, state: RunState) -> dict[str, Any]:
    bid_id = str(state["bid_id"])
    with s.span("agent.report") as span:
        record = assemble(s.catalog, s.store, state)
        documents = [DocumentInfo.model_validate(d) for d in state.get("documents", [])]

        with s.span("agent.validate.consistency") as check_span:
            issues = consistency.check(record.fields, documents)
            consistency.apply(record.fields, issues)
            record.tally.consistency_issues = [i.message for i in issues]
            check_span.set_attribute("agent.issues", record.tally.consistency_issues)

        usage: dict[str, float] = {}
        for spec in s.catalog.fields:
            if spec.type != "summary":
                continue
            with s.span("agent.summary"):
                outcome = s.llm.call(
                    system=SUMMARY_SYSTEM,
                    user=summary_user(summary_inputs(record.fields)),
                    schema=SummaryOut,
                    model=s.settings.cheap_model,
                    effort="low",
                )
            usage = outcome.usage.as_dict()
            text = outcome.output.summary if outcome.output else None
            summary = summary_field(spec, text, outcome.error, record.fields)
            if summary.status == "failed":
                record.tally.failed += 1
                record.errors.append(f"bid_summary: {outcome.error}")
            else:
                record.tally.passed += 1
            record.tally.fields += 1
            record.fields[spec.key] = summary

        by_name = {s.catalog.by_key(k).name: fr for k, fr in record.fields.items()}
        ordered = {
            spec.name: by_name[spec.name] for spec in s.catalog.fields if spec.name in by_name
        }
        result = BidResult(
            bid_id=bid_id,
            run_id=state["run_id"],
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            documents=documents,
            fields=ordered,
            addendum_changes=record.changes,
            validation=record.tally,
            usage=add_usage(dict(state.get("usage", {})), usage),
            models={
                "provider": s.settings.llm_provider,
                "extract": s.settings.extract_model,
                "cheap": s.settings.cheap_model,
            },
            errors=[*state.get("errors", []), *record.errors],
        )
        s.out_dir.mkdir(parents=True, exist_ok=True)
        path = s.out_dir / f"{bid_id}.json"
        path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        tally = result.validation
        span.set_attribute("agent.result_path", str(path))
        span.set_attribute(
            "agent.output",
            f"passed {tally.passed}, failed {tally.failed}, not_found {tally.not_found}, "
            f"conflicts {tally.conflicts}",
        )
    return {
        "result_path": str(path),
        "final_output": result.model_dump(mode="json"),
        "usage": usage,
        "log": [f"report: wrote {path}"],
    }
