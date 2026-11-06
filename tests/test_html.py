from pathlib import Path

import pytest

from rfp_intel.ingestion.html import parse_html, parse_text
from rfp_intel.ingestion.models import BlockKind, ParsedDocument

PORTAL = """<!doctype html>
<html><head><title>Laptops - Bid Information | Some Portal</title>
<script>var x = "should not appear";</script><style>.a{}</style></head>
<body>
<div id="ajaxIndicator" class="mets-ajax-indicator">Loading...</div>
<div id="accessibilitySkipToContent"><a href="#c">Skip to main content</a></div>
<div class="toolbarTitle"><h1>RFQ-117 - Student Laptops</h1></div>
<div class="hidden" id="deleteNoteDialog"><p>Are you sure you want to delete this note?</p></div>
<div class="share-options"><div>Facebook</div></div>
<main>
  <h3>Basic Information</h3>
  <div class="mets-field"><span class="mets-field-label">Solicitation Number</span>
       <div class="mets-field-body">RFQ-117</div></div>
  <div class="mets-field"><span class="mets-field-label">Closing Date</span>
       <div class="mets-field-body">07/09/2024 03:00 PM EDT</div></div>
  <div class="mets-field"><span class="mets-field-label no-label"></span>
       <div class="mets-field-body">buyer@example.gov</div></div>
  <div class="no-label">Plain text that is not a label</div>
  <h3>More</h3>
  <dl><dt>Delivery:</dt><dd>Within 45 days of award</dd></dl>
  <table><tr><th>Bid Bond</th><td>Not required</td></tr></table>
  <table>
    <tr><th>Item</th><th>Qty</th></tr>
    <tr><td>Laptop</td><td>30</td></tr>
  </table>
  <p>Questions go to<br>the buyer.</p>
</main>
<div class="cookie-banner"><p>We use cookies.</p></div>
<div id="footer">Terms &amp; Conditions</div>
</body></html>"""


@pytest.fixture
def portal(tmp_path: Path) -> ParsedDocument:
    path = tmp_path / "portal.html"
    path.write_text(PORTAL, encoding="utf-8")
    return parse_html(path, bid_id="BidA")


def test_title_from_h1_even_inside_a_toolbar(portal: ParsedDocument) -> None:
    assert portal.title == "RFQ-117 - Student Laptops"


def test_label_value_fields(portal: ParsedDocument) -> None:
    kv = {b.label: b.value for b in portal.blocks if b.kind is BlockKind.KV}
    assert kv["Solicitation Number"] == "RFQ-117"
    assert kv["Closing Date"] == "07/09/2024 03:00 PM EDT"
    assert kv["Delivery"] == "Within 45 days of award"
    assert kv["Bid Bond"] == "Not required"


def test_unlabelled_values_and_no_label_divs_become_paragraphs(portal: ParsedDocument) -> None:
    paragraphs = [b.text for b in portal.blocks if b.kind is BlockKind.PARAGRAPH]
    assert "buyer@example.gov" in paragraphs
    assert "Plain text that is not a label" in paragraphs


def test_page_chrome_is_removed(portal: ParsedDocument) -> None:
    text = portal.text()
    for chrome in (
        "Loading",
        "Skip to main",
        "Are you sure",
        "Facebook",
        "cookies",
        "Terms",
        "should not appear",
    ):
        assert chrome not in text


def test_data_tables_and_sections(portal: ParsedDocument) -> None:
    assert portal.tables[0].rows == [["Item", "Qty"], ["Laptop", "30"]]
    closing = next(b for b in portal.blocks if b.label == "Closing Date")
    assert closing.section_path == ["RFQ-117 - Student Laptops", "Basic Information"]


def test_br_splits_paragraphs(portal: ParsedDocument) -> None:
    paragraphs = [b.text for b in portal.blocks if b.kind is BlockKind.PARAGRAPH]
    assert "Questions go to" in paragraphs
    assert "the buyer." in paragraphs


def test_plain_text_and_markdown(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text(
        "# Scope\n\nDeliver 30 laptops\nwithin 45 days.\n\n## Warranty\n\nThree years.\n",
        encoding="utf-8",
    )
    doc = parse_text(path, bid_id="BidA")
    assert doc.title == "Scope"
    assert [b.text for b in doc.blocks] == [
        "Scope",
        "Deliver 30 laptops within 45 days.",
        "Warranty",
        "Three years.",
    ]
    assert doc.blocks[-1].section_path == ["Scope", "Warranty"]
