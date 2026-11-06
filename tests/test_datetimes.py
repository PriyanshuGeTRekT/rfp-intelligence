from datetime import date, time

import pytest

from rfp_intel.facts.datetimes import find_dates, find_datetimes, find_times, resolve_zone


def test_date_formats() -> None:
    text = "Due July 9, 2024; meeting 10-JUN-2024 14:00; posted 05/29/2024; iso 2024-06-13; bad 13/45/2024"
    assert [m.value for m in find_dates(text)] == [
        date(2024, 7, 9),
        date(2024, 6, 10),
        date(2024, 5, 29),
        date(2024, 6, 13),
    ]


def test_month_day_without_year_needs_a_default_year() -> None:
    assert find_dates("Bids due June 27 by noon") == []
    (m,) = find_dates("Bids due June 27 by noon", default_year=2024)
    assert m.value == date(2024, 6, 27)
    assert m.year_inferred


def test_the_verb_may_is_not_a_month() -> None:
    assert find_dates("Vendors may 10 times submit", default_year=2024) == []


@pytest.mark.parametrize(
    ("text", "expected", "tz"),
    [
        ("at 2:00 PM CST", time(14, 0), "CST"),
        ("by 3 p.m. Eastern Time", time(15, 0), "Eastern Time"),
        ("14:00:00", time(14, 0), None),
        ("02:00 PM EDT", time(14, 0), "EDT"),
        ("12:00 AM", time(0, 0), None),
        ("noon (CT)", time(12, 0), "CT"),
    ],
)
def test_times(text: str, expected: time, tz: str | None) -> None:
    (t,) = find_times(text)
    assert t.value == expected
    assert t.tz_text == tz


@pytest.mark.parametrize("text", ["12 cores", "4.3 GHz", "16:9 display ratio", "45 days", "13 PM"])
def test_not_times(text: str) -> None:
    assert find_times(text) == []


@pytest.mark.parametrize(
    ("tz", "iana", "season"),
    [
        ("CST", "America/Chicago", "standard"),
        ("CDT", "America/Chicago", "daylight"),
        ("CT", "America/Chicago", None),
        ("Central Daylight Time", "America/Chicago", "daylight"),
        ("EDT", "America/New_York", "daylight"),
        ("Pacific Time", "America/Los_Angeles", None),
        ("MST", "America/Denver", "standard"),
        ("UTC", "UTC", None),
        ("local time", None, None),
    ],
)
def test_zone_resolution(tz: str, iana: str | None, season: str | None) -> None:
    zone = resolve_zone(tz)
    assert (zone.iana, zone.season) == (iana, season)


def test_cst_in_july_is_read_as_central_local_time() -> None:
    """The Bid1 trap: Addendum 2 says 2:00 PM CST, the portal says 3:00 PM EDT."""
    (addendum,) = find_datetimes(
        "The new due date for this RFP will be July 9, 2024 at 2:00 PM CST."
    )
    (portal,) = find_datetimes("Closing Date: 07/09/2024 03:00 PM EDT")
    a, p = addendum.value(), portal.value()
    assert a["utc"] == p["utc"] == "2024-07-09T19:00:00Z"
    assert a["tz_effective"] == "CDT"
    assert a["utc_offset"] == "-05:00"
    assert a["utc_literal"] == "2024-07-09T20:00:00Z"
    assert "CDT applies" in a["tz_note"]
    assert "tz_note" not in p


def test_cdt_in_january_gets_a_note_too() -> None:
    (m,) = find_datetimes("January 15, 2025 at 10:00 AM CDT")
    v = m.value()
    assert v["utc"] == "2025-01-15T16:00:00Z"
    assert v["utc_literal"] == "2025-01-15T15:00:00Z"


def test_time_after_date_pairs_with_it() -> None:
    (m,) = find_datetimes("Solicitation Due | 27-JUN-2024 14:00:00")
    v = m.value()
    assert v["local"] == "2024-06-27T14:00:00"
    assert v["utc"] is None and not v["has_tz"]


def test_time_before_date_in_the_same_sentence_pairs_with_it() -> None:
    text = "A pre-proposal meeting will be held at 2:00 PM CST via TEAMS video conference on June 10, 2024."
    (m,) = find_datetimes(text)
    assert text[m.start : m.end] == "2:00 PM CST via TEAMS video conference on June 10, 2024"
    assert m.value()["utc"] == "2024-06-10T19:00:00Z"


def test_two_dates_two_times() -> None:
    text = "Questions by 06/11/2024 05:00 PM EDT; answers posted 06/13/2024 06:00 PM EDT."
    values = [m.value()["local"] for m in find_datetimes(text)]
    assert values == ["2024-06-11T17:00:00", "2024-06-13T18:00:00"]


def test_lone_time_and_lone_date() -> None:
    text = "Office hours 8:00 AM to 5:00 PM."
    assert [m.value()["time"] for m in find_datetimes(text)] == ["08:00", "17:00"]
    (d,) = find_datetimes("Issued 05/24/2024")
    assert d.value()["date"] == "2024-05-24" and not d.value()["has_time"]
