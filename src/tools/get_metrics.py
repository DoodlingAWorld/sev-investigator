from __future__ import annotations

import json
from datetime import datetime
from typing import cast

from sev_investigator.schemas.tools import GetMetricsInput, GetMetricsResult, MetricPoint
from sev_investigator.tools._config import get_fixtures_dir, to_naive


def get_metrics(metrics_input: GetMetricsInput) -> GetMetricsResult:
    """Return time-series metric data for a service, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "get_metrics.json"
    raw: dict[str, dict[str, dict[str, object]]] = json.loads(fixture_path.read_text())

    metric_data = raw.get(metrics_input.service, {}).get(metrics_input.metric, {})
    unit = str(metric_data.get("unit") or "")
    raw_points = cast(list[dict[str, object]], metric_data.get("points", []))

    start = to_naive(metrics_input.start)
    end   = to_naive(metrics_input.end)

    points = [
        MetricPoint.model_validate(p)
        for p in raw_points
        if start <= datetime.fromisoformat(str(p["timestamp"])) <= end
    ]

    return GetMetricsResult(service = metrics_input.service, metric = metrics_input.metric, unit = unit, points = points)
