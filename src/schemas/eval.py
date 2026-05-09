from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from sev_investigator.schemas.report import InvestigationReport


class RubricScore(BaseModel):
    dimension: str
    score: int = Field(ge=0, le=3)
    reasoning: str


class JudgeOutput(BaseModel):
    """Structured output of the LLM-as-judge for a single investigation."""

    scores: list[RubricScore]
    overall_assessment: str

    @computed_field  # type: ignore[misc]
    @property
    def total(self) -> int:
        return sum(s.score for s in self.scores)

    @computed_field  # type: ignore[misc]
    @property
    def max_total(self) -> int:
        return len(self.scores) * 3


class EvalResult(BaseModel):
    incident_id: str
    judge_output: JudgeOutput
    generated_report: InvestigationReport
