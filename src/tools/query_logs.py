from __future__ import annotations

import json

from sev_investigator.schemas.tools import LogEntry, QueryLogsInput, QueryLogsResult
from sev_investigator.tools._config import get_fixtures_dir, to_naive


def query_logs(query_input: QueryLogsInput) -> QueryLogsResult:
    """Return log entries for a service within a time window, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "query_logs.json"
    raw: dict[str, list[dict[str, object]]] = json.loads(fixture_path.read_text())

    start = to_naive(query_input.start)
    end   = to_naive(query_input.end)

    entries = [LogEntry.model_validate(e) for e in raw.get(query_input.service, [])]
    entries = [e for e in entries if start <= e.timestamp <= end]

    if query_input.level is not None:
        entries = [e for e in entries if e.level == query_input.level]

    return QueryLogsResult(service = query_input.service, entries = entries)
