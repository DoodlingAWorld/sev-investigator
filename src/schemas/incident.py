from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class IncidentEvent(BaseModel):
    """Structured trigger event that kicks off an investigation."""

    id: str
    title: str
    type: Literal["deploy_related", "config_change", "dependency_outage"]
    service: str
    started_at: datetime
    description: str
    severity: Literal["sev1", "sev2", "sev3"]
