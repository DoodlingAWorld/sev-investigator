from __future__ import annotations

from datetime import datetime
from pathlib import Path

_fixtures_dir: Path | None = None


def set_fixtures_dir(path: Path | None) -> None:
    """Point the mock tools at a specific incident's fixture directory. Pass None to reset."""
    global _fixtures_dir
    _fixtures_dir = path


def get_fixtures_dir() -> Path:
    if _fixtures_dir is None:
        raise RuntimeError(
            "Fixtures directory not configured. Call set_fixtures_dir() before using tools."
        )
    return _fixtures_dir


def to_naive(dt: datetime) -> datetime:
    """Strip timezone info so LLM-supplied aware datetimes can be compared with naive fixture timestamps."""
    return dt.replace(tzinfo=None)
