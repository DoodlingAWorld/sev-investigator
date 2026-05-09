from __future__ import annotations

from datetime import datetime

import pytest

from sev_investigator.schemas.incident import IncidentEvent


@pytest.fixture
def sample_incident() -> IncidentEvent:
    return IncidentEvent(
        id="inc-001",
        title="order-service 5xx spike",
        type="deploy_related",
        service="order-service",
        started_at=datetime(2026, 4, 15, 14, 25, 0),
        description=(
            "Error rate on order-service jumped to 12% at 14:25 UTC. "
            "Orders are failing at checkout."
        ),
        severity="sev2",
    )
