import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from rfp_intel.config import Settings
from rfp_intel.search.runtime import Runtime

from .agents_fakes import answering
from .conftest import build_sample_pdf, fake_runtime

pytest.importorskip("mcp")
from rfp_intel.mcp_server import build_server


@pytest.fixture
def runtime(settings: Settings, data_dir: Path) -> Iterator[Runtime]:
    build_sample_pdf(data_dir / "BidA" / "RFQ_2024-117.pdf")
    with fake_runtime(settings) as rt:
        rt.indexer().index_folder(data_dir / "BidA")
        yield rt


def test_tools_are_listed_and_work(settings: Settings, runtime: Runtime) -> None:
    server = build_server(settings, runtime=runtime, llm=answering(verbatim=True))
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == {"list_bids", "search", "facts", "ask"}

    bids = asyncio.run(server.call_tool("list_bids", {}))
    assert "BidA" in str(bids)

    hits = asyncio.run(server.call_tool("search", {"query": "379-BFNZ", "bid_id": "BidA", "k": 3}))
    assert "379-BFNZ" in str(hits) and "RFQ_2024-117.pdf" in str(hits)

    facts = asyncio.run(server.call_tool("facts", {"bid_id": "BidA", "fact_type": "deadline"}))
    assert "July 9, 2024 2:00 PM CDT" in str(facts)

    reply = asyncio.run(
        server.call_tool(
            "ask", {"question": "How soon must equipment be delivered?", "bid_id": "BidA"}
        )
    )
    assert "within 45 days of award." in str(reply)
