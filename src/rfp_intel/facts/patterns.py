"""Extractors for durations, money, percentages, contacts, identifiers and quantities.

Each returns `Match`es with exact character offsets into the text it was given, so every
fact can be checked later as a verbatim substring of its source block.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from rfp_intel.facts.models import FactKind


@dataclass(frozen=True)
class Match:
    kind: FactKind
    start: int
    end: int
    value: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------
# Numbers written as words

_UNITS_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}  # fmt: skip
_TENS_WORDS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}  # fmt: skip
_WORD_NUM = (
    rf"(?:(?:{'|'.join(_TENS_WORDS)})(?:[-\s](?:{'|'.join(_UNITS_WORDS)}))?"
    rf"|{'|'.join(sorted(_UNITS_WORDS, key=len, reverse=True))}"
    r"|one hundred(?: and)?(?: twenty| eighty)?)"
)
_NUM = rf"(?:\d{{1,3}}(?:,\d{{3}})+|\d{{1,4}}|{_WORD_NUM})"


def number_value(token: str) -> int | None:
    token = token.strip().lower().replace(",", "")
    if token.isdigit():
        return int(token)
    if token.startswith("one hundred"):
        rest = token.removeprefix("one hundred").replace("and", "").strip()
        return 100 + (_TENS_WORDS.get(rest, 0) if rest else 0)
    parts = re.split(r"[-\s]+", token)
    total = 0
    for part in parts:
        if part in _TENS_WORDS:
            total += _TENS_WORDS[part]
        elif part in _UNITS_WORDS:
            total += _UNITS_WORDS[part]
        else:
            return None
    return total


# ---------------------------------------------------------------------------------------------
# Durations: "within 45 days of award", "three (3) year agreement", "Net 30"

_UNIT_DAYS = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
_DURATION_RE = re.compile(
    rf"(?<![\w$.])(?P<n>{_NUM})(?:\s*\((?P<paren>\d{{1,4}})\))?[\s-]+"
    r"(?:(?P<qual>business|calendar|working|consecutive)\s+)?"
    r"(?P<unit>hours?|days?|weeks?|months?|years?|yrs?)\b(?:\s?\(s\))?",
    re.I,
)
_ANCHOR_RE = re.compile(
    # used with .match(text, pos), so no "^": it would only match at the start of the string
    r"\s*(?P<rel>of|after|from|following|prior to|before|upon|past)\s+(?:the\s+)?(?:date\s+of\s+)?"
    r"(?:the\s+)?(?:(?:receipt|issuance)\s+of\s+(?:an?\s+|the\s+)?)?"
    r"(?P<anchor>contract award|award|notice to proceed|delivery|order|purchase order|invoice"
    r"|notice|contract execution|execution|acceptance|expiration|contract anniversary"
    r"|anniversary|installation|shipment)\b",
    re.I,
)
_LEAD_RE = re.compile(
    r"(?P<rel>within|no later than|not to exceed|up to|at least|no fewer than|no less than|"
    r"minimum of|maximum of|for a period of|for)\s*(?:a\s+)?(?:total\s+of\s+)?$",
    re.I,
)
_COUNT_RE = re.compile(
    rf"(?P<count>{_NUM})(?:\s*\((?P<cparen>\d{{1,3}})\))?\s+(?:successive|additional|optional|"
    r"renewal|consecutive)?\s*$",
    re.I,
)
_NET_RE = re.compile(r"\bnet[\s-]*(?P<n>\d{1,3})\b(?:\s*days?)?", re.I)


def find_durations(text: str) -> list[Match]:
    out: list[Match] = []
    for m in _DURATION_RE.finditer(text):
        amount = int(m.group("paren")) if m.group("paren") else number_value(m.group("n"))
        if amount is None:
            continue
        unit = m.group("unit").lower().rstrip("s")
        unit = "year" if unit == "yr" else unit
        start, end = m.start(), m.end()
        value: dict[str, Any] = {
            "amount": amount,
            "unit": unit,
            "qualifier": (m.group("qual") or "").lower() or None,
            "days": round(amount * _UNIT_DAYS[unit], 2),
            "relation": None,
            "anchor": None,
            "count": None,
        }
        anchor = _ANCHOR_RE.match(text, end)
        if anchor:
            value["relation"] = anchor.group("rel").lower()
            value["anchor"] = anchor.group("anchor").lower()
            end = anchor.end()
        before = text[max(0, start - 40) : start]
        lead = _LEAD_RE.search(before)
        if lead:
            value["relation"] = lead.group("rel").lower() + (
                f" ... {value['relation']}" if value["relation"] else ""
            )
            start -= len(before) - lead.start()
        else:
            count = _COUNT_RE.search(before)
            if count:
                value["count"] = (
                    int(count.group("cparen"))
                    if count.group("cparen")
                    else number_value(count.group("count"))
                )
                start -= len(before) - count.start()
        out.append(Match(FactKind.DURATION, start, end, value))
    for m in _NET_RE.finditer(text):
        n = int(m.group("n"))
        out.append(
            Match(
                FactKind.DURATION,
                m.start(),
                m.end(),
                {"amount": n, "unit": "day", "days": n, "net_terms": True, "relation": "net"},
            )
        )
    return out


# ---------------------------------------------------------------------------------------------
# Money and percentages

_MONEY_RE = re.compile(
    r"(?<![\w$])(?:US\s?)?\$\s?(?P<amt>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<cents>\d{1,2}))?"
    r"(?:\s?(?P<mult>million|billion|thousand|[kKmM])\b)?"
    r"|(?<![\w.])(?P<amt2>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<cents2>\d{2}))?\s?(?:USD|dollars)\b",
    re.I,
)
_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9}
_PERCENT_RE = re.compile(r"(?<![\w.])(?P<p>\d{1,3}(?:\.\d+)?)\s?(?:%|percent\b|per cent\b)", re.I)


def find_money(text: str) -> list[Match]:
    out: list[Match] = []
    for m in _MONEY_RE.finditer(text):
        amt = m.group("amt") or m.group("amt2")
        cents = m.group("cents") or m.group("cents2")
        amount = float(amt.replace(",", "")) + (float(f"0.{cents}") if cents else 0.0)
        if m.group("mult"):
            amount *= _MULT[m.group("mult").lower()]
        out.append(Match(FactKind.MONEY, m.start(), m.end(), {"amount": amount, "currency": "USD"}))
    return out


def find_percents(text: str) -> list[Match]:
    return [
        Match(FactKind.PERCENT, m.start(), m.end(), {"percent": float(m.group("p"))})
        for m in _PERCENT_RE.finditer(text)
    ]


# ---------------------------------------------------------------------------------------------
# Contacts

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(
    r"(?<![\w/-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}"
    r"(?:\s?(?:x|ext\.?|extension)\s?(?P<ext>\d{1,5}))?(?![\w/-])",
    re.I,
)
_URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"'|]+", re.I)


def find_contacts(text: str) -> list[Match]:
    out: list[Match] = []
    for m in _EMAIL_RE.finditer(text):
        raw = m.group(0).rstrip(".")
        out.append(Match(FactKind.EMAIL, m.start(), m.start() + len(raw), {"email": raw.lower()}))
    for m in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0).split("x")[0].split("ext")[0])
        digits = digits[-10:]
        value: dict[str, Any] = {"phone": f"+1{digits}"}
        if m.group("ext"):
            value["ext"] = m.group("ext")
        out.append(Match(FactKind.PHONE, m.start(), m.end(), value))
    for m in _URL_RE.finditer(text):
        raw = m.group(0).rstrip(".,;:)")
        url = raw if raw.lower().startswith("http") else f"https://{raw}"
        out.append(Match(FactKind.URL, m.start(), m.start() + len(raw), {"url": url}))
    return out


# ---------------------------------------------------------------------------------------------
# Identifiers: solicitation numbers, SKUs, contract and part numbers

_ID_RE = re.compile(r"(?<![\w-])#?(?P<tok>[A-Z0-9](?:[A-Z0-9]|-(?=[A-Z0-9])){3,40})(?![\w-])")
_SKU_RE = re.compile(r"^\d{3}-[A-Z0-9]{4}$")
# Words that make a bare number an identifier: "Request For Proposal 168884", "Reference Number:".
_ID_CUE_RE = re.compile(
    r"(?:#|\bno\.?|\bnumber|\bnum\.?|\bid|\bref(?:erence)?|\bsourcing|\bsolicitation|\bproposal"
    r"|\brfp|\brfq|\bifb|\bitb|\bbid|\bcontract|\bp\.?o\.?|\border|\bproject|\bquote|\bitem"
    r"|\bsku|\bpart|\bmodel)\s*[:#]?\s*$",
    re.I,
)


def find_identifiers(text: str, taken: list[tuple[int, int]]) -> list[Match]:
    """Identifier-shaped tokens not already claimed by a date, phone, amount or address."""
    out: list[Match] = []
    for m in _ID_RE.finditer(text):
        start, end = m.start(), m.end()
        if any(s < end and start < e for s, e in taken):
            continue
        token = m.group("tok")
        has_letter = any(c.isalpha() for c in token)
        has_digit = any(c.isdigit() for c in token)
        if not has_digit:
            continue
        cue = _ID_CUE_RE.search(text[max(0, start - 30) : start])
        if has_letter:
            if len(token.replace("-", "")) < 5:
                continue
            family = "sku" if _SKU_RE.match(token) else "alnum"
        else:
            if len(token.replace("-", "")) < 6 or cue is None:
                continue
            family = "numeric"
        value: dict[str, Any] = {
            "id": token,
            "compact": token.replace("-", ""),
            "family": family,
            "cue": (cue.group(0).strip(" :#").lower() or "#") if cue else None,
        }
        out.append(Match(FactKind.IDENTIFIER, start, end, value))
    return out


# ---------------------------------------------------------------------------------------------
# Quantities

QTY_UNITS = {
    "each",
    "ea",
    "ea.",
    "unit",
    "units",
    "lot",
    "lots",
    "box",
    "boxes",
    "pcs",
    "pieces",
    "set",
    "sets",
}
_NUMBER_CELL_RE = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d{1,7}$")
_QTY_PROSE_RE = re.compile(
    r"\b(?:qty|quantity)\s*(?:of\s*)?[:#]?\s*(?P<n>\d{1,3}(?:,\d{3})+|\d{1,7})\b"
    r"|(?<![\w.,$])(?P<n2>\d{1,3}(?:,\d{3})+|\d{1,7})\s+(?:units?|each|ea\b|pcs|pieces)\b",
    re.I,
)


def is_number_cell(text: str) -> bool:
    return bool(_NUMBER_CELL_RE.match(text.strip()))


def find_prose_quantities(text: str) -> list[Match]:
    out: list[Match] = []
    for m in _QTY_PROSE_RE.finditer(text):
        n = m.group("n") or m.group("n2")
        out.append(Match(FactKind.QUANTITY, m.start(), m.end(), {"qty": int(n.replace(",", ""))}))
    return out
