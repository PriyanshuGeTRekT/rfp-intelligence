"""Confidence as a decision table, not a weighted formula.

Each tier is a sentence that can be said out loud, and its number is a label for that tier,
not a probability. Whether the tiers are ordered correctly is checked against the gold set
(accuracy per tier), and a miscalibrated tier is fixed by changing its conditions.

| Tier | Conditions                                                                 | Confidence |
|------|----------------------------------------------------------------------------|------------|
| A    | grounded and well-formed, and two documents agree or an addendum sets it     | 0.95       |
| B    | grounded and well-formed, one source                                       | 0.85       |
| C    | grounded only loosely, from an OCR page, or assembled from two sources       | 0.70       |
| D    | sources differ, but an addendum explains the difference                     | 0.60       |
| E    | sources differ and nothing explains it                                      | 0.40       |
| NF-1 | not found, and the search for it was thorough                               | 0.80       |
| NF-2 | not found, but the search did not meet the coverage bar                     | 0.50       |
| X    | the validator rejected every attempt                                       | 0.20       |
"""

from pydantic import BaseModel

TIERS: dict[str, float] = {
    "A": 0.95,
    "B": 0.85,
    "C": 0.70,
    "D": 0.60,
    "E": 0.40,
    "NF-1": 0.80,
    "NF-2": 0.50,
    "X": 0.20,
}
ORDER = ["A", "B", "C", "D", "E"]


class Evidence(BaseModel):
    """What the validator and reconciler learned about one field's value."""

    found: bool
    grounded: bool = True  # every quote is a verbatim substring of its evidence
    well_formed: bool = True  # the value parses as its field type and matches the quotes
    loose: bool = False  # grounded through a normalized or partial match only
    ocr: bool = False
    distinct_documents: int = 1  # documents whose quotes support the value
    set_by_addendum: bool = False
    assembled: bool = False  # e.g. date from the RFP, time from the portal
    explained_difference: bool = False
    unexplained_conflict: bool = False
    confirmed_by_addendum: bool = False
    coverage_met: bool = False  # for not-found: enough searches, no typed facts
    rejected: bool = False


def tier(e: Evidence) -> str:
    if e.rejected:
        return "X"
    if not e.found:
        return "NF-1" if e.coverage_met else "NF-2"
    if e.unexplained_conflict:
        return "E"
    if e.explained_difference:
        base = "D"
    elif not (e.grounded and e.well_formed) or e.loose or e.ocr or e.assembled:
        base = "C"
    elif e.distinct_documents >= 2 or e.set_by_addendum:
        base = "A"
    else:
        base = "B"
    if e.confirmed_by_addendum and base in ORDER and base != "A":
        base = ORDER[ORDER.index(base) - 1]  # an addendum confirming the value moves it up one
    if e.ocr and base in ("A", "B"):
        base = "C"  # OCR text caps at C
    return base


def score(e: Evidence) -> tuple[str, float]:
    t = tier(e)
    return t, TIERS[t]
