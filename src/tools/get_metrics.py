from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from sev_investigator.schemas.tools import GetMetricsInput, GetMetricsResult, MetricPoint
from sev_investigator.tools._config import get_fixtures_dir


def get_metrics(metrics_inp: GetMetricsInput) -> GetMetricsResult:
    """Return time-series metric data for a service, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "get_metrics.json"
    raw: dict[str, dict[str, dict[str, object]]] = json.loads(fixture_path.read_text())

    metric_data = raw.get(metrics_inp.service, {}).get(metrics_inp.metric, {})
    unit = str(metric_data.get("unit") or "")
    raw_points = cast(list[dict[str, object]], metric_data.get("points", []))

    points = [
        MetricPoint.model_validate(p)
        for p in raw_points
        if metrics_inp.start <= datetime.fromisoformat(str(p["timestamp"])) <= metrics_inp.end
    ]

    return GetMetricsResult(service = metrics_inp.service, metric = metrics_inp.metric, unit = unit, points = points)
