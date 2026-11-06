"""Structured JSON logging with the active trace and span ids on every line.

Logs and spans answer different questions: spans show the shape and timing of a run,
logs carry detail. Injecting the ids lets you jump from one to the other.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from opentelemetry import trace


def _add_otel_ids(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event_dict["trace_id"] = f"{ctx.trace_id:032x}"
        event_dict["span_id"] = f"{ctx.span_id:016x}"
    return event_dict


class _StderrLogger:
    """Writes to whatever `sys.stderr` is at call time.

    structlog's PrintLogger binds the stream once; if that stream is later replaced and
    closed (test runners, embedded use), every later log call fails.
    """

    def msg(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    log = debug = info = warning = warn = error = critical = exception = fatal = msg


def _stderr_logger_factory(*_: Any) -> _StderrLogger:
    return _StderrLogger()


def configure_logging(level: str = "INFO", *, json: bool = True) -> None:
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _add_otel_ids,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[level.upper()]
        ),
        logger_factory=_stderr_logger_factory,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    return structlog.get_logger(name)
