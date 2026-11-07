"""Runtime settings.

Every value comes from the environment or `.env`, never from code, so the same build runs
locally, in CI and in a container. Secrets are `SecretStr` so they never appear in logs or
reprs.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RFP_",
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    # Paths, relative to the working directory (run commands from the repo root).
    data_dir: Path = Path("data/bids")
    state_dir: Path = Path("var")
    traces_dir: Path = Path("traces")
    config_dir: Path = Path("config")

    # LLM provider: "anthropic" uses the Anthropic SDK; "openai" uses any OpenAI-compatible
    # chat API (OpenAI, Azure OpenAI, Groq, Mistral, Together, OpenRouter, Ollama, vLLM, ...).
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "RFP_ANTHROPIC_API_KEY"),
    )
    llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("RFP_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = "https://api.openai.com/v1"
    llm_auth_style: Literal["bearer", "api-key"] = "bearer"  # Azure OpenAI uses "api-key"
    llm_extra_query: dict[str, str] = Field(default_factory=dict)  # Azure: {"api-version": ...}
    llm_send_reasoning_effort: bool = False  # only for servers that accept reasoning_effort
    # Price per million tokens for the configured models when the built-in table lacks them.
    llm_price_input_per_m: float | None = None
    llm_price_output_per_m: float | None = None
    # Model names are provider-specific: Claude ids, or e.g. "gpt-5-mini", "llama3.1:70b".
    extract_model: str = "claude-opus-5-5"
    cheap_model: str = "claude-haiku-5-5"

    # Retrieval models (all run locally on CPU through fastembed).
    embed_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    # Used by the hybrid_facts_rerank config; see docs/eval/retrieval.md for why this one.
    rerank_model: str = "BAAI/bge-reranker-v2-m3-int8"
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
    trace_redact_pii: bool = True
    log_level: str = "INFO"

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
