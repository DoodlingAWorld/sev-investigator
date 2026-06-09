from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from sev_investigator.agent import MAX_REFLECTION_ROUNDS, coordinator
from sev_investigator.llm import LLMResponse
from sev_investigator.schemas.agent_state import (
    AgentState,
    CritiqueOutput,
    Evidence,
    PlannerDecision,
    ToolCallPlan,
)
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


# ── Shared fixtures ───────────────────────────────────────────────────────────

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
    return LLMResponse(result = result, prompt_tokens = 50, completion_tokens = 20, latency_ms = 80.0)


def _fake_evidence() -> Evidence:
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
            Mitigation(action = "Rollback the deploy", priority = "immediate", rationale = "Fastest recovery.")
        ],
        summary = "Deploy at 14:23 caused the error spike.",
    )


def _accept() -> CritiqueOutput:
    return CritiqueOutput(verdict = "accept", issues = [], guidance = "Report is well-supported.")


def _revise(issue: str = "Hypothesis lacks specific log reference.") -> CritiqueOutput:
    return CritiqueOutput(
        verdict = "revise",
        issues = [issue],
        guidance = "Cite the exact log entry that triggered the NullPointerException.",
    )


# ── Shared coordinator mock wiring ────────────────────────────────────────────

def _wire_planner_executor_synthesizer(
    mocker: MockerFixture,
    synth_side_effect: Any = None,
) -> None:
    planner_calls = 0

    def fake_planner(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls == 1:
            return _resp(PlannerDecision(
                action = "investigate",
                next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "Check for deploys"),
                reasoning = "Check recent deploys.",
            ))
        return _resp(PlannerDecision(action = "synthesize", next_step = None, reasoning = "Done."))

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = fake_planner)
    mocker.patch(
        "sev_investigator.agent.coordinator.executor.run",
        side_effect = lambda plan, state, rec = None: _fake_evidence(),
    )

    if synth_side_effect is None:
        mocker.patch(
            "sev_investigator.agent.synthesizer.parse",
            side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
        )
    else:
        mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = synth_side_effect)


# ── Critic unit tests ─────────────────────────────────────────────────────────

def test_critic_accept_path(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Coordinator accepts on the first critic pass and does not re-synthesize."""
    _wire_planner_executor_synthesizer(mocker)
    synth_call_count = [0]

    original_synth = mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )
    mocker.patch(
        "sev_investigator.agent.critic.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_accept()),
    )

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    # critic accepted on first pass — synthesizer called exactly once
    assert original_synth.call_count == 1


def test_critic_revise_then_accept(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Coordinator re-synthesizes on revise, then accepts on second critic pass."""
    _wire_planner_executor_synthesizer(mocker)

    synth_mock = mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )

    critic_calls = 0

    def fake_critic(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal critic_calls
        critic_calls += 1
        return _resp(_revise() if critic_calls == 1 else _accept())

    mocker.patch("sev_investigator.agent.critic.parse", side_effect = fake_critic)

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    assert critic_calls == 2                # revise → accept
    assert synth_mock.call_count == 2       # initial + one revision


def test_critic_revision_appends_feedback_to_prompt(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """When the critic requests a revision, the second synthesizer call includes critic guidance."""
    _wire_planner_executor_synthesizer(mocker)

    synth_call = 0
    captured_revision_user: list[str] = []

    def fake_synth(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal synth_call
        synth_call += 1
        if synth_call == 2:
            user_content: str = next(m["content"] for m in messages if m["role"] == "user")
            captured_revision_user.append(user_content)
        return _resp(_fake_synth_output())

    mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = fake_synth)

    critic_calls = 0

    def fake_critic(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal critic_calls
        critic_calls += 1
        return _resp(_revise("Hypothesis lacks specific log reference.") if critic_calls == 1 else _accept())

    mocker.patch("sev_investigator.agent.critic.parse", side_effect = fake_critic)

    coordinator.run(incident, FIXTURES_DIR)

    assert len(captured_revision_user) == 1
    assert "Critic feedback" in captured_revision_user[0]
    assert "Hypothesis lacks specific log reference" in captured_revision_user[0]


def test_critic_cap_terminates_loop(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Reflection loop terminates at MAX_REFLECTION_ROUNDS even if critic keeps returning revise."""
    _wire_planner_executor_synthesizer(mocker)

    synth_mock = mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )

    critic_mock = mocker.patch(
        "sev_investigator.agent.critic.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_revise()),
    )

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    # critic called exactly MAX_REFLECTION_ROUNDS times (loop exits after cap)
    assert critic_mock.call_count == MAX_REFLECTION_ROUNDS
    # synthesizer: 1 initial + MAX_REFLECTION_ROUNDS revisions
    assert synth_mock.call_count == MAX_REFLECTION_ROUNDS + 1


def test_investigate_more_triggers_re_investigation(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """On investigate_more, coordinator re-enters planner/executor before re-synthesizing."""
    planner_calls = 0

    def fake_planner(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        # calls 1+2: initial investigate→synthesize loop
        # calls 3+4: re-investigation investigate→synthesize loop
        if planner_calls in (1, 3):
            return _resp(PlannerDecision(
                action = "investigate",
                next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "check deploys"),
                reasoning = "Need more data.",
            ))
        return _resp(PlannerDecision(action = "synthesize", next_step = None, reasoning = "Done."))

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = fake_planner)

    executor_calls = 0

    def fake_executor(plan: Any, state: Any, rec: Any = None) -> Evidence:
        nonlocal executor_calls
        executor_calls += 1
        return _fake_evidence()

    mocker.patch(
        "sev_investigator.agent.coordinator.executor.run",
        side_effect = fake_executor,
    )

    synth_mock = mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )

    critic_calls = 0

    def fake_critic(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal critic_calls
        critic_calls += 1
        if critic_calls == 1:
            return _resp(CritiqueOutput(
                verdict = "investigate_more",
                issues = ["Dependencies not checked."],
                guidance = "Check dependency health for the affected service.",
                missing_evidence = ["get_dependencies"],
            ))
        return _resp(_accept())

    mocker.patch("sev_investigator.agent.critic.parse", side_effect = fake_critic)

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    assert critic_calls == 2                 # investigate_more → accept
    assert executor_calls == 2               # 1 initial + 1 re-investigation
    assert planner_calls == 4                # investigate, synthesize, investigate, synthesize
    assert synth_mock.call_count == 2        # initial + post-re-investigation


def test_investigate_more_guidance_appears_in_planner_prompt(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """The critic's guidance is forwarded to the planner during re-investigation."""
    planner_calls = 0
    captured_reinvestigation_user: list[str] = []

    def fake_planner(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        if planner_calls == 3:
            user_content: str = next(m["content"] for m in messages if m["role"] == "user")
            captured_reinvestigation_user.append(user_content)
        if planner_calls in (1, 3):
            return _resp(PlannerDecision(
                action = "investigate",
                next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "check"),
                reasoning = "Checking.",
            ))
        return _resp(PlannerDecision(action = "synthesize", next_step = None, reasoning = "Done."))

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = fake_planner)
    mocker.patch(
        "sev_investigator.agent.coordinator.executor.run",
        side_effect = lambda plan, state, rec = None: _fake_evidence(),
    )
    mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )

    critic_calls = 0

    def fake_critic(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal critic_calls
        critic_calls += 1
        if critic_calls == 1:
            return _resp(CritiqueOutput(
                verdict = "investigate_more",
                issues = ["Dependencies not checked."],
                guidance = "Check dependency health for the affected service.",
                missing_evidence = ["get_dependencies"],
            ))
        return _resp(_accept())

    mocker.patch("sev_investigator.agent.critic.parse", side_effect = fake_critic)

    coordinator.run(incident, FIXTURES_DIR)

    assert len(captured_reinvestigation_user) == 1
    assert "Critic guidance" in captured_reinvestigation_user[0]
    assert "Check dependency health" in captured_reinvestigation_user[0]


def test_investigate_more_budget_exhausted_falls_back_to_revise(
    mocker: MockerFixture, incident: IncidentEvent
) -> None:
    """When step budget is already exhausted, investigate_more is treated as revise."""
    from sev_investigator.agent import MAX_STEPS

    # Fill up the step budget in the initial loop
    planner_calls = 0

    def always_investigate(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal planner_calls
        planner_calls += 1
        return _resp(PlannerDecision(
            action = "investigate",
            next_step = ToolCallPlan(tool = "get_recent_deploys", rationale = "keep checking"),
            reasoning = "Need more data.",
        ))

    mocker.patch("sev_investigator.agent.planner.parse", side_effect = always_investigate)
    mocker.patch(
        "sev_investigator.agent.coordinator.executor.run",
        side_effect = lambda plan, state, rec = None: _fake_evidence(),
    )

    synth_mock = mocker.patch(
        "sev_investigator.agent.synthesizer.parse",
        side_effect = lambda messages, response_format, **kwargs: _resp(_fake_synth_output()),
    )

    critic_calls = 0

    def fake_critic(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        nonlocal critic_calls
        critic_calls += 1
        if critic_calls == 1:
            return _resp(CritiqueOutput(
                verdict = "investigate_more",
                issues = ["Dependencies not checked."],
                guidance = "Check dependency health.",
                missing_evidence = ["get_dependencies"],
            ))
        return _resp(_accept())

    mocker.patch("sev_investigator.agent.critic.parse", side_effect = fake_critic)

    report = coordinator.run(incident, FIXTURES_DIR)

    assert isinstance(report, InvestigationReport)
    # planner never called again after budget exhausted (only MAX_STEPS calls in initial loop)
    assert planner_calls == MAX_STEPS
    # synthesizer still called twice: initial + revision with critique as guidance
    assert synth_mock.call_count == 2


def test_synthesizer_no_critique_unchanged(mocker: MockerFixture, incident: IncidentEvent) -> None:
    """Calling synthesizer.run with no prior_critique produces the same prompt as before."""
    from sev_investigator.agent import synthesizer
    from sev_investigator.schemas.agent_state import AgentState

    state = AgentState(
        incident = incident,
        skill_name = "deploy_related",
        evidence = [_fake_evidence()],
    )

    captured: list[str] = []

    def fake_parse(messages: Any, response_format: Any, **kwargs: Any) -> Any:
        user_content: str = next(m["content"] for m in messages if m["role"] == "user")
        captured.append(user_content)
        return _resp(_fake_synth_output())

    mocker.patch("sev_investigator.agent.synthesizer.parse", side_effect = fake_parse)

    synthesizer.run(state)

    assert len(captured) == 1
    # No revision fragment should appear when no critique is passed
    assert "Critic feedback" not in captured[0]
