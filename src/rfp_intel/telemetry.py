"""OpenTelemetry tracing.

Spans always go to `traces/<run_id>.jsonl`; the submitted example trace is rendered from
that file. A CLI process is one run. The API server runs many, so it routes spans by trace:
every span of a trace whose root carries `rfp.run_id` goes to that run's file, and spans of
plain API calls (a search) go to `traces/api.jsonl`. When `OTEL_EXPORTER_OTLP_ENDPOINT` is set
and the `obs` extra is installed, the
same spans also go to Phoenix or Langfuse over OTLP. With redaction on, emails and phone
numbers in span attributes are masked before any exporter sees them.
"""

import json
import re
import threading
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.util.types import Attributes

from rfp_intel.config import Settings
from rfp_intel.logs import get_logger

log = get_logger(__name__)

SERVICE_NAME = "rfp-intel"

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# North American numbers: (214) 932-5000, 214.932.5000, +1 214 932 5000, 214-932-5000.
# A separator is required between groups so bare digit runs (bid numbers, SKUs) survive.
_PHONE_RE = re.compile(
    r"(?<![\w/-])(?:\+?1[\s.-]?)?(?:\(\d{3}\)\s?|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?![\w/-])"
)


def new_run_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


def redact_text(text: str) -> str:
    return _PHONE_RE.sub("[PHONE]", _EMAIL_RE.sub("[EMAIL]", text))


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return tuple(redact_text(v) if isinstance(v, str) else v for v in value)
    return value


def _redact_attributes(attributes: Attributes) -> dict[str, Any]:
    return {k: _redact_value(v) for k, v in (attributes or {}).items()}


def _ns_to_iso(ns: int | None) -> str | None:
    if ns is None:
        return None
    return datetime.fromtimestamp(ns / 1e9, UTC).isoformat()


def span_to_dict(span: ReadableSpan) -> dict[str, Any]:
    ctx = span.context
    duration_ms = (
        (span.end_time - span.start_time) / 1e6
        if span.end_time is not None and span.start_time is not None
        else None
    )
    return {
        "trace_id": f"{ctx.trace_id:032x}" if ctx else None,
        "span_id": f"{ctx.span_id:016x}" if ctx else None,
        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
        "name": span.name,
        "kind": span.kind.name,
        "start": _ns_to_iso(span.start_time),
        "end": _ns_to_iso(span.end_time),
        "duration_ms": duration_ms,
        "status": span.status.status_code.name,
        "status_description": span.status.description,
        "attributes": dict(span.attributes or {}),
        "events": [
            {
                "name": e.name,
                "time": _ns_to_iso(e.timestamp),
                "attributes": dict(e.attributes or {}),
            }
            for e in span.events
        ],
        "resource": dict(span.resource.attributes),
    }


class JsonlSpanExporter(SpanExporter):
    """Append one JSON object per finished span to a file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        lines = [json.dumps(span_to_dict(s), default=str, ensure_ascii=False) for s in spans]
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None


class RedactingSpanExporter(SpanExporter):
    """Mask PII in span and event attributes, then hand the copies to another exporter."""

    def __init__(self, inner: SpanExporter) -> None:
        self.inner = inner

    @staticmethod
    def _redacted(span: ReadableSpan) -> ReadableSpan:
        return ReadableSpan(
            name=span.name,
            context=span.context,
            parent=span.parent,
            resource=span.resource,
            attributes=_redact_attributes(span.attributes),
            events=[
                Event(e.name, _redact_attributes(e.attributes), e.timestamp) for e in span.events
            ],
            links=span.links,
            kind=span.kind,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        )

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self.inner.export([self._redacted(s) for s in spans])

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def _otlp_exporter(endpoint: str) -> SpanExporter | None:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found,unused-ignore]
            OTLPSpanExporter,
        )
    except ImportError:
        log.warning("otlp_exporter_unavailable", hint="install the `obs` extra")
        return None
    exporter: SpanExporter = OTLPSpanExporter(endpoint=endpoint)
    return exporter


def build_tracer_provider(settings: Settings, run_id: str) -> TracerProvider:
    """Create a provider that writes this run's spans to JSONL and optionally to OTLP."""
    provider = TracerProvider(
        resource=Resource.create({"service.name": SERVICE_NAME, "rfp.run_id": run_id})
    )

    def wrap(exporter: SpanExporter) -> SpanExporter:
        return RedactingSpanExporter(exporter) if settings.trace_redact_pii else exporter

    jsonl = JsonlSpanExporter(settings.traces_dir / f"{run_id}.jsonl")
    # Synchronous processor: a crash mid-run still leaves every finished span on disk.
    provider.add_span_processor(SimpleSpanProcessor(wrap(jsonl)))

    if settings.otlp_endpoint:
        otlp = _otlp_exporter(settings.otlp_endpoint)
        if otlp is not None:
            provider.add_span_processor(BatchSpanProcessor(wrap(otlp)))
    return provider


class RunFileSpanProcessor(SpanProcessor):
    """Write each finished span to the JSONL file of the run its trace belongs to."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._runs: dict[int, str] = {}  # trace id -> run id
        self._exporters: dict[str, SpanExporter] = {}
        self._lock = threading.Lock()

    def on_start(self, span: Span, parent_context: otel_context.Context | None = None) -> None:
        run_id = (span.attributes or {}).get("rfp.run_id")
        if run_id and span.parent is None:
            with self._lock:
                self._runs[span.context.trace_id] = str(run_id)

    def _exporter(self, name: str) -> SpanExporter:
        with self._lock:
            if name not in self._exporters:
                jsonl = JsonlSpanExporter(self.settings.traces_dir / f"{name}.jsonl")
                self._exporters[name] = (
                    RedactingSpanExporter(jsonl) if self.settings.trace_redact_pii else jsonl
                )
            return self._exporters[name]

    def on_end(self, span: ReadableSpan) -> None:
        trace_id = span.context.trace_id if span.context else 0
        with self._lock:
            name = self._runs.get(trace_id, "api")
            if span.parent is None:
                self._runs.pop(trace_id, None)
        self._exporter(name).export([span])

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def setup_server_tracing(settings: Settings) -> TracerProvider:
    """Install the global provider for a long-running server (API, MCP): one file per run."""
    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(RunFileSpanProcessor(settings))
    if settings.otlp_endpoint and (otlp := _otlp_exporter(settings.otlp_endpoint)) is not None:
        exporter = RedactingSpanExporter(otlp) if settings.trace_redact_pii else otlp
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


def instrument_libraries(provider: TracerProvider) -> list[str]:
    """Attach the OpenInference instrumentors that are installed; return their names."""
    attached: list[str] = []
    try:
        from openinference.instrumentation.anthropic import (  # type: ignore[import-not-found,unused-ignore]
            AnthropicInstrumentor,
        )

        AnthropicInstrumentor().instrument(tracer_provider=provider)
        attached.append("anthropic")
    except ImportError:
        pass
    try:
        from openinference.instrumentation.langchain import (  # type: ignore[import-not-found,unused-ignore]
            LangChainInstrumentor,
        )

        LangChainInstrumentor().instrument(tracer_provider=provider)
        attached.append("langchain")
    except ImportError:
        pass
    return attached


def setup_tracing(settings: Settings, run_id: str | None = None) -> tuple[TracerProvider, str]:
    """Install the global tracer provider for this process. Call once per CLI run."""
    run_id = run_id or new_run_id()
    provider = build_tracer_provider(settings, run_id)
    trace.set_tracer_provider(provider)
    attached = instrument_libraries(provider)
    log.info(
        "tracing_ready", run_id=run_id, instrumented=attached, otlp=bool(settings.otlp_endpoint)
    )
    return provider, run_id
