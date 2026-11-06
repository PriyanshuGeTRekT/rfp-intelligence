import pytest

from rfp_intel.ingestion.clean import is_page_number, join_lines, normalize_text, page_marker_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Due​ Date", "Due Date"),
        ("ﬁnal  oﬀer", "final offer"),  # ligatures via NFKC
        ("Type ……………………… Provide", "Type Provide"),  # dot leaders
        ("Name ---------------------- here", "Name here"),
        ("bad�char", "badchar"),
        ("  spaced\u00a0\tout  ", "spaced out"),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


@pytest.mark.parametrize(
    ("prev", "nxt", "expected"),
    [
        ("meet the require-", "ments listed", "meet the requirements listed"),
        ("Display Monitor -", "Touch", "Display Monitor - Touch"),
        ("(Non-", "Touch)", "(Non- Touch)"),
        (
            "contact thawkins@treasurer.state.md",
            ".us today",
            "contact thawkins@treasurer.state.md.us today",
        ),
        ("see https://example.org/bids/", "rfp-117", "see https://example.org/bids/rfp-117"),
        ("•", "Bullet text", "• Bullet text"),
        ("first line", "second line", "first line second line"),
    ],
)
def test_join_lines(prev: str, nxt: str, expected: str) -> None:
    assert join_lines(prev, nxt) == expected


@pytest.mark.parametrize("text", ["Page 3 of 40", "Page 1 | 5", "12", "- 4 -", "page 2/9"])
def test_page_numbers(text: str) -> None:
    assert is_page_number(text)


@pytest.mark.parametrize(
    "text", ["Page Layout Rules", "Section 3", "2024-117", "Dallas ISD rev 2.0"]
)
def test_not_page_numbers(text: str) -> None:
    assert not is_page_number(text)


def test_marker_key_masks_digits() -> None:
    assert page_marker_key("Dallas ISD rev 1.0") == page_marker_key("Dallas  ISD rev 2.0")
