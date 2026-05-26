from __future__ import annotations

import json

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import (
    SYNTHESIZER_REVISION_FRAGMENT,
    SYNTHESIZER_SYSTEM_PROMPT,
    SYNTHESIZER_USER_TEMPLATE,
)
from sev_investigator.schemas.agent_state import AgentState, CritiqueOutput
from sev_investigator.schemas.report import InvestigationReport, SynthesizerOutput
from sev_investigator.traces.recorder import NullRecorder, Recorder

_NULL = NullRecorder()


def run(
    state: AgentState,
    recorder: Recorder = _NULL,
    prior_critique: CritiqueOutput | None = None,
) -> InvestigationReport:
    """Synthesize all collected evidence into a structured investigation report.

    When prior_critique is provided, the critic's feedback is appended to the prompt
    so the synthesizer can address identified issues in this revised draft.
    """
    evidence_str = json.dumps(
        [e.model_dump(mode = "json") for e in state.evidence], indent = 2
    )

    user = (
        SYNTHESIZER_USER_TEMPLATE
        .replace("{incident_json}", state.incident.model_dump_json(indent = 2))
        .replace("{evidence_str}", evidence_str)
    )

    if prior_critique is not None:
        issues_str = "; ".join(prior_critique.issues) if prior_critique.issues else "none listed"
        revision_fragment = (
            SYNTHESIZER_REVISION_FRAGMENT
            .replace("{issues_str}", issues_str)
            .replace("{guidance}", prior_critique.guidance)
        )
        user = user + "\n\n" + revision_fragment

    response = parse(
        messages = [system_msg(SYNTHESIZER_SYSTEM_PROMPT), user_msg(user)],
        response_format = SynthesizerOutput,
    )

    span_id = (
        "synthesizer"
        if prior_critique is None
        else f"synthesizer-rev-{state.reflection_rounds}"
    )

    recorder.emit(
        "synthesizer_call",
        payload = {"evidence_count": len(state.evidence)},
        span_id = span_id,
        parent_span_id = "coordinator",
        tokens = {"prompt": response.prompt_tokens, "completion": response.completion_tokens},
        latency_ms = response.latency_ms,
    )

    return InvestigationReport(
        **response.result.model_dump(),
        run_id = state.run_id,
        incident_id = state.incident.id,
    )
