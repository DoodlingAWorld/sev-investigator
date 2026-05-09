from __future__ import annotations

import json

from sev_investigator.schemas.tools import Dependency, GetDependenciesInput, GetDependenciesResult
from sev_investigator.tools._config import get_fixtures_dir


def get_dependencies(dep_input: GetDependenciesInput) -> GetDependenciesResult:
    """Return the dependency graph for a service, loaded from fixture data."""
    fixture_path = get_fixtures_dir() / "get_dependencies.json"
    raw: dict[str, list[dict[str, object]]] = json.loads(fixture_path.read_text())

    dependencies = [Dependency.model_validate(d) for d in raw.get(dep_input.service, [])]

    return GetDependenciesResult(service = dep_input.service, dependencies = dependencies)
