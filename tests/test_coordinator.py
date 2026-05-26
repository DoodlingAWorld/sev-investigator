from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from sev_investigator.agent import MAX_STEPS, coordinator
from sev_investigator.llm import LLMResponse
from sev_investigator.schemas.agent_state import CritiqueOutput, Evidence, PlannerDecision, ToolCallPlan
from sev_investigator.schemas.incident import IncidentEvent
from sev_investigator.schemas.report import (
    InvestigationReport,
    Mitigation,
    RootCauseHypothesis,
    SynthesizerOutput,
)
from sev_investigator.schemas.tools import GetRecentDeploysResult

FIXTURES_DIR = Path(__file__).parent.parent / "samples" / "incident_001_bad_deploy" / "fixtures"

_T = TypeVar("_T", bound=BaseModel)


@pytest.fixture
def incident() -> IncidentEvent:
    return IncidentEvent(
        id = "inc-001",
        title = "order-service 5xx spike",
        type = "deploy_related",
        service = "order-service",
        started_at = datetime(2026, 4, 15, 14, 25, 0),
        description = "Error rate spiked at checkout.",
        severity = "sev2",
    )


def _resp(result: _T) -> LLMResponse[_T]:
    return LLMResponse(result = result, prompt_tokens = 50, completion_tokens = 25, latency_ms = 100.0)


def _fake_evidence() -> Evidence:
    """A minimal Evidence object returned by the mocked executor."""
    return Evidence(
        tool = "get_recent_deploys",
        args = {"service": "order-service", "since": "2026-04-15T14:00:00+00:00"},
        result = GetRecentDeploysResult(service = "order-service", deploys = []),
    )


def _fake_synth_output() -> SynthesizerOutput:
    return SynthesizerOutput(
        timeline = ["14:23 deploy landed", "14:25 errors began"],
        hypotheses = [
            RootCauseHypothesis(
                description = "Deploy at 14:23 introduced a null pointer bug.",
                confidence = 0.9,
                supporting_evidence = ["Deploy at 14:23", "NullPointerException at 14:25"],
                rank = 1,
            )
        ],
        mitigations = [
            Mitigation(action = "Rollback the deploy", priority = "immediate", rationale = "Fastest recovery path.")
        ],
        summary = "Deploy at 14:23 caused the error spike.",
    )


def _fake_critic_accept(messages: Any, response_format: Any, **kwargs: Any) -> Any:
    return _resp(CritiqueOutput(
        verdict = "accept",
        issues = [],
        guidance = "Report is well-supported by the evidence.",
    ))


# ── happy path ────────────────────────────────────────────────────────────────

def test_coordinator_runs_full_loop(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Coordinator runs planner→executor→planner(synthesize)→synthesizer and returns a valid report."""
    planner_calls = 0

    def fake_planner(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls == 1:
            return _resp(PlannerDecision(
                action = "investigate",
                next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "Check for deploys"),
                reasoning = "Check whether a deploy preceded the incident.",
            ))
        return _resp(PlannerDecision(action = "synthesize", next_step = None, reasoning = "Done."))

    executor_calls = 0

    def fake_executor_run(plan: Any, state: Any, rec: Any = None) -> Evidence:
        nonlocal executor_calls
        executor_calls += 1
        return _fake_evidence()

    def fake_synthesizer(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        return _resp(_fake_synth_output())

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = fake_planner)
    mocker.patch("sev_investigator.agent.coordinator.executor.run", side_effect = fake_executor_run)
    mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = fake_synthesizer)
    mocker.patch("sev_investigator.agent.critic.parse", side_effect = _fake_critic_accept)

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    assert report.incident_id == "inc-001"
    assert report.run_id  # non-empty string
    assert planner_calls == 2  # one investigate + one synthesize
    assert executor_calls == 1
    assert len(report.hypotheses) == 1
    assert report.hypotheses[0].confidence == 0.9


def test_coordinator_passes_evidence_to_synthesizer(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Evidence collected from tool calls appears in the synthesizer's user message."""
    planner_calls = 0

    def fake_planner(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls == 1:
            return _resp(PlannerDecision(
                action = "investigate",
                next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "check deploys"),
                reasoning = "Need to look for recent deploys.",
            ))
        return _resp(PlannerDecision(action = "synthesize", next_step = None, reasoning = "Done."))

    def fake_executor_run(plan: Any, state: Any, rec: Any = None) -> Evidence:
        return _fake_evidence()

    captured_user_message: list[str] = []

    def fake_synthesizer(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        user_content: str = next(m["content"] for m in messages if m["role"] == "user")
        captured_user_message[:] = [user_content]
        return _resp(_fake_synth_output())

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = fake_planner)
    mocker.patch("sev_investigator.agent.coordinator.executor.run", side_effect = fake_executor_run)
    mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = fake_synthesizer)
    mocker.patch("sev_investigator.agent.critic.parse", side_effect = _fake_critic_accept)

    coordinator.run(incident, FIXTURES_DIR)

    assert len(captured_user_message) == 1
    assert '"get_recent_deploys"' in captured_user_message[0]


# ── budget exhaustion ─────────────────────────────────────────────────────────

def test_coordinator_stops_at_max_steps(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Coordinator synthesizes after exactly MAX_STEPS when the planner never stops investigating."""
    planner_calls = 0
    executor_calls = 0

    def always_investigate(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        return _resp(PlannerDecision(
            action = "investigate",
            next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "keep checking"),
            reasoning = "Need more data.",
        ))

    def fake_executor_run(plan: Any, state: Any, rec: Any = None) -> Evidence:
        nonlocal executor_calls
        executor_calls += 1
        return _fake_evidence()

    def fake_synthesizer(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        return _resp(SynthesizerOutput(
            timeline = ["14:25 errors started"],
            hypotheses = [
                RootCauseHypothesis(
                    description = "Unknown cause", confidence = 0.3,
                    supporting_evidence = ["Errors observed"], rank = 1,
                )
            ],
            mitigations = [
                Mitigation(action = "Investigate further", priority = "short_term", rationale = "Inconclusive.")
            ],
            summary = "Investigation inconclusive after budget exhaustion.",
        ))

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = always_investigate)
    mocker.patch("sev_investigator.agent.coordinator.executor.run", side_effect = fake_executor_run)
    mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = fake_synthesizer)
    mocker.patch("sev_investigator.agent.critic.parse", side_effect = _fake_critic_accept)

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    assert planner_calls == MAX_STEPS
    assert executor_calls == MAX_STEPS
