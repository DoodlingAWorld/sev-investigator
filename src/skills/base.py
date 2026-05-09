from __future__ import annotations

from abc import ABC, abstractmethod


class Skill(ABC):
    """Base class for incident-type-specific investigation strategies."""

    name: str
    description: str
    tool_whitelist: list[str]

    @property
    @abstractmethod
    def system_prompt_fragment(self) -> str:
        """System prompt fragment injected into planner and executor calls."""
        ...

    @property
    @abstractmethod
    def hypothesis_categories(self) -> list[str]:
        """Default hypothesis categories to consider for this incident type."""
        ...
