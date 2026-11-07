"""What the agents share: settings, the search engine (their tool), the indexer, the model
client, the field catalog and the evidence store. Built once per run and passed to every node.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from opentelemetry import trace
from opentelemetry.trace import Span

from rfp_intel.agents.evidence import EvidenceStore
from rfp_intel.agents.fields import FieldCatalog, load_fields
from rfp_intel.agents.guarded import GuardedLLM
from rfp_intel.agents.llm import LLM
from rfp_intel.config import Settings
from rfp_intel.facts.store import FactStore
from rfp_intel.search.engine import SearchEngine
from rfp_intel.search.indexer import Indexer
from rfp_intel.search.runtime import Runtime

tracer = trace.get_tracer("rfp_intel.agents")


@dataclass
class Services:
    settings: Settings
    engine: SearchEngine
    indexer: Indexer
    llm: GuardedLLM
    catalog: FieldCatalog
    store: EvidenceStore
    out_dir: Path
    root_span: Span | None = field(default=None, repr=False)

    @classmethod
    def build(cls, settings: Settings, runtime: Runtime, llm: LLM, out_dir: Path) -> "Services":
        return cls(
            settings=settings,
            engine=runtime.engine(),
            indexer=runtime.indexer(),
            llm=GuardedLLM(
                llm,
                max_output_tokens=settings.llm_max_output_tokens,
                trace_chars=settings.trace_max_chars,
            ),
            catalog=load_fields(settings.config_dir / "fields.yaml"),
            store=EvidenceStore(loader=runtime.backend.fetch),
            out_dir=out_dir,
        )

    @contextmanager
    def span(self, name: str) -> Iterator[Span]:
        """A span under the run's root span, even from LangGraph's worker threads."""
        ctx = trace.set_span_in_context(self.root_span) if self.root_span is not None else None
        with tracer.start_as_current_span(name, context=ctx) as span:
            yield span

    def facts(self) -> FactStore:
        return FactStore(self.settings.db_path)
