from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RootCauseHypothesis(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str]
    rank: int = Field(ge=1, description="1 = most likely")


class Mitigation(BaseModel):
    model_config = ConfigDict(extra = "forbid")

    action: str
    priority: Literal["immediate", "short_term", "long_term"]
    rationale: str


class SynthesizerOutput(BaseModel):
    """The LLM-produced content of a report. System fields (run_id, incident_id) are applied after."""

    model_config = ConfigDict(extra = "forbid")

    timeline: list[str]
    hypotheses: list[RootCauseHypothesis]
    mitigations: list[Mitigation]
    summary: str


class InvestigationReport(BaseModel):
    """Final structured output of a completed investigation."""

    run_id: str
    incident_id: str
    timeline: list[str]
    hypotheses: list[RootCauseHypothesis]
    mitigations: list[Mitigation]
    summary: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
