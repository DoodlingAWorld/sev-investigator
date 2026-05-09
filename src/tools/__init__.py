from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from sev_investigator.tools._config import set_fixtures_dir as set_fixtures_dir
from sev_investigator.tools.get_config_diff import get_config_diff
from sev_investigator.tools.get_dependencies import get_dependencies
from sev_investigator.tools.get_metrics import get_metrics
from sev_investigator.tools.get_recent_deploys import get_recent_deploys
from sev_investigator.tools.query_logs import query_logs
from sev_investigator.schemas.tools import (
    GetConfigDiffInput,
    GetDependenciesInput,
    GetMetricsInput,
    GetRecentDeploysInput,
    QueryLogsInput,
)

TOOL_REGISTRY: dict[str, Callable[[Any], BaseModel]] = {
    "query_logs": query_logs,
    "get_recent_deploys": get_recent_deploys,
    "get_config_diff": get_config_diff,
    "get_dependencies": get_dependencies,
    "get_metrics": get_metrics,
}

INPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "query_logs": QueryLogsInput,
    "get_recent_deploys": GetRecentDeploysInput,
    "get_config_diff": GetConfigDiffInput,
    "get_dependencies": GetDependenciesInput,
    "get_metrics": GetMetricsInput,
}

__all__ = [
    "set_fixtures_dir",
    "TOOL_REGISTRY",
    "INPUT_SCHEMAS",
]
