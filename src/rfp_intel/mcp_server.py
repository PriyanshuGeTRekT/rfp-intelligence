"""An MCP server exposing the bid index to agent clients (Claude Desktop, IDEs, other agents).

Tools: list_bids, search, facts, ask. Runs over stdio by default (`rfp-mcp`), or
streamable HTTP (`rfp-mcp --http`). Needs the `mcp` extra: `uv sync --extra mcp`.
"""

import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from rfp_intel.agents.graph import run_question
from rfp_intel.agents.llm import LLM, llm_from_settings
from rfp_intel.agents.services import Services
from rfp_intel.config import Settings, get_settings
from rfp_intel.facts.models import FactKind
from rfp_intel.facts.store import FactStore
from rfp_intel.search.manifest import Manifest
from rfp_intel.search.runtime import Runtime, open_runtime

INSTRUCTIONS = (
    "Search and question answering over indexed public procurement bids (RFPs, addenda, "
    "quotes, portal pages). Use list_bids to see what is indexed, search for passages with "
    "file and page, facts for parsed dates, amounts and identifiers, and ask for a cited answer."
)


def build_server(
    settings: Settings | None = None, runtime: Runtime | None = None, llm: LLM | None = None
) -> MCPServer[Any]:
    settings = settings or get_settings()
    state: dict[str, Any] = {"runtime": runtime, "llm": llm}
    server: MCPServer[Any] = MCPServer("rfp-intel", instructions=INSTRUCTIONS)

    def rt() -> Runtime:
        if state["runtime"] is None:
            state["runtime"] = open_runtime(settings, load_reranker=False)
        runtime_obj: Runtime = state["runtime"]
        return runtime_obj

    @server.tool(description="Bid folders currently in the index.")
    def list_bids() -> list[str]:
        with Manifest(settings.db_path) as manifest:
            return manifest.bids()

    @server.tool(
        description="Hybrid search over the indexed documents. Each hit has file, pages, "
        "document type and the passage text."
    )
    def search(
        query: str, bid_id: str | None = None, doc_type: str | None = None, k: int = 5
    ) -> list[dict[str, Any]]:
        result = (
            rt()
            .engine()
            .search(query, bid_id=bid_id, doc_types=[doc_type] if doc_type else None, k=min(k, 20))
        )
        return [
            {
                "bid_id": h.bid_id,
                "file": h.file_name,
                "pages": h.pages,
                "doc_type": h.doc_type,
                "addendum_number": h.addendum_number,
                "score": h.score,
                "text": h.text,
            }
            for h in result.hits
        ]

    @server.tool(
        description="Typed facts parsed from a bid: dates (with UTC), durations, money, "
        "identifiers, contacts, quantities. Filter by label (deadline, delivery, warranty, "
        "bond_insurance, ...) or kind (datetime, duration, identifier, ...)."
    )
    def facts(
        bid_id: str, fact_type: str | None = None, kind: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        kinds = [FactKind(kind)] if kind else None
        with FactStore(settings.db_path) as store:
            found = store.query(bid_id, fact_types=[fact_type] if fact_type else None, kinds=kinds)
        return [
            {
                "file": f.file_name,
                "page": f.page,
                "kind": f.kind.value,
                "labels": f.fact_types,
                "raw": f.raw,
                "value": f.value,
                "context": f.context,
            }
            for f in found[: min(limit, 200)]
        ]

    @server.tool(
        description="Answer a question from the documents with verbatim citations, or say "
        "it is not found. Runs the agent graph with the configured model."
    )
    def ask(question: str, bid_id: str | None = None) -> dict[str, Any]:
        if state["llm"] is None:
            state["llm"] = llm_from_settings(settings)
        services = Services.build(settings, rt(), state["llm"], settings.outputs_dir)
        result, _ = run_question(services, question, bid_id=bid_id)
        return result.model_dump(mode="json")

    return server


def main() -> None:
    server = build_server()
    if "--http" in sys.argv[1:]:
        server.run("streamable-http")
    else:
        server.run("stdio")


if __name__ == "__main__":
    main()
