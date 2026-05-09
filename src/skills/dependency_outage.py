from __future__ import annotations

from typing import ClassVar

from sev_investigator.prompts import DEPENDENCY_OUTAGE_SKILL_PROMPT
from sev_investigator.skills.base import Skill


class DependencyOutageSkill(Skill):
    """Investigation strategy for incidents caused by a failing upstream dependency."""

    name: ClassVar[str] = "dependency_outage"
    description: ClassVar[str] = "Investigates incidents caused by a failing upstream dependency."
    tool_whitelist: ClassVar[list[str]] = [
        "get_dependencies",
        "query_logs",
        "get_metrics",
        "get_recent_deploys",
        "get_config_diff",
    ]

    @property
    def system_prompt_fragment(self) -> str:
        return DEPENDENCY_OUTAGE_SKILL_PROMPT

    @property
    def hypothesis_categories(self) -> list[str]:
        return [
            "Upstream dependency is fully down, causing all dependent requests to fail",
            "Upstream dependency is degraded and intermittently available, causing error waves",
            "Dependency is reachable but misconfigured or connection-pool exhausted, causing partial failures",
        ]
