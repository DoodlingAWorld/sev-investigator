from __future__ import annotations

import json

from sev_investigator.agent import MAX_STEPS
from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import PLANNER_GUIDANCE_FRAGMENT, PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState, PlannerDecision
from sev_investigator.skills.base import Skill
from sev_investigator.traces.recorder import NullRecorder, Recorder

_NULL = NullRecorder()


def run(
    state: AgentState,
    skill: Skill,
    recorder: Recorder = _NULL,
    guidance: str | None = None,
) -> PlannerDecision:
    """Decide what to investigate next, or whether to synthesize.

    When guidance is provided (from a critic's investigate_more verdict), it is
    appended to the user prompt to steer the re-investigation.
    """
    evidence_str = (
        json.dumps([e.model_dump(mode = "json") for e in state.evidence], indent = 2)
        if state.evidence
        else "No evidence collected yet."
    )

    system = PLANNER_SYSTEM_PROMPT.replace("{skill_prompt}", skill.system_prompt_fragment)
    user = (
        PLANNER_USER_TEMPLATE
        .replace("{incident_json}", state.incident.model_dump_json(indent = 2))
        .replace("{step_count}", str(state.step_count))
        .replace("{max_steps}", str(MAX_STEPS))
        .replace("{tool_whitelist}", ", ".join(skill.tool_whitelist))
        .replace("{evidence_str}", evidence_str)
    )

    if guidance is not None:
        user = user + "\n\n" + PLANNER_GUIDANCE_FRAGMENT.replace("{guidance}", guidance)

    response = parse(
        messages = [system_msg(system), user_msg(user)],
        response_format = PlannerDecision,
    )
    decision = response.result

    recorder.emit(
        "planner_call",
        payload = {
            "step": state.step_count,
            "action": decision.action,
            "reasoning": decision.reasoning,
            "next_tool": decision.next_step.tool if decision.next_step else None,
        },
        span_id = f"planner-{state.step_count}",
        parent_span_id = "coordinator",
        tokens = {"prompt": response.prompt_tokens, "completion": response.completion_tokens},
        latency_ms = response.latency_ms,
    )

    return decision
