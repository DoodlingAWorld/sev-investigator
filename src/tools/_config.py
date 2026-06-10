from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

_local = threading.local()


def set_fixtures_dir(path: Path | None) -> None:
    """Point the mock tools at a specific incident's fixture directory. Pass None to reset."""
    _local.fixtures_dir = path


def get_fixtures_dir() -> Path:
    path: Path | None = getattr(_local, "fixtures_dir", None)
    if path is None:
        raise RuntimeError(
            "Fixtures directory not configured. Call set_fixtures_dir() before using tools."
        )
    return path


def to_naive(dt: datetime) -> datetime:
    """Strip timezone info so LLM-supplied aware datetimes can be compared with naive fixture timestamps."""
    return dt.replace(tzinfo=None)
