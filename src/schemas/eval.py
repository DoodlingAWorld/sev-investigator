from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from sev_investigator.schemas.report import InvestigationReport

RUBRIC_DIMENSIONS = (
    "root_cause_accuracy",
    "evidence_quality",
    "hypothesis_completeness",
    "mitigation_utility",
    "hallucination",
)

_NUM_DIMENSIONS = len(RUBRIC_DIMENSIONS)
_MAX_SCORE = 3


class RubricScore(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    dimension: str
    score: int = Field(ge=0, le=_MAX_SCORE)
    reasoning: str

    @field_validator("dimension")
    @classmethod
    def dimension_must_be_valid(cls, v: str) -> str:
        if v not in RUBRIC_DIMENSIONS:
            raise ValueError(
                f"Unknown rubric dimension {v!r}. Must be one of {RUBRIC_DIMENSIONS}"
            )
        return v


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
        return _NUM_DIMENSIONS * _MAX_SCORE


class ReferenceReport(BaseModel):
    """Hand-written ground truth for evaluating an investigation report."""

    root_cause: str
    key_evidence: list[str]
    expected_mitigations: list[str]
    notes: str = ""


class EvalResult(BaseModel):
    incident_id: str
    judge_output: JudgeOutput
    generated_report: InvestigationReport
