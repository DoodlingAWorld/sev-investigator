from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ── Log querying ──────────────────────────────────────────────────────────────

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LogEntry(BaseModel):
    timestamp: datetime
    level: LogLevel
    message: str


class QueryLogsInput(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    service: str
    start: datetime
    end: datetime
    level: LogLevel | None = None


class QueryLogsResult(BaseModel):
    tool_name: Literal["query_logs"] = "query_logs"
    service: str
    entries: list[LogEntry]


# ── Recent deploys ────────────────────────────────────────────────────────────

class DeployEvent(BaseModel):
    deployed_at: datetime
    commit_hash: str
    files_changed: int
    deployed_by: str
    description: str


class GetRecentDeploysInput(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    service: str
    since: datetime
    until: datetime | None = None


class GetRecentDeploysResult(BaseModel):
    tool_name: Literal["get_recent_deploys"] = "get_recent_deploys"
    service: str
    deploys: list[DeployEvent]


# ── Config diff ───────────────────────────────────────────────────────────────

class ConfigChange(BaseModel):
    changed_at: datetime
    key: str
    old_value: str
    new_value: str
    changed_by: str


class GetConfigDiffInput(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    service: str
    since: datetime
    until: datetime | None = None


class GetConfigDiffResult(BaseModel):
    tool_name: Literal["get_config_diff"] = "get_config_diff"
    service: str
    changes: list[ConfigChange]


# ── Dependencies ──────────────────────────────────────────────────────────────

class Dependency(BaseModel):
    name: str
    type: Literal["database", "cache", "service", "queue"]
    health: Literal["healthy", "degraded", "down"] | None = None


class GetDependenciesInput(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    service: str


class GetDependenciesResult(BaseModel):
    tool_name: Literal["get_dependencies"] = "get_dependencies"
    service: str
    dependencies: list[Dependency]


# ── Metrics ───────────────────────────────────────────────────────────────────

class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


MetricName = Literal["error_rate", "latency_p50", "latency_p99", "request_rate", "cache_hit_rate"]


class GetMetricsInput(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    service: str
    metric: MetricName
    start: datetime
    end: datetime


class GetMetricsResult(BaseModel):
    tool_name: Literal["get_metrics"] = "get_metrics"
    service: str
    metric: MetricName
    unit: str
    points: list[MetricPoint]


# ── Union ─────────────────────────────────────────────────────────────────────

ToolResult = Annotated[
    Union[
        QueryLogsResult,
        GetRecentDeploysResult,
        GetConfigDiffResult,
        GetDependenciesResult,
        GetMetricsResult,
    ],
    Field(discriminator="tool_name"),
]
