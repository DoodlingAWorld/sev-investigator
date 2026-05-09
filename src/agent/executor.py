from __future__ import annotations

from pydantic import TypeAdapter

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState, Evidence, ToolCallPlan
from sev_investigator.schemas.tools import ToolResult
from sev_investigator.tools import INPUT_SCHEMAS, TOOL_REGISTRY

_TOOL_RESULT_ADAPTER: TypeAdapter[ToolResult] = TypeAdapter(ToolResult)


def run(plan: ToolCallPlan, state: AgentState) -> Evidence:
    """Translate a ToolCallPlan into an exact tool call, execute it, and return the evidence."""
    if plan.tool not in INPUT_SCHEMAS or plan.tool not in TOOL_REGISTRY:
        raise ValueError(
            f"Planner requested unknown tool {plan.tool!r}. "
            f"Known tools: {sorted(INPUT_SCHEMAS)}"
        )

    user = (
        EXECUTOR_USER_TEMPLATE
        .replace("{incident_json}", state.incident.model_dump_json(indent = 2))
        .replace("{tool}", plan.tool)
        .replace("{rationale}", plan.rationale)
    )

    tool_input = parse(
        messages = [system_msg(EXECUTOR_SYSTEM_PROMPT), user_msg(user)],
        response_format = INPUT_SCHEMAS[plan.tool],
    ).result

    raw = TOOL_REGISTRY[plan.tool](tool_input)
    result = _TOOL_RESULT_ADAPTER.validate_python(raw.model_dump(mode = "json"))

    return Evidence(
        tool = plan.tool,
        args = tool_input.model_dump(mode = "json"),
        result = result,
    )
