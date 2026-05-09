from __future__ import annotations

import json
from datetime import datetime

from sev_investigator.schemas.tools import ConfigChange, GetConfigDiffInput, GetConfigDiffResult
from sev_investigator.tools._config import get_fixtures_dir


def get_config_diff(inp: GetConfigDiffInput) -> GetConfigDiffResult:
    """Return config changes for a service within a time window, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "get_config_diff.json"
    raw: dict[str, list[dict[str, object]]] = json.loads(fixture_path.read_text())

    until = inp.until



    changes = [
        ConfigChange.model_validate(c)
        for c in raw.get(inp.service, [])
        if inp.since <= datetime.fromisoformat(str(c["changed_at"]))
        and (until is None or datetime.fromisoformat(str(c["changed_at"])) <= until)
    ]

    return GetConfigDiffResult(service=inp.service, changes=changes)
