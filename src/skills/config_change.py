from __future__ import annotations

from typing import ClassVar

from sev_investigator.prompts import CONFIG_CHANGE_SKILL_PROMPT
from sev_investigator.skills.base import Skill


class ConfigChangeSkill(Skill):
    """Investigation strategy for incidents likely caused by a configuration change."""

    name: ClassVar[str] = "config_change"
    description: ClassVar[str] = "Investigates incidents likely caused by a configuration change."
    tool_whitelist: ClassVar[list[str]] = [
        "get_config_diff",
        "get_metrics",
        "query_logs",
        "get_recent_deploys",
        "get_dependencies",
    ]

    @property
    def system_prompt_fragment(self) -> str:
        return CONFIG_CHANGE_SKILL_PROMPT

    @property
    def hypothesis_categories(self) -> list[str]:
        return [
            "Configuration change caused performance degradation",
            "Configuration change disabled a critical feature",
            "Configuration change introduced incorrect behavior",
        ]
