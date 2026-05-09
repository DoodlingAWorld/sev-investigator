from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sev_investigator.schemas.incident import IncidentEvent
from sev_investigator.schemas.tools import ToolResult


class ToolCallPlan(BaseModel):
    """What the planner wants the executor to investigate next."""

    model_config = ConfigDict(extra = "forbid")

    tool: str
    rationale: str


class PlannerDecision(BaseModel):
    """Structured output of a single planner LLM call."""

    model_config = ConfigDict(extra = "forbid")

    action: Literal["investigate", "synthesize"]
    next_step: ToolCallPlan | None = None
    reasoning: str

    @model_validator(mode="after")
    def next_step_required_when_investigating(self) -> "PlannerDecision":
        if self.action == "investigate" and self.next_step is None:
            raise ValueError("next_step is required when action is 'investigate'")
        return self


class Evidence(BaseModel):
    """A single tool call and its result collected during an investigation."""

    tool: str
    args: dict[str, Any]
    result: ToolResult
    collected_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AgentState(BaseModel):
    """Working memory for an in-progress investigation."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    incident: IncidentEvent
    skill_name: str
    evidence: list[Evidence] = Field(default_factory=list)
    step_count: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
