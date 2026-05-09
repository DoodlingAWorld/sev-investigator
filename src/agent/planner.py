from __future__ import annotations

import json

from sev_investigator.agent import MAX_STEPS
from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import PLANNER_SYSTEM_PROMPT, PLANNER_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState, PlannerDecision
from sev_investigator.skills.base import Skill


def run(state: AgentState, skill: Skill) -> PlannerDecision:
    """Decide what to investigate next, or whether to synthesize."""
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

    return parse(
        messages = [system_msg(system), user_msg(user)],
        response_format = PlannerDecision,
    ).result
