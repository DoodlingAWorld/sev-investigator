from __future__ import annotations

import json

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import SYNTHESIZER_SYSTEM_PROMPT, SYNTHESIZER_USER_TEMPLATE
from sev_investigator.schemas.agent_state import AgentState
from sev_investigator.schemas.report import InvestigationReport, SynthesizerOutput


def run(state: AgentState) -> InvestigationReport:
    """Synthesize all collected evidence into a structured investigation report."""
    evidence_str = json.dumps(
        [e.model_dump(mode = "json") for e in state.evidence], indent = 2
    )

    user = (
        SYNTHESIZER_USER_TEMPLATE
        .replace("{incident_json}", state.incident.model_dump_json(indent = 2))
        .replace("{evidence_str}", evidence_str)
    )

    output = parse(
        messages = [system_msg(SYNTHESIZER_SYSTEM_PROMPT), user_msg(user)],
        response_format = SynthesizerOutput,
    ).result

    return InvestigationReport(
        **output.model_dump(),
        run_id = state.run_id,
        incident_id = state.incident.id,
    )
