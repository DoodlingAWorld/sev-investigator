from __future__ import annotations

from typing import ClassVar

from sev_investigator.prompts import DEPLOY_RELATED_SKILL_PROMPT
from sev_investigator.skills.base import Skill


class DeployRelatedSkill(Skill):
    """Investigation strategy for incidents likely caused by a recent code deployment."""

    name: ClassVar[str] = "deploy_related"
    description: ClassVar[str] = "Investigates incidents likely caused by a recent code deployment."
    tool_whitelist: ClassVar[list[str]] = [
        "query_logs",
        "get_recent_deploys",
        "get_config_diff",
        "get_metrics",
        "get_dependencies",
    ]

    @property
    def system_prompt_fragment(self) -> str:
        return DEPLOY_RELATED_SKILL_PROMPT

    @property
    def hypothesis_categories(self) -> list[str]:
        return [
            "Code bug introduced by the deploy",
            "Configuration change introduced by the deploy",
            "Resource exhaustion from a new code path",
            "Dependency incompatibility introduced by the deploy",
        ]
