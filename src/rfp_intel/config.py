"""Runtime settings.

Values come from the environment, `.env`, and `config/defaults.env` (read first, so the others
override it). Model names have no defaults in code: they are configuration only. Secrets are
`SecretStr` so they never appear in logs or reprs.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import dotenv_values
from pydantic import AliasChoices, Field, PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULTS_ENV = Path("config/defaults.env")
ENV_FILES = (DEFAULTS_ENV, Path(".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RFP_",
        env_file=ENV_FILES,
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    # Paths, relative to the working directory (run commands from the repo root).
    data_dir: Path = Path("data/bids")
    state_dir: Path = Path("var")
    traces_dir: Path = Path("traces")
    outputs_dir: Path = Path("outputs")  # one JSON record per bid, and the Q&A log
    config_dir: Path = Path("config")

    # LLM provider. "anthropic"/"claude" uses the Anthropic SDK. Any other name uses the
    # OpenAI-compatible chat API: a known preset (openai, azure, groq, xai/grok, gemini,
    # mistral, together, openrouter, deepseek, ollama, lmstudio, vllm) fills in the base URL
    # and the key variable; any other service works with RFP_LLM_BASE_URL set explicitly.
    llm_provider: str
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "RFP_ANTHROPIC_API_KEY"),
    )
    llm_api_key: SecretStr | None = None  # overrides the preset's key variable
    llm_base_url: str | None = None  # overrides the preset's base URL
    llm_auth_style: Literal["bearer", "api-key"] | None = None  # preset default; Azure: api-key
    llm_extra_query: dict[str, str] = Field(default_factory=dict)  # Azure: {"api-version": ...}
    llm_send_reasoning_effort: bool = False  # only for servers that accept reasoning_effort
    # Price per million tokens for a model not in config/llm_prices.yaml.
    llm_price_input_per_m: float | None = None
    llm_price_output_per_m: float | None = None
    # Model names (provider-specific) come from config/defaults.env or .env, never from code.
    extract_model: str
    cheap_model: str
    qa_model: str | None = None  # question answering; the extraction model when unset

    # Limits that make small quotas work (a free tier) and large ones fast. Defaults suit a
    # paid provider; .env.example shows free-tier values.
    llm_tokens_per_minute: int = Field(default=0, ge=0)  # client-side pacing; 0 = off
    llm_max_concurrency: int = Field(default=4, ge=1)  # parallel graph branches
    llm_max_prompt_tokens: int = Field(default=24_000, ge=1_000)  # evidence budget per call
    llm_max_output_tokens: int = Field(default=8_000, ge=256)
    extract_batch_size: int = Field(default=5, ge=1)  # fields per extraction call
    extract_effort: str = "medium"
    extract_rerank: bool = True  # rerank each field's evidence with the cross-encoder
    max_retries: int = Field(default=2, ge=0)  # validator-driven retries per field
    qa_search_config: str = "hybrid_facts_rerank"
    qa_passages: int = Field(default=8, ge=1)
    # Semantic cache: reuse the answer to an earlier question this similar (cosine of the dense
    # embeddings) over the same documents and records; 0 turns the cache off.
    qa_cache_threshold: float = Field(default=0.95, ge=0, le=1)

    # Retrieval models (all run locally on CPU through fastembed); names from configuration.
    embed_model: str
    sparse_model: str
    rerank_model: str
    # Default ~/.cache/rfp-intel/models: shared across checkouts, and short, because the Hugging
    # Face cache nests deep folders and a long repo path on Windows exceeds the 260-char limit.
    model_cache_dir: Path | None = None

    # Vector store: embedded Qdrant under state_dir unless a server URL is given.
    qdrant_url: str | None = None
    qdrant_collection: str = "chunks"

    # API.
    api_key: SecretStr | None = None
    max_request_bytes: int = Field(default=64 * 1024, gt=0)

    # Observability.
    otlp_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "RFP_OTLP_ENDPOINT"),
    )
    ocr: bool = True  # read scanned pages (image-only PDF pages) with OCR
    trace_redact_pii: bool = True
    trace_max_chars: int = Field(default=20_000, ge=0)  # prompt and output text kept per span
    log_level: str = "INFO"

    _env_files: tuple[Path, ...] = PrivateAttr(default=ENV_FILES)

    def __init__(self, **values: Any) -> None:
        env_file = values.get("_env_file", type(self).model_config.get("env_file"))
        super().__init__(**values)
        if env_file is None:
            self._env_files = ()
        elif isinstance(env_file, str | Path):
            self._env_files = (Path(env_file),)
        else:
            self._env_files = tuple(Path(f) for f in env_file)

    def external_env(self, name: str) -> str | None:
        """A variable without the RFP_ prefix, such as GROQ_API_KEY: from the process
        environment first, then from the same env files the settings were read from."""
        if value := os.environ.get(name):
            return value
        for path in reversed(self._env_files):
            if path.exists() and (value := dotenv_values(path).get(name)):
                return value
        return None

    @property
    def qdrant_path(self) -> Path:
        return self.state_dir / "qdrant"

    @property
    def db_path(self) -> Path:
        """SQLite file holding the manifest, facts, change events and run metadata."""
        return self.state_dir / "rfp.sqlite"

    @property
    def docs_dir(self) -> Path:
        """Parsed documents as JSON, written by the indexer."""
        return self.state_dir / "docs"

    @property
    def models_dir(self) -> Path:
        return self.model_cache_dir or Path.home() / ".cache" / "rfp-intel" / "models"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
