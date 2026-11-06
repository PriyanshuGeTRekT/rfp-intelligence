"""End-to-end retrieval on the two real bids with the real models.

Marked slow: the first run downloads about 750 MB of models into ~/.cache/rfp-intel. Run with
`uv run pytest -m slow`.
"""

import shutil
from collections.abc import Iterator

import pytest

from rfp_intel.config import Settings
from rfp_intel.search.runtime import Runtime, open_runtime

from .conftest import BIDS_DIR, REPO_ROOT

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def runtime(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Runtime]:
    tmp = tmp_path_factory.mktemp("real")
    data = tmp / "bids"
    for bid in ("Bid1", "Bid2"):
        shutil.copytree(BIDS_DIR / bid, data / bid)
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_dir=data,
        state_dir=tmp / "var",
        config_dir=REPO_ROOT / "config",
        # models come from the default per-user cache, so they download once
    )
    with open_runtime(settings) as rt:
        for bid in ("Bid1", "Bid2"):
            rt.indexer().index_folder(data / bid)
        yield rt


def _top(runtime: Runtime, q: str, k: int = 3, **kw: object) -> list[str]:
    hits = runtime.engine().search(q, k=k, **kw).hits  # type: ignore[arg-type]
    return [f"{h.file_name} p{h.pages}: {h.text}" for h in hits]


def test_exact_identifier(runtime: Runtime) -> None:
    assert "WD22TB4" in _top(runtime, "WD22TB4", k=1)[0]
    assert "379-BFNZ" in _top(runtime, "379-BFNZ", k=1)[0]


def test_due_date_after_addenda(runtime: Runtime) -> None:
    top = _top(runtime, "When is the proposal due after the addendums?", k=1, bid_id="Bid1")[0]
    assert top.startswith("Addendum 2") and "July 9, 2024 at 2:00 PM CST" in top


def test_bid_bond_evidence(runtime: Runtime) -> None:
    assert any("bond" in t.lower() for t in _top(runtime, "Is a bid bond required?", bid_id="Bid1"))


def test_affidavits_for_the_dell_bid(runtime: Runtime) -> None:
    top = _top(runtime, "What affidavits are required?", k=5, bid_id="Bid2")
    assert any("Affidavit" in t for t in top)


def test_delivery_window(runtime: Runtime) -> None:
    assert any(
        "45 days" in t for t in _top(runtime, "What is the delivery timeline?", bid_id="Bid2")
    )
