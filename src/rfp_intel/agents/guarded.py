"""LLM calls that never crash the pipeline, and that leave a full record in the trace.

Agents call `GuardedLLM.call(...)` instead of the raw client. A call that fails for any
reason (timeout, rate limit after retries, invalid JSON after the repair round, refusal,
truncation, a network error) comes back as an `Outcome` with `error` set, so the agent can
degrade: an extraction draft is marked failed and retried, an addendum is skipped with a note,
a Q&A answer says it could not answer. The current span gets the model, the prompt, the
output, tokens, cost and any error; the exporter redacts emails and phone numbers.
"""

import json
from dataclasses import dataclass, field
from typing import TypeVar

from opentelemetry import trace
from pydantic import BaseModel

from rfp_intel.agents.llm import LLM, Usage
from rfp_intel.logs import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


@dataclass
class Outcome[T: BaseModel]:
    output: T | None
    usage: Usage = field(default_factory=Usage)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.output is not None


class GuardedLLM:
    def __init__(self, llm: LLM, *, max_output_tokens: int = 8000, trace_chars: int = 20_000):
        self.llm = llm
        self.max_output_tokens = max_output_tokens
        self.trace_chars = trace_chars

    def call(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: str = "medium",
    ) -> Outcome[T]:
        span = trace.get_current_span()
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.schema", schema.__name__)
        span.set_attribute("llm.system", self._clip(system))
        span.set_attribute("llm.input", self._clip(user))
        try:
            out, usage = self.llm.structured(
                system=system, user=user, schema=schema, model=model, effort=effort,
                max_tokens=self.max_output_tokens,
            )  # fmt: skip
        except Exception as exc:  # any failure becomes data; the agent decides how to degrade
            error = f"{type(exc).__name__}: {exc}"[:500]
            log.warning("llm_call_failed", model=model, schema=schema.__name__, error=error)
            span.set_attribute("llm.error", error)
            return Outcome(output=None, error=error)
        span.set_attribute("llm.output", self._clip(out.model_dump_json()))
        span.set_attribute("llm.input_tokens", usage.input_tokens)
        span.set_attribute("llm.output_tokens", usage.output_tokens)
        span.set_attribute("llm.cost_usd", usage.cost_usd)
        span.set_attribute("llm.latency_ms", usage.latency_ms)
        return Outcome(output=out, usage=usage)

    def _clip(self, text: str) -> str:
        if len(text) <= self.trace_chars:
            return text
        return text[: self.trace_chars] + f"... [{len(text) - self.trace_chars} more chars]"


def io_attribute(value: object, limit: int = 4000) -> str:
    """A node's input or output as compact JSON for a span attribute."""
    text = json.dumps(value, default=str, separators=(",", ":"))
    return text if len(text) <= limit else text[:limit] + "..."
