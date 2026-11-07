from pathlib import Path

import pytest

from rfp_intel.config import Settings

from .conftest import DEFAULTS_ENV


def test_defaults_point_at_repo_relative_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RFP_DATA_DIR", "RFP_STATE_DIR", "RFP_EXTRACT_MODEL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=DEFAULTS_ENV)  # type: ignore[call-arg]
    assert s.data_dir == Path("data/bids")
    assert s.db_path == Path("var/rfp.sqlite")
    assert s.qdrant_path == Path("var/qdrant")
    assert s.extract_model == "claude-opus-5-5"


def test_env_overrides_and_unprefixed_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_EXTRACT_MODEL", "claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces")
    s = Settings(_env_file=DEFAULTS_ENV)  # type: ignore[call-arg]
    assert s.extract_model == "claude-sonnet-5-5"
    assert s.anthropic_api_key is not None
    assert s.anthropic_api_key.get_secret_value() == "sk-test-123"
    assert s.otlp_endpoint == "http://localhost:6006/v1/traces"


def test_empty_env_values_mean_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    s = Settings(_env_file=DEFAULTS_ENV)  # type: ignore[call-arg]
    assert s.api_key is None
    assert s.anthropic_api_key is None


def test_secrets_do_not_leak_into_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RFP_API_KEY", "super-secret-value")
    s = Settings(_env_file=DEFAULTS_ENV)  # type: ignore[call-arg]
    assert "super-secret-value" not in repr(s)
    assert "super-secret-value" not in s.model_dump_json()
