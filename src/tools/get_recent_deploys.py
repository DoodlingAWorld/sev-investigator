from __future__ import annotations

import json
from datetime import datetime

from sev_investigator.schemas.tools import DeployEvent, GetRecentDeploysInput, GetRecentDeploysResult
from sev_investigator.tools._config import get_fixtures_dir, to_naive


def get_recent_deploys(recent_input: GetRecentDeploysInput) -> GetRecentDeploysResult:
    """Return deploy events for a service within a time window, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "get_recent_deploys.json"
    raw: dict[str, list[dict[str, object]]] = json.loads(fixture_path.read_text())

    since = to_naive(recent_input.since)
    until = to_naive(recent_input.until) if recent_input.until else None

    deploys = [
        DeployEvent.model_validate(d)
        for d in raw.get(recent_input.service, [])
        if since <= datetime.fromisoformat(str(d["deployed_at"]))
        and (until is None or datetime.fromisoformat(str(d["deployed_at"])) <= until)
    ]

    return GetRecentDeploysResult(service = recent_input.service, deploys = deploys)
