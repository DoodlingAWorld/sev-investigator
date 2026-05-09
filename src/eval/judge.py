from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from sev_investigator.llm import parse, system_msg, user_msg
from sev_investigator.prompts import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE
from sev_investigator.schemas.eval import JudgeOutput, ReferenceReport, RubricScore
from sev_investigator.schemas.report import InvestigationReport


class _JudgeResponse(BaseModel):
    """What the LLM produces. Converted to JudgeOutput after parsing."""

    model_config = ConfigDict(extra = "forbid")

    scores: list[RubricScore]
    overall_assessment: str


def score(
    report: InvestigationReport,
    reference: ReferenceReport,
    fixture_data: dict[str, Any] | None = None,
) -> JudgeOutput:
    """Score a generated investigation report against a reference using an LLM judge.

    fixture_data: the raw tool outputs the agent saw, used to ground hallucination scoring.
    """
    fixture_section = (
        "\n\nActual tool outputs (ground truth for hallucination scoring):\n"
        + json.dumps(fixture_data, indent = 2)
        if fixture_data
        else ""
    )

    user = (
        JUDGE_USER_TEMPLATE
        .replace("{reference_json}", reference.model_dump_json(indent = 2))
        .replace("{report_json}", report.model_dump_json(indent = 2))
        .replace("{fixture_json}", fixture_section)
    )

    response = parse(
        messages = [system_msg(JUDGE_SYSTEM_PROMPT), user_msg(user)],
        response_format = _JudgeResponse,
    ).result

    return JudgeOutput.model_validate(response.model_dump())
