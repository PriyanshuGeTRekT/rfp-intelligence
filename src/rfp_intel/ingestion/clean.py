"""Text normalization shared by every parser."""

import re
import unicodedata

# Zero-width characters, BOM, soft hyphen and the replacement character from bad encodings.
_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\ufffd]")
_DOT_LEADER_RE = re.compile(r"(?:\.\s?){4,}")  # "......" fill leaders; NFKC turns "…" into "..."
_RULE_RE = re.compile(r"[-=_~*]{5,}")  # drawn rules made of characters
_SPACE_RE = re.compile("[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
# Bullet glyphs, including U+F0B7, the Symbol-font bullet that Word-made PDFs often contain.
_BULLETS = {"\u2022", "\u25e6", "\u25aa", "\u25a0", "\u25cf", "\u25cb", "-", "\u2013", "*", "\u00b7", "\uf0b7", "o"}  # fmt: skip  # noqa: E501

# A word broken across lines: "require-" + "ments". Only a letter right before the hyphen and a
# lowercase letter after it, so "Monitor -" + "Touch" and "Non-" + "Touch" are left alone.
_HYPHEN_END_RE = re.compile(r"[A-Za-z]-$")
# The tail of an email address or URL that wrapped onto the next line.
_LINK_TAIL_RE = re.compile(r"(?:\S+@\S*|https?://\S*|www\.\S*)$")


def normalize_text(text: str) -> str:
    """NFKC, strip invisible characters, drop dot leaders and character rules, squeeze spaces."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _DOT_LEADER_RE.sub(" ", text)
    text = _RULE_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def is_bullet(text: str) -> bool:
    return text.strip() in _BULLETS


def join_lines(prev: str, nxt: str) -> str:
    """Join two wrapped lines of the same paragraph."""
    prev, nxt = prev.rstrip(), nxt.lstrip()
    if not prev:
        return nxt
    if not nxt:
        return prev
    if is_bullet(prev):
        return f"{prev} {nxt}"
    if _HYPHEN_END_RE.search(prev) and nxt[0].islower():
        return prev[:-1] + nxt
    link = _LINK_TAIL_RE.search(prev)
    if link and (nxt[0] in "./@-_" or link.group(0)[-1] in "./@-_"):
        return prev + nxt
    return f"{prev} {nxt}"


def page_marker_key(text: str) -> str:
    """Key for spotting repeated headers and footers: case-folded, digits masked."""
    return re.sub(r"\d+", "#", _SPACE_RE.sub(" ", text).strip().casefold())


_PAGE_NUMBER_RE = re.compile(
    r"^(?:page\s*)?#(?:\s*(?:of|/|\|)\s*#)?$|^-\s*#\s*-$",
)


def is_page_number(text: str) -> bool:
    """True for bare page markers: "Page 3 of 40", "Page 1 | 5", "3", "- 3 -"."""
    return bool(_PAGE_NUMBER_RE.match(page_marker_key(text)))
