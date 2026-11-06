from pathlib import Path

import pytest

from rfp_intel.security import PathNotAllowedError, resolve_within


def test_relative_path_inside_base(data_dir: Path) -> None:
    assert resolve_within(data_dir, "BidA") == (data_dir / "BidA").resolve()


def test_absolute_path_inside_base(data_dir: Path) -> None:
    target = (data_dir / "BidA").resolve()
    assert resolve_within(data_dir, target) == target


@pytest.mark.parametrize("candidate", ["..", "../..", "BidA/../../etc", "../bids-other"])
def test_traversal_is_rejected(data_dir: Path, candidate: str) -> None:
    with pytest.raises(PathNotAllowedError):
        resolve_within(data_dir, candidate)


def test_absolute_path_elsewhere_is_rejected(data_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(PathNotAllowedError):
        resolve_within(data_dir, tmp_path)
