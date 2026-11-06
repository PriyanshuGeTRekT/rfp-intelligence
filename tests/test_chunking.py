import itertools
from collections.abc import Callable

import pytest

from rfp_intel.facts.extract import extract_facts
from rfp_intel.facts.labels import FactTypeConfig, load_fact_types
from rfp_intel.ingestion.models import Block, BlockKind, DocType, ParsedDocument, Table
from rfp_intel.search.chunking import ChunkConfig, approx_tokens, chunk_document, is_boilerplate
from rfp_intel.search.models import Chunk, ChunkType

from .conftest import REPO_ROOT

MakeDoc = Callable[..., ParsedDocument]
SMALL = ChunkConfig(target_tokens=60, max_tokens=80, overlap_tokens=15, min_tokens=8)


@pytest.fixture(scope="module")
def facts_config() -> FactTypeConfig:
    return load_fact_types(REPO_ROOT / "config" / "fact_types.yaml")


def heading(text: str, path: list[str], level: int = 2, page: int = 1) -> Block:
    return Block(
        kind=BlockKind.HEADING, text=text, page=page, heading_level=level, section_path=path
    )


def para(text: str, path: list[str], page: int = 1) -> Block:
    return Block(kind=BlockKind.PARAGRAPH, text=text, page=page, section_path=path)


def doc_with(
    make_doc: MakeDoc, blocks: list[Block], tables: list[Table] | None = None, **kw: object
) -> ParsedDocument:
    doc = make_doc(title="Request for Quotation 117", **kw)
    doc.blocks = blocks
    doc.tables = tables or []
    doc.doc_type = DocType.RFP
    return doc


def _covers(doc: ParsedDocument, chunk: Chunk) -> None:
    """Every span is a real slice of its block, and the chunk text is made of those slices."""
    for s in chunk.spans:
        piece = doc.blocks[s.block_index].text[s.start : s.end]
        assert piece and piece in chunk.text


def test_sections_never_mix_and_headings_lead(make_doc: MakeDoc) -> None:
    a, b = ["Scope"], ["Delivery"]
    long_a = " ".join(f"Sentence {i} about the scope of work for laptops." for i in range(12))
    doc = doc_with(
        make_doc,
        [
            heading("Scope", a),
            para(long_a, a),
            heading("Delivery", b),
            para("Deliver within 45 days of award.", b),
        ],
    )
    chunks = chunk_document(doc, [], SMALL)
    assert all(approx_tokens(c.text) <= SMALL.max_tokens for c in chunks)
    scope = [c for c in chunks if c.section_path == a]
    assert len(scope) >= 2
    assert scope[0].text.startswith("Scope")
    delivery = chunks[-1]
    assert delivery.section_path == b and delivery.text.startswith("Delivery")
    assert "45 days" not in " ".join(c.text for c in scope)
    for c in chunks:
        _covers(doc, c)


def test_long_prose_overlaps_between_chunks(make_doc: MakeDoc) -> None:
    path = ["Terms"]
    sentences = [
        f"Clause {i} sets out obligation number {i} for the awarded vendor." for i in range(14)
    ]
    doc = doc_with(make_doc, [para(" ".join(sentences), path)])
    chunks = chunk_document(doc, [], SMALL)
    assert len(chunks) >= 3
    for prev, nxt in itertools.pairwise(chunks):
        last_sentence = prev.text.split(". ")[-1].rstrip(".")
        assert last_sentence in nxt.text  # the last sentence is repeated at the next start


def test_small_sibling_sections_merge_with_their_headings(make_doc: MakeDoc) -> None:
    root = ["1 Requirements"]
    blocks = [
        heading("Deployment Services", [*root, "Deployment Services"], 3),
        para("White glove delivery is required.", [*root, "Deployment Services"]),
        heading("Warranty", [*root, "Warranty"], 3),
        para("Three-year warranty minimum.", [*root, "Warranty"]),
    ]
    (chunk,) = chunk_document(doc_with(make_doc, blocks), [], SMALL)
    assert chunk.section_path == root
    assert (
        chunk.text
        == "Deployment Services\n\nWhite glove delivery is required.\n\nWarranty\n\nThree-year warranty minimum."
    )


def test_large_table_repeats_its_header(make_doc: MakeDoc) -> None:
    rows = [["Description", "SKU"]] + [
        [f"Component number {i} for the laptop build", f"{100 + i}-ABCD"] for i in range(30)
    ]
    table = Table(table_id=0, page=2, rows=rows, method="t")
    path = ["Quote"]
    doc = doc_with(
        make_doc,
        [
            heading("Quote", path),
            Block(
                kind=BlockKind.TABLE, text=table.to_text(), page=2, table_id=0, section_path=path
            ),
        ],
        [table],
    )
    chunks = chunk_document(doc, [], SMALL)
    assert len(chunks) > 2 and {c.chunk_type for c in chunks} == {ChunkType.TABLE_ROWS}
    assert chunks[0].text.startswith("Quote\n\nDescription | SKU")  # heading carried into the table
    for c in chunks[1:]:
        assert c.text.startswith("Description | SKU")
    assert sum(c.text.count("-ABCD") for c in chunks) == 30  # every row exactly once


def test_small_table_is_one_chunk(make_doc: MakeDoc) -> None:
    table = Table(table_id=0, page=1, rows=[["Item", "Qty"], ["Laptop", "30"]], method="t")
    doc = doc_with(
        make_doc, [Block(kind=BlockKind.TABLE, text=table.to_text(), page=1, table_id=0)], [table]
    )
    (chunk,) = chunk_document(doc, [], SMALL)
    assert chunk.chunk_type is ChunkType.TABLE and chunk.text == "Item | Qty\nLaptop | 30"


def test_questions_and_answers_are_their_own_chunks(make_doc: MakeDoc) -> None:
    path = ["Addendum 1"]
    blocks = [
        para("The purpose of this addendum is to answer vendor questions.", path),
        para(
            "11. Will the district extend the deadline?\nAnswer: The district does not anticipate extending the deadline.",
            path,
        ),
        para(
            "12. Is etching required on monitors?\nAnswer: Etching is required on laptops only.",
            path,
        ),
    ]
    chunks = chunk_document(doc_with(make_doc, blocks), [], SMALL)
    qa = [c for c in chunks if c.chunk_type is ChunkType.QA_PAIR]
    assert [c.text.split(".")[0] for c in qa] == ["11", "12"]
    assert "Answer: Etching is required on laptops only." in qa[1].text


def test_portal_fields_group_into_one_chunk(make_doc: MakeDoc) -> None:
    path = ["Bid", "Dates"]
    kv = [
        Block(
            kind=BlockKind.KV,
            text="Publication: 05/29/2024",
            page=1,
            label="Publication",
            value="05/29/2024",
            section_path=path,
        ),
        Block(
            kind=BlockKind.KV,
            text="Closing Date: 07/09/2024 03:00 PM EDT",
            page=1,
            label="Closing Date",
            value="x",
            section_path=path,
        ),
    ]
    (chunk,) = chunk_document(doc_with(make_doc, [heading("Dates", path), *kv]), [], SMALL)
    assert chunk.chunk_type is ChunkType.KV
    assert chunk.text == "Dates\n\nPublication: 05/29/2024\n\nClosing Date: 07/09/2024 03:00 PM EDT"


def test_facts_become_chunk_metadata(make_doc: MakeDoc, facts_config: FactTypeConfig) -> None:
    path = ["Key Dates"]
    doc = doc_with(
        make_doc,
        [para("Solicitation Due | 27-JUN-2024 14:00:00\nSolicitation Number | JA-207652", path)],
    )
    facts = extract_facts(doc, facts_config)
    (chunk,) = chunk_document(doc, facts, SMALL)
    assert {"JA-207652", "JA207652"} <= set(chunk.identifiers)
    assert "deadline" in chunk.fact_types
    assert set(chunk.fact_ids) == {f.fact_id for f in facts}


def test_embed_text_carries_document_and_section(make_doc: MakeDoc) -> None:
    doc = doc_with(make_doc, [para("Deliver within 45 days.", ["2 Terms", "2.1 Delivery"])])
    (chunk,) = chunk_document(doc, [], SMALL)
    assert chunk.embed_text.startswith(
        "Request for Quotation 117 (rfp)\n2 Terms > 2.1 Delivery\n\n"
    )


def test_chunk_ids_are_stable(make_doc: MakeDoc) -> None:
    doc = doc_with(make_doc, [para("Same text.", ["A"])])
    assert [c.chunk_id for c in chunk_document(doc, [])] == [
        c.chunk_id for c in chunk_document(doc, [])
    ]


def test_boilerplate_detection() -> None:
    form = "Company Federal Tax ID Number\nType\nProvide your answer below\nCompany Address\nType\nProvide your answer below"
    assert is_boilerplate(form)
    assert not is_boilerplate("All deliveries must include white glove services and asset tagging.")


def test_affidavits_are_never_boilerplate(make_doc: MakeDoc) -> None:
    text = "I am the ________ (Title) and duly authorized representative of ________ (name of business). Signature ______ Printed name ______"
    doc = doc_with(make_doc, [para(text, ["Affidavit"])])
    assert chunk_document(doc, [], SMALL)[0].is_boilerplate
    doc.doc_type = DocType.AFFIDAVIT
    assert not chunk_document(doc, [], SMALL)[0].is_boilerplate
