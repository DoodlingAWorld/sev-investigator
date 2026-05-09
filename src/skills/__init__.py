from __future__ import annotations

from sev_investigator.skills.base import Skill

SKILL_REGISTRY: dict[str, type[Skill]] = {}


def get_skill(incident_type: str) -> Skill:
    """Return an instantiated skill for the given incident type."""
    if incident_type not in SKILL_REGISTRY:
        raise ValueError(f"No skill registered for incident type: {incident_type!r}")
    return SKILL_REGISTRY[incident_type]()
