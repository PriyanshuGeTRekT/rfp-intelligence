from pathlib import Path

import pytest

from rfp_intel.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
BIDS_DIR = REPO_ROOT / "data" / "bids"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "bids"
    (root / "BidA").mkdir(parents=True)
    return root


@pytest.fixture
def settings(tmp_path: Path, data_dir: Path) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=data_dir,
        state_dir=tmp_path / "var",
        traces_dir=tmp_path / "traces",
        api_key=None,
    )


@pytest.fixture(autouse=True)
def _fresh_settings_cache() -> None:
    get_settings.cache_clear()
