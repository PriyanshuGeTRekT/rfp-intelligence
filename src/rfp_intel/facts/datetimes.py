"""Dates, times and US time zones, parsed deterministically.

Time-zone abbreviations are mapped to IANA zones and read as *local time in that zone*. US
bid documents routinely write "CST" for a July deadline, when Central Daylight Time applies;
a literal reading (fixed UTC-6) would put "2:00 PM CST" one hour away from the portal's
"3:00 PM EDT" for the same instant. When the written abbreviation disagrees with the season,
the value carries a `tz_note` and the literal UTC reading as well, so nothing is hidden.
"""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

_MONTH_NAMES = [
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
    ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
    ("oct", "october"), ("nov", "november"), ("dec", "december"),
]  # fmt: skip
MONTHS = {name: i + 1 for i, names in enumerate(_MONTH_NAMES) for name in names}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_MON_CAP = "|".join(
    sorted({n.capitalize() for n in MONTHS} | {n.upper() for n in MONTHS}, key=len, reverse=True)
)

_DATE_WITH_YEAR = [
    # July 9, 2024 / Jul. 9 2024 / June 13th, 2024
    re.compile(
        rf"\b(?P<mon>{_MON})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})\b", re.I
    ),
    # 9 July 2024 / 27-JUN-2024 / 9th of July, 2024
    re.compile(
        rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?[\s-](?P<mon>{_MON})\.?[\s,-]+(?P<y>\d{{4}})\b",
        re.I,
    ),
    # 06/13/2024, 6-13-2024 (US month-first order)
    re.compile(r"(?<![\d/-])(?P<m>\d{1,2})[/-](?P<d>\d{1,2})[/-](?P<y>\d{4})(?![\d/-])"),
    # 2024-06-13
    re.compile(r"(?<![\d-])(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?![\d-])"),
]
# "June 27" with no year: only capitalised month names, so the verb "may" never matches.
_DATE_NO_YEAR = re.compile(
    rf"\b(?P<mon>{_MON_CAP})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*,?\s*\d{{4}})(?![\d:/])"
)

_TIME_RE = re.compile(
    r"(?<![\d:/.$,])(?P<h>[01]?\d|2[0-3])(?::(?P<m>[0-5]\d))?(?::(?P<s>[0-5]\d))?"
    r"(?:\s*(?P<ap>[ap])\.?\s?m\b\.?)?(?![\d%])",
    re.I,
)
_NOON_RE = re.compile(r"\b(?P<w>noon|midnight)\b", re.I)
_TZ_RE = re.compile(
    r"\s*\(?\s*(?P<tz>AK[SD]T|[ECMP][SD]T|[ECMP]T|HST|UTC|GMT"
    r"|(?:Eastern|Central|Mountain|Pacific)(?:\s+(?:Standard|Daylight|Prevailing))?(?:\s+Time)?"
    r"|local\s+time)\b(?:\s*\))?",
    re.I,
)
# What may sit between a date and the time that belongs to it: "July 9, 2024 at 2:00 PM".
_CONNECTOR_RE = re.compile(r"^[\s,]*(?:at|@|by|on|-|\u2013|before|no later than)?[\s,]*$", re.I)

_REGIONS = {
    "E": ("America/New_York", "Eastern"),
    "C": ("America/Chicago", "Central"),
    "M": ("America/Denver", "Mountain"),
    "P": ("America/Los_Angeles", "Pacific"),
}
_STANDARD_OFFSETS = {
    "America/New_York": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Los_Angeles": -8,
    "America/Anchorage": -9,
    "Pacific/Honolulu": -10,
    "UTC": 0,
}


@dataclass(frozen=True)
class Zone:
    iana: str | None
    season: str | None  # "standard" | "daylight" | None when the text does not say


def resolve_zone(tz_text: str) -> Zone:
    key = re.sub(r"\s+", " ", tz_text.strip()).upper()
    if key in ("UTC", "GMT"):
        return Zone("UTC", None)
    if key == "HST":
        return Zone("Pacific/Honolulu", "standard")
    if key in ("AKST", "AKDT"):
        return Zone("America/Anchorage", "standard" if key == "AKST" else "daylight")
    if key == "LOCAL TIME":
        return Zone(None, None)
    if len(key) in (2, 3) and key[0] in _REGIONS:
        season = {"S": "standard", "D": "daylight"}.get(key[1]) if len(key) == 3 else None
        return Zone(_REGIONS[key[0]][0], season)
    word = key.split()[0]
    for iana, region in _REGIONS.values():
        if word == region.upper():
            season = "standard" if "STANDARD" in key else "daylight" if "DAYLIGHT" in key else None
            return Zone(iana, season)
    return Zone(None, None)


@dataclass(frozen=True)
class DateMatch:
    value: date
    start: int
    end: int
    year_inferred: bool = False


@dataclass(frozen=True)
class TimeMatch:
    value: time
    start: int
    end: int  # includes the time zone, when present
    tz_text: str | None = None


@dataclass(frozen=True)
class DateTimeMatch:
    start: int
    end: int
    date: date | None
    time: TimeMatch | None
    year_inferred: bool = False

    def value(self) -> dict[str, Any]:
        return datetime_value(self.date, self.time, year_inferred=self.year_inferred)


def _drop_overlaps[T: (DateMatch, TimeMatch)](matches: list[T]) -> list[T]:
    kept: list[T] = []
    for m in sorted(matches, key=lambda m: (m.start, -(m.end - m.start))):
        if not kept or m.start >= kept[-1].end:
            kept.append(m)
    return kept


def find_dates(text: str, default_year: int | None = None) -> list[DateMatch]:
    """Calendar dates in `text`. "June 27" without a year uses `default_year` when given."""
    found: list[DateMatch] = []
    for rx in _DATE_WITH_YEAR:
        for m in rx.finditer(text):
            g = m.groupdict()
            month = MONTHS[g["mon"].lower()] if g.get("mon") else int(g["m"])
            try:
                found.append(DateMatch(date(int(g["y"]), month, int(g["d"])), m.start(), m.end()))
            except ValueError:
                continue
    if default_year is not None:
        for m in _DATE_NO_YEAR.finditer(text):
            try:
                value = date(default_year, MONTHS[m.group("mon").lower()], int(m.group("d")))
            except ValueError:
                continue
            found.append(DateMatch(value, m.start(), m.end(), year_inferred=True))
    return _drop_overlaps(found)


def find_times(text: str) -> list[TimeMatch]:
    found: list[TimeMatch] = []
    for m in _TIME_RE.finditer(text):
        hour, minute, ap = int(m.group("h")), m.group("m"), m.group("ap")
        if minute is None and ap is None:
            continue  # a bare number is not a time
        if ap:
            if not 1 <= hour <= 12:
                continue
            hour = hour % 12 + (12 if ap.lower() == "p" else 0)
        value = time(hour, int(minute or 0), int(m.group("s") or 0))
        found.append(_with_zone(text, value, m.start(), m.end()))
    for m in _NOON_RE.finditer(text):
        value = time(12) if m.group("w").lower() == "noon" else time(0)
        found.append(_with_zone(text, value, m.start(), m.end()))
    return _drop_overlaps(found)


def _with_zone(text: str, value: time, start: int, end: int) -> TimeMatch:
    tz = _TZ_RE.match(text, end)
    if tz:
        return TimeMatch(value, start, tz.end(), tz.group("tz"))
    return TimeMatch(value, start, end)


def find_datetimes(text: str, default_year: int | None = None) -> list[DateTimeMatch]:
    """Dates paired with their times.

    A time right after a date ("27-JUN-2024 14:00:00", "July 9, 2024 at 2:00 PM CST") belongs
    to it. A time left over may belong to the nearest date without a time in the same text,
    which handles "at 2:00 PM CST via TEAMS video conference on June 10, 2024".
    """
    dates = find_dates(text, default_year)
    times = [t for t in find_times(text) if not any(d.start <= t.start < d.end for d in dates)]
    pairs: dict[int, TimeMatch] = {}
    used: set[int] = set()
    for di, d in enumerate(dates):
        for ti, t in enumerate(times):
            if ti in used or t.start < d.end:
                continue
            if t.start - d.end <= 20 and _CONNECTOR_RE.match(text[d.end : t.start]):
                pairs[di] = t
                used.add(ti)
            break
    for ti, t in enumerate(times):
        if ti in used:
            continue
        candidates = [
            (abs(t.start - d.end) if t.start >= d.end else abs(d.start - t.end), di)
            for di, d in enumerate(dates)
            if di not in pairs
        ]
        if candidates:
            distance, di = min(candidates)
            if distance <= 120:
                pairs[di] = t
                used.add(ti)

    out: list[DateTimeMatch] = []
    for di, d in enumerate(dates):
        paired = pairs.get(di)
        start = min(d.start, paired.start) if paired else d.start
        end = max(d.end, paired.end) if paired else d.end
        out.append(DateTimeMatch(start, end, d.value, paired, d.year_inferred))
    for ti, t in enumerate(times):
        if ti not in used:
            out.append(DateTimeMatch(t.start, t.end, None, t))
    return sorted(out, key=lambda m: m.start)


def _offset(delta: timedelta | None) -> str | None:
    if delta is None:
        return None
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def _utc(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def datetime_value(
    d: date | None, t: TimeMatch | None, *, year_inferred: bool = False
) -> dict[str, Any]:
    """The normalized JSON stored for a date/time fact."""
    zone = resolve_zone(t.tz_text) if t and t.tz_text else Zone(None, None)
    value: dict[str, Any] = {
        "date": d.isoformat() if d else None,
        "time": t.value.strftime("%H:%M") if t else None,
        "tz_text": t.tz_text if t else None,
        "iana": zone.iana,
        "has_date": d is not None,
        "has_time": t is not None,
        "has_tz": zone.iana is not None,
        "year_inferred": year_inferred,
        "local": None,
        "utc": None,
    }
    if d is None or t is None:
        return value
    local = datetime.combine(d, t.value)
    value["local"] = local.isoformat()
    if zone.iana is None:
        return value
    aware = local.replace(tzinfo=ZoneInfo(zone.iana))
    value["utc"] = _utc(aware)
    value["tz_effective"] = aware.tzname()
    value["utc_offset"] = _offset(aware.utcoffset())
    in_dst = bool(aware.dst())
    if (zone.season == "standard" and in_dst) or (zone.season == "daylight" and not in_dst):
        hours = _STANDARD_OFFSETS.get(zone.iana, 0) + (1 if zone.season == "daylight" else 0)
        literal = local.replace(tzinfo=None) - timedelta(hours=hours)
        value["utc_literal"] = literal.strftime("%Y-%m-%dT%H:%M:%SZ")
        value["tz_note"] = (
            f"'{t.tz_text}' is written for a date when {aware.tzname()} applies; read as local "
            f"time in {zone.iana} (UTC{value['utc_offset']}). A literal {t.tz_text} reading would "
            f"be {value['utc_literal']}."
        )
    return value
