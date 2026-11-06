"""Format-independent structure: heading levels and section paths."""

import re

from rfp_intel.ingestion.models import Block, BlockKind, Section

_NUMBERED_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+\S")
_NAMED_RE = re.compile(
    r"^(?:section|article|part|chapter|attachment|exhibit|appendix)\s+[\dIVXA-Z]+\b", re.I
)


def numbered_level(text: str) -> int | None:
    """Heading depth from its number: "2" -> 1, "2.1" -> 2, "Section 3" -> 1."""
    m = _NUMBERED_RE.match(text)
    if m:
        return min(m.group(1).count(".") + 1, 5)
    if _NAMED_RE.match(text):
        return 1
    return None


def _same_heading(a: str, b: str) -> bool:
    return re.sub(r"\W+", " ", a).strip().casefold() == re.sub(r"\W+", " ", b).strip().casefold()


def assign_sections(blocks: list[Block]) -> tuple[list[Block], list[Section]]:
    """Give every block its heading path and group consecutive blocks into sections.

    A heading identical to one already open is a running heading repeated after a page
    break; it is dropped instead of opening a new section.
    """
    stack: list[tuple[int, str]] = []
    out: list[Block] = []
    for block in blocks:
        if block.kind is BlockKind.HEADING:
            level = block.heading_level or 3
            if any(_same_heading(title, block.text) for _, title in stack):
                continue
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, block.text))
        block.section_path = [title for _, title in stack]
        out.append(block)

    sections: list[Section] = []
    for i, block in enumerate(out):
        if sections and sections[-1].path == block.section_path:
            sections[-1].block_indices.append(i)
            sections[-1].page_end = block.page
        else:
            sections.append(
                Section(
                    path=list(block.section_path),
                    page_start=block.page,
                    page_end=block.page,
                    block_indices=[i],
                )
            )
    return out, sections
