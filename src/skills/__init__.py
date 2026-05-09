from __future__ import annotations

from sev_investigator.skills.base import Skill
from sev_investigator.skills.deploy_related import DeployRelatedSkill
from sev_investigator.tools import TOOL_REGISTRY

SKILL_REGISTRY: dict[str, type[Skill]] = {
    DeployRelatedSkill.name: DeployRelatedSkill,
}

# Validate that every skill's tool_whitelist only references tools that exist.
for _skill_cls in SKILL_REGISTRY.values():
    _unknown = set(_skill_cls.tool_whitelist) - TOOL_REGISTRY.keys()
    if _unknown:
        raise RuntimeError(
            f"Skill {_skill_cls.name!r} tool_whitelist references unknown tools: {_unknown}"
        )


def get_skill(incident_type: str) -> Skill:
    """Return an instantiated skill for the given incident type."""
    if incident_type not in SKILL_REGISTRY:
        raise ValueError(f"No skill registered for incident type: {incident_type!r}")
    return SKILL_REGISTRY[incident_type]()
