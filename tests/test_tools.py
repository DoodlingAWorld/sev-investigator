from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import pytest

from sev_investigator.schemas.tools import (
    GetConfigDiffInput,
    GetDependenciesInput,
    GetMetricsInput,
    GetRecentDeploysInput,
    QueryLogsInput,
)
from sev_investigator.tools import INPUT_SCHEMAS, TOOL_REGISTRY, set_fixtures_dir
from sev_investigator.tools.get_config_diff import get_config_diff
from sev_investigator.tools.get_dependencies import get_dependencies
from sev_investigator.tools.get_metrics import get_metrics
from sev_investigator.tools.get_recent_deploys import get_recent_deploys
from sev_investigator.tools.query_logs import query_logs

FIXTURES_DIR = Path(__file__).parent.parent / "samples" / "incident_001_bad_deploy" / "fixtures"

DEPLOY_TIME   = datetime(2026, 4, 15, 14, 23, 0)
INCIDENT_TIME = datetime(2026, 4, 15, 14, 25, 0)


@pytest.fixture(autouse = True)
def configure_fixtures() -> Generator[None, None, None]:
    set_fixtures_dir(FIXTURES_DIR)
    yield
    set_fixtures_dir(None)


# ── query_logs ────────────────────────────────────────────────────────────────

def test_query_logs_returns_entries_in_window() -> None:
    result = query_logs(QueryLogsInput(
        service = "order-service",
        start = datetime(2026, 4, 15, 14, 20, 0),
        end = datetime(2026, 4, 15, 14, 28, 0),
    ))
    assert result.service == "order-service"
    assert result.entries, "Expected log entries for order-service in window, got none"


def test_query_logs_no_errors_before_deploy() -> None:
    result = query_logs(QueryLogsInput(
        service = "order-service",
        start = datetime(2026, 4, 15, 14, 20, 0),
        end = datetime(2026, 4, 15, 14, 24, 59),
    ))
    assert all(e.level != "ERROR" for e in result.entries)


def test_query_logs_errors_appear_after_deploy() -> None:
    result = query_logs(QueryLogsInput(
        service = "order-service",
        start = INCIDENT_TIME,
        end = datetime(2026, 4, 15, 14, 28, 0),
    ))
    error_entries = [e for e in result.entries if e.level == "ERROR"]
    assert error_entries, "Expected ERROR entries after deploy time, got none"


def test_query_logs_level_filter() -> None:
    result = query_logs(QueryLogsInput(
        service = "order-service",
        start = datetime(2026, 4, 15, 14, 20, 0),
        end = datetime(2026, 4, 15, 14, 28, 0),
        level = "ERROR",
    ))
    assert all(e.level == "ERROR" for e in result.entries)


def test_query_logs_unknown_service_returns_empty() -> None:
    result = query_logs(QueryLogsInput(
        service = "unknown-service",
        start = datetime(2026, 4, 15, 14, 20, 0),
        end = datetime(2026, 4, 15, 14, 28, 0),
    ))
    assert result.entries == []


# ── get_recent_deploys ────────────────────────────────────────────────────────

def test_get_recent_deploys_finds_deploy_before_incident() -> None:
    result = get_recent_deploys(GetRecentDeploysInput(
        service = "order-service",
        since = datetime(2026, 4, 15, 14, 0, 0),
    ))
    assert any(d.deployed_at == DEPLOY_TIME for d in result.deploys), (
        f"Expected deploy at {DEPLOY_TIME}, found: {[d.deployed_at for d in result.deploys]}"
    )


def test_get_recent_deploys_respects_since_filter() -> None:
    result = get_recent_deploys(GetRecentDeploysInput(
        service = "order-service",
        since = datetime(2026, 4, 15, 15, 0, 0),
    ))
    assert result.deploys == []


def test_get_recent_deploys_respects_until_filter() -> None:
    result = get_recent_deploys(GetRecentDeploysInput(
        service = "order-service",
        since = datetime(2026, 4, 14, 0, 0, 0),
        until = datetime(2026, 4, 14, 23, 59, 59),
    ))
    assert result.deploys, "Expected at least one April 14 deploy in fixture"
    assert all(d.deployed_at.day == 14 for d in result.deploys)


# ── get_config_diff ───────────────────────────────────────────────────────────

def test_get_config_diff_empty_for_deploy_incident() -> None:
    result = get_config_diff(GetConfigDiffInput(
        service = "order-service",
        since = datetime(2026, 4, 15, 14, 0, 0),
    ))
    assert result.changes == []


# ── get_dependencies ──────────────────────────────────────────────────────────

def test_get_dependencies_returns_all_healthy() -> None:
    result = get_dependencies(GetDependenciesInput(service = "order-service"))
    assert result.dependencies, "Expected dependencies for order-service, got none"
    assert all(d.health == "healthy" for d in result.dependencies)


def test_get_dependencies_unknown_service_returns_empty() -> None:
    result = get_dependencies(GetDependenciesInput(service = "unknown-service"))
    assert result.dependencies == []


# ── get_metrics ───────────────────────────────────────────────────────────────

def test_get_metrics_error_rate_spikes_at_incident_time() -> None:
    result = get_metrics(GetMetricsInput(
        service = "order-service",
        metric = "error_rate",
        start = datetime(2026, 4, 15, 14, 20, 0),
        end = datetime(2026, 4, 15, 14, 28, 0),
    ))
    assert result.unit == "percent"
    baseline = [p.value for p in result.points if p.timestamp < INCIDENT_TIME]
    spike    = [p.value for p in result.points if p.timestamp >= INCIDENT_TIME]
    assert baseline, "Expected baseline points before incident time — fixture may have changed"
    assert spike,    "Expected spike points at/after incident time — fixture may have changed"
    assert all(v < 1.0  for v in baseline), f"Unexpected high values before incident: {baseline}"
    assert all(v > 10.0 for v in spike),    f"Spike values below threshold: {spike}"


def test_get_metrics_time_filter() -> None:
    start = datetime(2026, 4, 15, 14, 20, 0)
    end   = datetime(2026, 4, 15, 14, 22, 0)
    result = get_metrics(GetMetricsInput(
        service = "order-service",
        metric = "error_rate",
        start = start,
        end = end,
    ))
    assert all(start <= p.timestamp <= end for p in result.points)


# ── registry ──────────────────────────────────────────────────────────────────

def test_tool_registry_and_input_schemas_in_sync() -> None:
    assert set(TOOL_REGISTRY.keys()) == set(INPUT_SCHEMAS.keys())
