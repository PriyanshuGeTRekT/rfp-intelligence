"""Small security helpers used by the API and CLI."""

from pathlib import Path


class PathNotAllowedError(ValueError):
    """A user-supplied path resolves outside the directory it is allowed to read."""


def resolve_within(base: Path, candidate: str | Path) -> Path:
    """Resolve `candidate` against `base` and refuse anything that escapes `base`.

    Relative paths are taken relative to `base`. `..` segments, absolute paths elsewhere and
    symlinks pointing outside are all rejected because the check runs on the resolved path.
    """
    base_resolved = base.resolve()
    path = Path(candidate)
    target = (path if path.is_absolute() else base_resolved / path).resolve()
    if not target.is_relative_to(base_resolved):
        raise PathNotAllowedError(f"path is outside the data directory: {candidate}")
    return target
