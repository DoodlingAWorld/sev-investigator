from __future__ import annotations

import pytest

from sev_investigator.skills import SKILL_REGISTRY, get_skill
from sev_investigator.skills.deploy_related import DeployRelatedSkill
from sev_investigator.tools import TOOL_REGISTRY


def test_get_skill_deploy_related_returns_correct_type() -> None:
    skill = get_skill("deploy_related")
    assert isinstance(skill, DeployRelatedSkill)


def test_get_skill_unknown_raises_value_error() -> None:
    with pytest.raises(ValueError, match="No skill registered"):
        get_skill("not_a_real_skill")


def test_deploy_related_name() -> None:
    skill = get_skill("deploy_related")
    assert skill.name == "deploy_related"


def test_deploy_related_tool_whitelist_all_exist_in_registry() -> None:
    skill = get_skill("deploy_related")
    for tool in skill.tool_whitelist:
        assert tool in TOOL_REGISTRY, f"{tool!r} is in tool_whitelist but not in TOOL_REGISTRY"


def test_deploy_related_has_hypothesis_categories() -> None:
    skill = get_skill("deploy_related")
    assert len(skill.hypothesis_categories) > 0


def test_deploy_related_system_prompt_not_empty() -> None:
    skill = get_skill("deploy_related")
    assert len(skill.system_prompt_fragment) > 100


def test_skill_registry_keys_match_class_names() -> None:
    for key, skill_cls in SKILL_REGISTRY.items():
        assert key == skill_cls.name, (
            f"Registry key {key!r} does not match skill class name {skill_cls.name!r}"
        )
