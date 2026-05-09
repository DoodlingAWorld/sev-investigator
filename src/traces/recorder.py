from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Recorder:
    """Writes structured trace events to a JSONL file for a single investigation run."""

    def __init__(self, run_id: str, traces_dir: Path = Path("traces")) -> None:
        self.run_id = run_id
        traces_dir.mkdir(parents = True, exist_ok = True)
        self._path = traces_dir / f"{run_id}.jsonl"
        self._file = self._path.open("a", encoding = "utf-8")

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        tokens: dict[str, int] | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """Write one trace event as a JSON line."""
        event: dict[str, Any] = {
            "timestamp": datetime.now(tz = timezone.utc).isoformat(),
            "event_type": event_type,
            "span_id": span_id or str(uuid.uuid4())[:8],
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        if tokens is not None:
            event["tokens"] = tokens
        if latency_ms is not None:
            event["latency_ms"] = round(latency_ms, 2)
        self._file.write(json.dumps(event) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "Recorder":
        return self

    def __exit__(self, *args: object) -> None:
        try:
            self.close()
        except OSError:
            pass  # don't mask the original exception with a close/flush error


class NullRecorder(Recorder):
    """A no-op recorder used as the default when tracing is not needed."""

    def __init__(self) -> None:
        pass  # intentionally does not open a file because we only need it as a class object

    def emit(self, event_type: str, payload: dict[str, Any], **kwargs: Any) -> None:
        pass

    def close(self) -> None:
        pass

    def __exit__(self, *args: object) -> None:
        pass
