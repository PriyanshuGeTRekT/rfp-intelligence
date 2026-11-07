"""An LLM client for any OpenAI-compatible chat API.

One implementation covers OpenAI, Azure OpenAI, Groq, Mistral, Together, OpenRouter, Ollama,
vLLM and other servers that expose `POST /chat/completions`. Structured output is requested
with `response_format: json_schema`; a server that rejects that (HTTP 400) is retried once
with `json_object` and the schema in the system prompt, and the choice is remembered per
model. Every response is validated against the Pydantic schema; an invalid one gets one repair
attempt with the validation error, then fails loudly. No SDK is needed, only httpx.
"""

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError

from rfp_intel.agents.llm import LLM, LLMError, Usage, cost
from rfp_intel.logs import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------------------------
# Provider presets


@dataclass(frozen=True)
class Preset:
    base_url: str | None  # None: the user must give RFP_LLM_BASE_URL
    key_env: str | None  # the provider's conventional key variable
    auth_style: str = "bearer"
    needs_key: bool = True
    note: str = ""


PRESETS: dict[str, Preset] = {
    "openai": Preset("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "azure": Preset(
        None,
        "AZURE_OPENAI_API_KEY",
        auth_style="api-key",
        note="set RFP_LLM_BASE_URL=https://<resource>.openai.azure.com/openai/deployments/"
        '<deployment> and RFP_LLM_EXTRA_QUERY={"api-version":"2024-10-21"}',
    ),
    "groq": Preset("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "xai": Preset("https://api.x.ai/v1", "XAI_API_KEY"),
    "gemini": Preset("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "mistral": Preset("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "together": Preset("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "openrouter": Preset("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "deepseek": Preset("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "ollama": Preset("http://localhost:11434/v1", None, needs_key=False),
    "lmstudio": Preset("http://localhost:1234/v1", None, needs_key=False),
    "vllm": Preset("http://localhost:8000/v1", None, needs_key=False),
}
ALIASES = {
    "claude": "anthropic",
    "grok": "xai",
    "x.ai": "xai",
    "google": "gemini",
    "openai-compatible": "openai",
    "local": "ollama",
}
LOCAL_HOSTS = ("localhost", "127.0.0.1", "host.docker.internal")


@dataclass(frozen=True)
class Resolved:
    """Where the model calls go, after presets, overrides and key lookup."""

    name: str
    kind: str  # "anthropic" | "openai"
    base_url: str | None
    key: str | None
    auth_style: str
    key_source: str  # which setting or variable supplied the key, for `doctor`


def resolve_provider(settings: Any) -> Resolved:
    """Apply aliases, presets and overrides. Raises LLMError when something is missing."""
    name = ALIASES.get(settings.llm_provider.strip().lower(), settings.llm_provider.strip().lower())
    if name == "anthropic":
        if settings.anthropic_api_key is not None:
            return Resolved(
                name,
                "anthropic",
                None,
                settings.anthropic_api_key.get_secret_value(),
                "bearer",
                "ANTHROPIC_API_KEY",
            )
        if settings.llm_api_key is not None:
            return Resolved(
                name,
                "anthropic",
                None,
                settings.llm_api_key.get_secret_value(),
                "bearer",
                "RFP_LLM_API_KEY",
            )
        raise LLMError(
            "No API key for Claude: set ANTHROPIC_API_KEY (or RFP_LLM_API_KEY). To use another "
            "provider set RFP_LLM_PROVIDER, e.g. openai, groq, grok, gemini, mistral, ollama."
        )
    preset = PRESETS.get(name)
    base_url = settings.llm_base_url or (preset.base_url if preset else None)
    if not base_url:
        hint = f" ({preset.note})" if preset and preset.note else ""
        raise LLMError(f"Provider '{name}' needs RFP_LLM_BASE_URL{hint}.")
    key: str | None = None
    source = "none"
    if settings.llm_api_key is not None:
        key, source = settings.llm_api_key.get_secret_value(), "RFP_LLM_API_KEY"
    elif preset and preset.key_env and (env_key := _external_env(settings, preset.key_env)):
        key, source = env_key, preset.key_env
    local = any(h in base_url for h in LOCAL_HOSTS)
    needs_key = (preset.needs_key if preset else True) and not local
    if needs_key and not key:
        var = preset.key_env if preset and preset.key_env else "RFP_LLM_API_KEY"
        raise LLMError(
            f"No API key for provider '{name}': set {var} or RFP_LLM_API_KEY (see .env.example)."
        )
    auth_style = settings.llm_auth_style or (preset.auth_style if preset else "bearer")
    return Resolved(name, "openai", base_url, key, auth_style, source)


def _external_env(settings: Any, name: str) -> str | None:
    lookup = getattr(settings, "external_env", None)
    return lookup(name) if lookup else os.environ.get(name)


class Ping(BaseModel):
    ok: bool = Field(description="true")
    word: str = Field(description="the word 'ready'")


def check_llm(llm: LLM, model: str) -> dict[str, Any]:
    """One tiny structured call; returns what a user needs to see that the setup works."""
    start = time.perf_counter()
    out, usage = llm.structured(
        system="You reply with JSON matching the given schema and nothing else.",
        user="Set ok to true and word to 'ready'.",
        schema=Ping,
        model=model,
        effort="low",
        max_tokens=200,
    )
    modes = getattr(llm, "mode", None)  # the generic client remembers a fallback per model
    mode = modes.get(model, "json_schema") if isinstance(modes, dict) else "native"
    return {
        "model": model,
        "ok": out.ok and out.word.strip().lower() == "ready",
        "reply": out.model_dump(),
        "latency_ms": round((time.perf_counter() - start) * 1000),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": usage.cost_usd,
        "structured_output_mode": mode,
    }


_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_MAX_WAIT_S = 90.0  # longest server-requested wait honored before giving up


class _InvalidOutputError(Exception):
    """The server rejected the model's own output as not matching the schema (repairable)."""


def retry_delay(response: httpx.Response, attempt: int) -> float:
    """The server's `retry-after` (seconds or Groq-style "7.5s"/"1m2s"), else 2**attempt.
    Not capped: a caller compares it with the longest wait it is willing to make."""
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        value = response.headers.get(header)
        if value and (seconds := _parse_seconds(value)) is not None:
            return max(seconds, 0.5)
    return float(2**attempt)


def _quota_message(response: httpx.Response) -> str:
    try:
        message = str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        message = response.text
    return message[:300]


def _parse_seconds(value: str) -> float | None:
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", value)
    if not parts:
        return None
    scale = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    return sum(float(n) * scale[unit] for n, unit in parts)


_EFFORT = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


class OpenAICompatibleLLM:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        auth_style: str = "bearer",
        extra_query: Mapping[str, str] | None = None,
        send_reasoning_effort: bool = False,
        timeout_s: float = 120.0,
        max_attempts: int = 4,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        headers = (
            {"Authorization": f"Bearer {api_key}"}
            if auth_style == "bearer"
            else {"api-key": api_key}
        )
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers=headers,
            params=dict(extra_query or {}),
            timeout=timeout_s,
            transport=transport,
        )
        self.send_reasoning_effort = send_reasoning_effort
        self.max_attempts = max_attempts
        self._sleep = sleep
        self.mode: dict[str, str] = {}  # model -> "json_schema" | "json_object", once learned

    # --------------------------------------------------------------------------------------

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
        json_schema = schema.model_json_schema()
        usage = Usage()
        repair: str | None = None
        for _ in range(2):  # one repair round for an invalid or non-JSON answer
            try:
                data = self._complete(
                    model, system, user + (repair or ""), json_schema, effort, max_tokens, usage
                )
            except _InvalidOutputError as exc:
                repair = _repair_note(str(exc))
                continue
            choice = data["choices"][0]
            finish = choice.get("finish_reason")
            if finish == "length":
                raise LLMError(f"output truncated at {max_tokens} tokens")
            if finish == "content_filter":
                raise LLMError("the model declined this request")
            content = choice["message"].get("content") or ""
            try:
                parsed = schema.model_validate(json.loads(_FENCE_RE.sub("", content.strip())))
            except (json.JSONDecodeError, ValidationError) as exc:
                repair = _repair_note(str(exc))
                continue
            usage.cost_usd = cost(model, usage)
            return parsed, usage
        raise LLMError("the response did not match the output schema after a repair attempt")

    def _complete(
        self,
        model: str,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        effort: str,
        max_tokens: int,
        usage: Usage,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            mode = self.mode.get(model, "json_schema")
            body = self._body(model, system, user, json_schema, effort, max_tokens, mode)
            start = time.perf_counter()
            try:
                response = self.client.post("/chat/completions", json=body)
            except httpx.TransportError as exc:
                last = exc
                self._sleep(2**attempt)
                continue
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            if response.status_code == 400 and "json_validate_failed" in response.text:
                # Structured output works; this answer did not fit the schema.
                raise _InvalidOutputError(response.text[:400])
            if response.status_code == 400 and mode == "json_schema":
                log.info("json_schema_unsupported", model=model, detail=response.text[:200])
                self.mode[model] = "json_object"
                continue
            if response.status_code in (413, 429) and "request too large" in response.text.lower():
                # One request exceeds the per-minute ceiling: waiting cannot help.
                raise LLMError(
                    f"request too large for the provider's limit: {_quota_message(response)}; "
                    "lower RFP_LLM_MAX_PROMPT_TOKENS or RFP_LLM_MAX_OUTPUT_TOKENS"
                )
            if response.status_code in _TRANSIENT_STATUS:
                last = httpx.HTTPStatusError(
                    response.text[:200], request=response.request, response=response
                )
                delay = retry_delay(response, attempt)
                if delay > _MAX_WAIT_S:
                    # A quota that resets in minutes or hours (Groq's tokens-per-day limit, for
                    # one) will not clear by waiting here: fail now, with the server's reason.
                    raise LLMError(
                        f"rate limited for {delay:.0f} s, longer than the {_MAX_WAIT_S:.0f} s "
                        f"this client waits: {_quota_message(response)}"
                    )
                log.info("llm_retry", model=model, status=response.status_code, wait_s=delay)
                self._sleep(delay)
                continue
            if response.status_code >= 400:
                raise LLMError(f"provider returned {response.status_code}: {response.text[:300]}")
            data: dict[str, Any] = response.json()
            self._record(data, elapsed, usage)
            return data
        raise LLMError(f"gave up after {self.max_attempts} attempts: {last}")

    def _body(
        self,
        model: str,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        effort: str,
        max_tokens: int,
        mode: str,
    ) -> dict[str, Any]:
        if mode == "json_object":
            system = (
                f"{system}\n\nRespond with a single JSON object that matches this JSON Schema, "
                f"and nothing else:\n{json.dumps(json_schema)}"
            )
            response_format: dict[str, Any] = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {"name": json_schema.get("title", "output"), "schema": json_schema},
            }
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "response_format": response_format,
        }
        if self.send_reasoning_effort:
            body["reasoning_effort"] = _EFFORT.get(effort, "medium")
        return body

    @staticmethod
    def _record(data: dict[str, Any], elapsed_ms: float, usage: Usage) -> None:
        u = data.get("usage") or {}
        details = u.get("prompt_tokens_details") or {}
        cached = int(details.get("cached_tokens") or 0)
        usage.add(
            Usage(
                calls=1,
                input_tokens=int(u.get("prompt_tokens") or 0) - cached,
                output_tokens=int(u.get("completion_tokens") or 0),
                cache_read_tokens=cached,
                latency_ms=elapsed_ms,
            )
        )


def _repair_note(error: str) -> str:
    return (
        "\n\nYour previous reply was not valid for the required schema: "
        f"{error[:400]}. Reply with one JSON object that matches the schema."
    )
