"""Runtime settings.

Every value comes from the environment or `.env`, never from code, so the same build runs
locally, in CI and in a container. Secrets are `SecretStr` so they never appear in logs or
reprs.
"""

from functools import lru_cache
from pathlib import Path

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

    # LLM provider. The key keeps its conventional unprefixed name.
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "RFP_ANTHROPIC_API_KEY"),
    )
    extract_model: str = "claude-opus-5-5"
    cheap_model: str = "claude-haiku-5-5"

    # Retrieval models (all run locally on CPU through fastembed).
    embed_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    rerank_model: str = "Xenova/ms-marco-MiniLM-L-12-v2"

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
