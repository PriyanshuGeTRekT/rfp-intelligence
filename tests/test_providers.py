"""The OpenAI-compatible client against a mock HTTP server."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from rfp_intel.agents import providers
from rfp_intel.agents.llm import PRICES, AnthropicLLM, LLMError, llm_from_settings
from rfp_intel.agents.providers import OpenAICompatibleLLM
from rfp_intel.config import Settings

from .conftest import DEFAULTS_ENV


class Answer(BaseModel):
    text: str
    count: int


def _reply(content: str, finish: str = "stop", cached: int = 0) -> dict[str, Any]:
    return {
        "choices": [
            {"message": {"role": "assistant", "content": content}, "finish_reason": finish}
        ],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


class Server:
    """A scripted OpenAI-compatible endpoint; each entry is a status or a reply body."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self.script.pop(0)
        if isinstance(step, int):
            return httpx.Response(step, json={"error": {"message": f"status {step}"}})
        if isinstance(step, httpx.Response):
            return step
        if isinstance(step, Exception):
            raise step
        return httpx.Response(200, json=step)

    def body(self, i: int = -1) -> dict[str, Any]:
        return dict(json.loads(self.requests[i].content))


def _client(server: Server, **kw: Any) -> OpenAICompatibleLLM:
    kw.setdefault("sleep", lambda seconds: None)
    return OpenAICompatibleLLM(
        "sk-test",
        base_url="https://llm.example/v1",
        transport=httpx.MockTransport(server.handler),
        **kw,
    )


def test_json_schema_request_and_usage() -> None:
    server = Server([_reply('{"text": "ok", "count": 2}', cached=400)])
    out, usage = _client(server).structured(
        system="sys", user="q", schema=Answer, model="m", effort="high"
    )
    assert out == Answer(text="ok", count=2)
    req = server.requests[0]
    assert (
        req.url.path == "/v1/chat/completions" and req.headers["authorization"] == "Bearer sk-test"
    )
    body = server.body()
    assert body["response_format"]["type"] == "json_schema"
    assert (
        body["response_format"]["json_schema"]["schema"]["properties"]["count"]["type"] == "integer"
    )
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert "temperature" not in body and "reasoning_effort" not in body
    assert (usage.calls, usage.input_tokens, usage.cache_read_tokens, usage.output_tokens) == (
        1,
        600,
        400,
        50,
    )


def test_falls_back_to_json_object_and_remembers_it() -> None:
    server = Server([400, _reply('{"text": "a", "count": 1}'), _reply('{"text": "b", "count": 2}')])
    client = _client(server)
    first, _ = client.structured(system="sys", user="q", schema=Answer, model="m")
    assert first.text == "a"
    fallback = server.body(1)
    assert fallback["response_format"] == {"type": "json_object"}
    assert (
        "JSON Schema" in fallback["messages"][0]["content"]
        and '"count"' in fallback["messages"][0]["content"]
    )
    second, _ = client.structured(system="sys", user="q2", schema=Answer, model="m")
    assert second.text == "b" and len(server.requests) == 3  # no 400 round trip the second time
    assert server.body(2)["response_format"] == {"type": "json_object"}


def test_invalid_answer_gets_one_repair_then_fails() -> None:
    server = Server([_reply('```json\n{"text": "x"}\n```'), _reply('{"text": "x", "count": 3}')])
    out, usage = _client(server).structured(system="s", user="q", schema=Answer, model="m")
    assert out.count == 3 and usage.calls == 2
    assert "not valid for the required schema" in server.body(1)["messages"][1]["content"]

    bad = Server([_reply("not json"), _reply("still not json")])
    with pytest.raises(LLMError, match="repair attempt"):
        _client(bad).structured(system="s", user="q", schema=Answer, model="m")


def test_transient_errors_retry_then_give_up() -> None:
    server = Server([429, httpx.ConnectError("boom"), _reply('{"text": "ok", "count": 1}')])
    out, _ = _client(server).structured(system="s", user="q", schema=Answer, model="m")
    assert out.text == "ok" and len(server.requests) == 3
    with pytest.raises(LLMError, match="gave up"):
        _client(Server([503] * 4)).structured(system="s", user="q", schema=Answer, model="m")
    with pytest.raises(LLMError, match="provider returned 401"):
        _client(Server([401])).structured(system="s", user="q", schema=Answer, model="m")


def test_server_requested_waits_are_honored() -> None:
    limited = httpx.Response(429, headers={"retry-after": "7"}, json={"error": {}})
    groq_style = httpx.Response(429, headers={"x-ratelimit-reset-tokens": "1m2.5s"}, json={})
    waits: list[float] = []
    server = Server([limited, groq_style, _reply('{"text": "ok", "count": 1}')])
    _client(server, sleep=waits.append).structured(system="s", user="q", schema=Answer, model="m")
    assert waits == [7.0, 62.5]
    assert providers.retry_delay(httpx.Response(503), attempt=2) == 4.0


def test_a_request_over_the_per_minute_ceiling_fails_fast() -> None:
    too_big = httpx.Response(
        429,
        headers={"retry-after": "3"},
        json={"error": {"message": "Request too large for model"}},
    )
    with pytest.raises(LLMError, match="RFP_LLM_MAX_PROMPT_TOKENS"):
        _client(Server([too_big])).structured(system="s", user="q", schema=Answer, model="m")


def test_a_quota_that_resets_later_fails_fast_with_the_reason() -> None:
    daily = httpx.Response(
        429,
        headers={"retry-after": "1740"},
        json={"error": {"message": "Rate limit reached on tokens per day (TPD): Limit 200000"}},
    )
    waits: list[float] = []
    with pytest.raises(LLMError, match="tokens per day"):
        _client(Server([daily]), sleep=waits.append).structured(
            system="s", user="q", schema=Answer, model="m"
        )
    assert waits == []  # no pointless retries


def test_server_side_schema_failure_gets_a_repair_round() -> None:
    rejected = httpx.Response(400, json={"error": {"code": "json_validate_failed"}})
    server = Server([rejected, _reply('{"text": "ok", "count": 1}')])
    client = _client(server)
    out, _ = client.structured(system="s", user="q", schema=Answer, model="m")
    assert out.count == 1
    assert "not valid for the required schema" in server.body()["messages"][1]["content"]
    assert client.mode == {}  # json_schema mode is kept: the server supports it


def test_truncation_and_content_filter_are_errors() -> None:
    with pytest.raises(LLMError, match="truncated"):
        _client(Server([_reply("{", finish="length")])).structured(
            system="s", user="q", schema=Answer, model="m"
        )
    with pytest.raises(LLMError, match="declined"):
        _client(Server([_reply("", finish="content_filter")])).structured(
            system="s", user="q", schema=Answer, model="m"
        )


def test_azure_style_auth_query_and_reasoning_effort() -> None:
    server = Server([_reply('{"text": "ok", "count": 1}')])
    client = OpenAICompatibleLLM(
        "azkey",
        base_url="https://res.openai.azure.com/openai/deployments/dep",
        auth_style="api-key",
        extra_query={"api-version": "2024-10-21"},
        send_reasoning_effort=True,
        transport=httpx.MockTransport(server.handler),
    )
    client.structured(system="s", user="q", schema=Answer, model="dep", effort="xhigh")
    req = server.requests[0]
    assert req.headers["api-key"] == "azkey" and "authorization" not in req.headers
    assert req.url.params["api-version"] == "2024-10-21"
    assert server.body()["reasoning_effort"] == "high"


def _settings(**kw: Any) -> Settings:
    values: dict[str, Any] = {"anthropic_api_key": None, "llm_api_key": None, **kw}
    return Settings(_env_file=DEFAULTS_ENV, **values)  # type: ignore[call-arg]


def test_provider_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "RFP_LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        llm_from_settings(_settings())
    with pytest.raises(LLMError, match="RFP_LLM_API_KEY"):
        llm_from_settings(_settings(llm_provider="openai"))

    openai = llm_from_settings(
        _settings(llm_provider="openai", llm_api_key=SecretStr("k"), extract_model="gpt-x",
                  llm_price_input_per_m=1.0, llm_price_output_per_m=4.0)
    )  # fmt: skip
    assert isinstance(openai, OpenAICompatibleLLM) and PRICES["gpt-x"] == (1.0, 4.0)

    ollama = llm_from_settings(
        _settings(
            llm_provider="openai",
            llm_base_url="http://localhost:11434/v1",
            extract_model="llama3.1",
        )
    )
    assert isinstance(ollama, OpenAICompatibleLLM)  # local servers need no key

    anthropic_via_generic_key = _settings(llm_api_key=SecretStr("sk-ant"))
    monkeypatch.setattr(AnthropicLLM, "__init__", lambda self, key, **kw: None)
    assert isinstance(llm_from_settings(anthropic_via_generic_key), AnthropicLLM)


def test_any_provider_satisfies_the_llm_protocol() -> None:
    def make() -> OpenAICompatibleLLM:
        return _client(Server([]))

    assert hasattr(make(), "structured")


def test_presets_aliases_and_key_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    from rfp_intel.agents.providers import PRESETS, check_llm, resolve_provider

    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    # a named provider fills in its base URL; the key comes from its usual variable
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    groq = resolve_provider(_settings(llm_provider="groq"))
    assert (groq.kind, groq.base_url, groq.key, groq.key_source) == (
        "openai", "https://api.groq.com/openai/v1", "gsk-test", "GROQ_API_KEY",
    )  # fmt: skip

    # aliases: "grok" is xAI, "claude" is anthropic; case does not matter
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    grok = resolve_provider(_settings(llm_provider="Grok"))
    assert grok.name == "xai" and grok.base_url == PRESETS["xai"].base_url
    claude = resolve_provider(_settings(llm_provider="claude", anthropic_api_key=SecretStr("a")))
    assert claude.kind == "anthropic" and claude.key_source == "ANTHROPIC_API_KEY"

    # RFP_LLM_API_KEY beats the provider variable; RFP_LLM_BASE_URL beats the preset
    both = resolve_provider(
        _settings(
            llm_provider="groq", llm_api_key=SecretStr("mine"), llm_base_url="https://proxy/v1"
        )
    )
    assert (both.key, both.key_source, both.base_url) == (
        "mine",
        "RFP_LLM_API_KEY",
        "https://proxy/v1",
    )

    # a missing key names the variable to set
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        resolve_provider(_settings(llm_provider="groq"))

    # unknown providers work with an explicit base URL; azure needs one and uses api-key auth
    with pytest.raises(LLMError, match="RFP_LLM_BASE_URL"):
        resolve_provider(_settings(llm_provider="some-new-service"))
    custom = resolve_provider(
        _settings(
            llm_provider="some-new-service",
            llm_base_url="https://llm.corp/v1",
            llm_api_key=SecretStr("k"),
        )
    )
    assert custom.kind == "openai" and custom.auth_style == "bearer"
    with pytest.raises(LLMError, match="api-version"):
        resolve_provider(_settings(llm_provider="azure", llm_api_key=SecretStr("k")))
    azure = resolve_provider(
        _settings(
            llm_provider="azure",
            llm_api_key=SecretStr("k"),
            llm_base_url="https://r.openai.azure.com/openai/deployments/d",
        )
    )
    assert azure.auth_style == "api-key"

    # local servers need no key
    assert resolve_provider(_settings(llm_provider="ollama")).key is None
    assert resolve_provider(_settings(llm_provider="lmstudio")).kind == "openai"

    # the check call reports a usable setup
    server = Server([_reply('{"ok": true, "word": "ready"}')])
    report = check_llm(_client(server), "m")
    assert report["ok"] and report["structured_output_mode"] == "json_schema"
