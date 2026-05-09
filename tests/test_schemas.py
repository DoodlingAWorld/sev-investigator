from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from sev_investigator.schemas.agent_state import AgentState, PlannerDecision, ToolCallPlan
from sev_investigator.schemas.eval import JudgeOutput, RubricScore
from sev_investigator.schemas.incident import IncidentEvent
from sev_investigator.schemas.report import (
    InvestigationReport,
    Mitigation,
    RootCauseHypothesis,
    SynthesizerOutput,
)
from sev_investigator.schemas.tools import GetRecentDeploysResult, QueryLogsResult


@pytest.fixture
def sample_incident() -> IncidentEvent:
    return IncidentEvent(
        id = "inc-001",
        title = "order-service 5xx spike",
        type = "deploy_related",
        service = "order-service",
        started_at = datetime(2026, 4, 15, 14, 25, 0),
        description = "Error rate spiked at checkout.",
        severity = "sev2",
    )


def test_incident_event_constructs() -> None:
    incident = IncidentEvent(
        id = "inc-001",
        title = "order-service 5xx spike",
        type = "deploy_related",
        service = "order-service",
        started_at = datetime(2026, 4, 15, 14, 25, 0),
        description = "Something broke.",
        severity = "sev2",
    )
    assert incident.id == "inc-001"
    assert incident.service == "order-service"
    assert incident.type == "deploy_related"


def test_incident_event_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        IncidentEvent(
            id = "inc-001",
            title = "test",
            type = "unknown_type",
            service = "svc",
            started_at = datetime(2026, 1, 1),
            description = "test",
            severity = "sev1",
        )


def test_planner_decision_investigate_requires_next_step() -> None:
    with pytest.raises(ValidationError):
        PlannerDecision(action = "investigate", next_step = None, reasoning = "test")


def test_planner_decision_synthesize_allows_no_next_step() -> None:
    decision = PlannerDecision(action = "synthesize", next_step = None, reasoning = "enough evidence")
    assert decision.action == "synthesize"
    assert decision.next_step is None


def test_planner_decision_investigate_with_next_step() -> None:
    plan = ToolCallPlan(tool = "query_logs", rationale = "check logs")
    decision = PlannerDecision(action = "investigate", next_step = plan, reasoning = "need logs")
    assert decision.next_step is not None
    assert decision.next_step.tool == "query_logs"


def test_tool_result_discriminated_union() -> None:
    result = QueryLogsResult(service = "order-service", entries = [])
    assert result.tool_name == "query_logs"

    result2 = GetRecentDeploysResult(service = "order-service", deploys = [])
    assert result2.tool_name == "get_recent_deploys"


def test_judge_output_computed_totals() -> None:
    scores = [
        RubricScore(dimension = "root_cause_accuracy",      score = 3, reasoning = "correct"),
        RubricScore(dimension = "evidence_quality",         score = 2, reasoning = "adequate"),
        RubricScore(dimension = "hypothesis_completeness",  score = 1, reasoning = "partial"),
        RubricScore(dimension = "mitigation_utility",       score = 3, reasoning = "actionable"),
        RubricScore(dimension = "hallucination",            score = 3, reasoning = "no hallucinations"),
    ]
    output = JudgeOutput(scores = scores, overall_assessment = "good")
    assert output.total == 12
    assert output.max_total == 15  # always 5 dimensions × 3


def test_synthesizer_output_propagates_to_report() -> None:
    output = SynthesizerOutput(
        timeline = ["14:23 deploy landed", "14:25 errors began"],
        hypotheses = [
            RootCauseHypothesis(
                description = "Null pointer in promo code handler",
                confidence = 0.9,
                supporting_evidence = ["NullPointerException in logs at 14:25"],
                rank = 1,
            )
        ],
        mitigations = [
            Mitigation(action = "Rollback to previous deploy", priority = "immediate", rationale = "Fastest path to recovery")
        ],
        summary = "Deploy at 14:23 introduced a null pointer bug.",
    )

    report = InvestigationReport(
        **output.model_dump(),
        run_id = "abc123",
        incident_id = "inc-001",
    )

    assert report.run_id == "abc123"
    assert report.incident_id == "inc-001"
    assert report.summary == output.summary
    assert len(report.hypotheses) == 1
    assert report.hypotheses[0].confidence == 0.9


def test_agent_state_initialises_empty_evidence(sample_incident: IncidentEvent) -> None:
    state = AgentState(incident = sample_incident, skill_name = "deploy_related")
    assert state.evidence == []
    assert state.step_count == 0
    assert len(state.run_id) == 8
