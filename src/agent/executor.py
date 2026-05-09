from __future__ import annotations

import time

from pydantic import TypeAdapter

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import EXECUTOR_SYSTEM_PROMPT, EXECUTOR_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState, Evidence, ToolCallPlan
from sev_investigator.schemas.tools import ToolResult
from sev_investigator.tools import INPUT_SCHEMAS, TOOL_REGISTRY
from sev_investigator.traces.recorder import NullRecorder, Recorder

_TOOL_RESULT_ADAPTER: TypeAdapter[ToolResult] = TypeAdapter(ToolResult)
_NULL = NullRecorder()


def run(plan: ToolCallPlan, state: AgentState, recorder: Recorder = _NULL) -> Evidence:
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

    response = parse(
        messages = [system_msg(EXECUTOR_SYSTEM_PROMPT), user_msg(user)],
        response_format = INPUT_SCHEMAS[plan.tool],
    )
    tool_input = response.result

    recorder.emit(
        "executor_call",
        payload = {
            "step": state.step_count,
            "tool": plan.tool,
            "rationale": plan.rationale,
        },
        span_id = f"executor-{state.step_count}",
        parent_span_id = f"planner-{state.step_count}",
        tokens = {"prompt": response.prompt_tokens, "completion": response.completion_tokens},
        latency_ms = response.latency_ms,
    )

    t0 = time.monotonic()
    raw = TOOL_REGISTRY[plan.tool](tool_input)
    tool_latency_ms = (time.monotonic() - t0) * 1000
    result = _TOOL_RESULT_ADAPTER.validate_python(raw.model_dump(mode = "json"))

    tool_args = tool_input.model_dump(mode = "json")

    recorder.emit(
        "tool_call",
        payload = {
            "step": state.step_count,
            "tool": plan.tool,
            "args": tool_args,
            "result": result.model_dump(mode = "json"),
        },
        span_id = f"tool-{state.step_count}",
        parent_span_id = f"executor-{state.step_count}",
        latency_ms = tool_latency_ms,
    )

    return Evidence(
        tool = plan.tool,
        args = tool_args,
        result = result,
    )
