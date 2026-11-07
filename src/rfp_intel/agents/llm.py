"""LLM access behind one small interface.

Agents call `LLM.structured(...)` and get a validated Pydantic object plus usage. Two
implementations:

- `AnthropicLLM`: Claude through the Anthropic SDK's `messages.parse` with a Pydantic output
  format, adaptive thinking (always on for Opus 5.5) steered by `output_config.effort`, a cached
  system prompt, timeouts and retries on transient errors. The SDK is imported on first use.
- `ScriptedLLM`: deterministic responses for tests and offline runs, keyed by output schema,
  recording every call so tests can assert on prompts.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# USD per million tokens (input, output), filled from config/llm_prices.yaml.
PRICES: dict[str, tuple[float, float]] = {}


def load_prices(path: Path) -> None:
    """Load the price table; a missing file only means costs are reported as 0."""
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for model, (price_in, price_out) in (data.get("prices") or {}).items():
        PRICES[str(model)] = (float(price_in), float(price_out))


def estimate_tokens(text: str) -> int:
    """A deliberately high estimate (3.5 characters per token) for budgets and pacing: GPT-style
    tokenizers average about 4 on English, others count more tokens for the same text."""
    return int(len(text) / 3.5) + 1


class LLMError(RuntimeError):
    """The model could not produce a usable answer (refusal, truncation, invalid output)."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        for name in (
            "calls",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.latency_ms = round(self.latency_ms + other.latency_ms, 1)
        self.cost_usd = round(self.cost_usd + other.cost_usd, 6)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def cost(model: str, u: Usage) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return round(
        (
            u.input_tokens * price_in
            + u.cache_read_tokens * price_in * 0.1
            + u.cache_write_tokens * price_in * 1.25
            + u.output_tokens * price_out
        )
        / 1_000_000,
        6,
    )


class LLM(Protocol):
    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: str = "medium",
        max_tokens: int = 8000,
    ) -> tuple[T, Usage]: ...


# ---------------------------------------------------------------------------------------------


@dataclass
class Call:
    schema: str
    model: str
    system: str
    user: str


Responder = Callable[[str, str], BaseModel]  # (system, user) -> response


@dataclass
class ScriptedLLM:
    """Answers from `responders[schema name]`; records every call."""

    responders: dict[str, Responder]
    calls: list[Call] = field(default_factory=list)

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: str = "medium",
        max_tokens: int = 8000,
    ) -> tuple[T, Usage]:
        self.calls.append(Call(schema.__name__, model, system, user))
        responder = self.responders.get(schema.__name__)
        if responder is None:
            raise LLMError(f"no scripted response for {schema.__name__}")
        result = responder(system, user)
        if not isinstance(result, schema):
            result = schema.model_validate(result.model_dump())
        tokens = len(system + user) // 4
        return result, Usage(
            calls=1, input_tokens=tokens, output_tokens=len(result.model_dump_json()) // 4
        )


# ---------------------------------------------------------------------------------------------

_TRANSIENT = {
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
    "OverloadedError",
}


class AnthropicLLM:
    """Claude via the Anthropic SDK. Untested here without an API key; see README."""

    def __init__(
        self, api_key: str, *, timeout_s: float = 120.0, max_attempts: int = 3, client: Any = None
    ) -> None:
        if client is None:
            import anthropic  # imported lazily: tests and offline runs never need it

            client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=0)
        self.client = client
        self.max_attempts = max_attempts

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str,
        effort: str = "medium",
        max_tokens: int = 8000,
    ) -> tuple[T, Usage]:
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            start = time.perf_counter()
            try:
                response = self.client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    # The system prompt (instructions and field definitions) is identical across
                    # calls, so it is cached; repeated calls read it at a tenth of the price.
                    system=[
                        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                    ],
                    messages=[{"role": "user", "content": user}],
                    output_format=schema,
                    output_config={"effort": effort},
                )
            except Exception as exc:
                if type(exc).__name__ not in _TRANSIENT or attempt == self.max_attempts - 1:
                    raise
                last = exc
                time.sleep(2**attempt)
                continue
            usage = Usage(
                calls=1,
                input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
                cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
            )
            usage.cost_usd = cost(model, usage)
            if response.stop_reason == "refusal":
                raise LLMError("the model declined this request")
            if response.stop_reason == "max_tokens":
                raise LLMError(f"output truncated at {max_tokens} tokens")
            parsed = response.parsed_output
            if parsed is None:
                raise LLMError("the response did not match the output schema")
            return parsed, usage
        raise LLMError(f"gave up after {self.max_attempts} attempts: {last}")


def register_price(model: str, input_per_m: float | None, output_per_m: float | None) -> None:
    """Price a model the built-in table does not know (per million tokens)."""
    if model not in PRICES and input_per_m is not None and output_per_m is not None:
        PRICES[model] = (input_per_m, output_per_m)


def llm_from_settings(settings: Any) -> LLM:
    """The configured provider's client, paced when a token rate is set, or a clear error
    naming what is missing."""
    from rfp_intel.agents.providers import OpenAICompatibleLLM, resolve_provider
    from rfp_intel.agents.ratelimit import RateLimitedLLM

    load_prices(settings.config_dir / "llm_prices.yaml")
    for model in (settings.extract_model, settings.cheap_model):
        register_price(model, settings.llm_price_input_per_m, settings.llm_price_output_per_m)
    resolved = resolve_provider(settings)
    client: LLM
    if resolved.kind == "anthropic":
        client = AnthropicLLM(resolved.key or "")
    else:
        client = OpenAICompatibleLLM(
            resolved.key or "none",
            base_url=resolved.base_url or "",
            auth_style=resolved.auth_style,
            extra_query=settings.llm_extra_query,
            send_reasoning_effort=settings.llm_send_reasoning_effort,
        )
    if settings.llm_tokens_per_minute:
        client = RateLimitedLLM(client, tokens_per_minute=settings.llm_tokens_per_minute)
    return client
