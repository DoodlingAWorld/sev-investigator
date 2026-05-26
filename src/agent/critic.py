from __future__ import annotations

import json

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import CRITIC_SYSTEM_PROMPT, CRITIC_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState, CritiqueOutput
from sev_investigator.schemas.report import InvestigationReport
from sev_investigator.traces.recorder import NullRecorder, Recorder

_NULL = NullRecorder()


def run(
    state: AgentState,
    report: InvestigationReport,
    recorder: Recorder = _NULL,
) -> CritiqueOutput:
    """Evaluate a candidate report against the collected evidence and return a verdict."""
    evidence_str = json.dumps(
        [e.model_dump(mode = "json") for e in state.evidence], indent = 2
    )

    user = (
        CRITIC_USER_TEMPLATE
        .replace("{incident_json}", state.incident.model_dump_json(indent = 2))
        .replace("{evidence_str}", evidence_str)
        .replace("{report_json}", report.model_dump_json(indent = 2))
    )

    response = parse(
        messages = [system_msg(CRITIC_SYSTEM_PROMPT), user_msg(user)],
        response_format = CritiqueOutput,
    )
    critique = response.result

    recorder.emit(
        "critic_call",
        payload = {
            "round": state.reflection_rounds,
            "verdict": critique.verdict,
            "issue_count": len(critique.issues),
            "guidance": critique.guidance[:120],
        },
        span_id = f"critic-{state.reflection_rounds}",
        parent_span_id = "coordinator",
        tokens = {"prompt": response.prompt_tokens, "completion": response.completion_tokens},
        latency_ms = response.latency_ms,
    )

    return critique
