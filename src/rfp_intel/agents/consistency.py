"""Cross-field consistency checks: the part of validation that needs all fields at once.

Per-field checks (quotes verbatim, value supported, not-found justified) run in the validator
node as drafts arrive. These run when every field is final, on dates that must be in order:

- the pre-bid meeting is before the due date;
- the due date is after the solicitation was issued;
- every addendum is dated on or before the due date it leads to;
- a delivery date stated as a calendar date is after the due date.

A failed check does not delete a value: the field it most likely concerns drops to tier E
("sources differ and nothing explains it") with the reason in its notes, and the issue is
listed in the validation tally.
"""

from datetime import date

from pydantic import BaseModel

from rfp_intel.agents.confidence import TIERS
from rfp_intel.agents.schema import DocumentInfo, FieldResult
from rfp_intel.facts.datetimes import find_dates


class Issue(BaseModel):
    field: str  # the field to downgrade
    message: str


def _date_of(fr: FieldResult | None) -> date | None:
    if fr is None or fr.status not in ("found", "conflict"):
        return None
    if fr.normalized and fr.normalized.get("date"):
        return date.fromisoformat(fr.normalized["date"])
    return None


def _calendar_date(fr: FieldResult | None) -> date | None:
    """A date written in a text value ("by August 30, 2024"); None for relative windows."""
    if fr is None or fr.status != "found" or not isinstance(fr.value, str):
        return None
    matches = find_dates(fr.value)
    return matches[0].value if matches else None


def check(fields: dict[str, FieldResult], documents: list[DocumentInfo]) -> list[Issue]:
    """`fields` is keyed by field key."""
    issues: list[Issue] = []
    due = _date_of(fields.get("due_date"))
    if due is None:
        return issues

    pre_bid = _date_of(fields.get("pre_bid_meeting"))
    if pre_bid is not None and pre_bid > due:
        issues.append(
            Issue(
                field="pre_bid_meeting",
                message=f"pre-bid meeting {pre_bid} is after the due date {due}",
            )
        )

    issued = [d.doc_date for d in documents if d.doc_type == "rfp" and d.doc_date is not None]
    if issued and min(issued) > due:
        issues.append(
            Issue(
                field="due_date",
                message=f"due date {due} is before the solicitation was issued ({min(issued)})",
            )
        )

    for d in documents:
        if d.doc_type == "addendum" and d.doc_date is not None and d.doc_date > due:
            issues.append(
                Issue(
                    field="due_date",
                    message=f"{d.file} is dated {d.doc_date}, after the due date {due}",
                )
            )

    delivery = _calendar_date(fields.get("delivery_date"))
    if delivery is not None and delivery < due:
        issues.append(
            Issue(
                field="delivery_date",
                message=f"delivery date {delivery} is before the due date {due}",
            )
        )
    return issues


def apply(fields: dict[str, FieldResult], issues: list[Issue]) -> None:
    """Downgrade the fields the issues concern, in place."""
    for issue in issues:
        fr = fields.get(issue.field)
        if fr is None:
            continue
        fr.tier, fr.confidence = "E", TIERS["E"]
        note = f"Consistency check failed: {issue.message}."
        fr.notes = f"{fr.notes} {note}" if fr.notes else note
