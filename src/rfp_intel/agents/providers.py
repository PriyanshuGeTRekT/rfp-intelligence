"""An LLM client for any OpenAI-compatible chat API.

One implementation covers OpenAI, Azure OpenAI, Groq, Mistral, Together, OpenRouter, Ollama,
vLLM and other servers that expose `POST /chat/completions`. Structured output is requested
with `response_format: json_schema`; a server that rejects that (HTTP 400) is retried once
with `json_object` and the schema in the system prompt, and the choice is remembered per
model. Every response is validated against the Pydantic schema; an invalid one gets one repair
attempt with the validation error, then fails loudly. No SDK is needed, only httpx.
"""

import json
import re
import time
from collections.abc import Mapping
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from rfp_intel.agents.llm import LLMError, Usage, cost
from rfp_intel.logs import get_logger

log = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
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
        max_attempts: int = 3,
        transport: httpx.BaseTransport | None = None,
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
            data = self._complete(
                model, system, user + (repair or ""), json_schema, effort, max_tokens, usage
            )
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
                repair = (
                    "\n\nYour previous reply was not valid for the required schema: "
                    f"{str(exc)[:400]}. Reply with one JSON object that matches the schema."
                )
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
                time.sleep(2**attempt)
                continue
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            if response.status_code == 400 and mode == "json_schema":
                log.info("json_schema_unsupported", model=model, detail=response.text[:200])
                self.mode[model] = "json_object"
                continue
            if response.status_code in _TRANSIENT_STATUS:
                last = httpx.HTTPStatusError(
                    response.text[:200], request=response.request, response=response
                )
                time.sleep(2**attempt)
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
