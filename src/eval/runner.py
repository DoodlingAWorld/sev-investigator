from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from sev_investigator.agent import coordinator
from sev_investigator.eval import judge
from sev_investigator.schemas.eval import EvalResult, ReferenceReport, RUBRIC_DIMENSIONS
from sev_investigator.schemas.incident import IncidentEvent

_console = Console()


def _load_fixtures(fixtures_dir: Path) -> dict[str, Any]:
    """Load all fixture JSON files in a directory into a single dict keyed by tool name."""
    return {
        f.stem: json.loads(f.read_text())
        for f in sorted(fixtures_dir.glob("*.json"))
    }


def run(eval_dir: Path) -> list[EvalResult]:
    """Run the agent on each eval case and score with the LLM judge."""
    cases = sorted(p for p in eval_dir.iterdir() if p.is_dir())

    if not cases:
        _console.print(f"[red]No eval cases found in {eval_dir}[/red]")
        return []

    _console.print(f"\nEvaluating [bold]{len(cases)}[/bold] cases...\n")

    results: list[EvalResult] = []

    for case_dir in cases:
        incident_path  = case_dir / "incident.json"
        reference_path = case_dir / "reference_report.json"
        fixtures_dir   = case_dir / "fixtures"

        missing = [p for p in (incident_path, reference_path, fixtures_dir) if not p.exists()]
        if missing:
            _console.print(
                f"[red]  Skipping {case_dir.name}:[/red] "
                f"missing {[p.name for p in missing]}"
            )
            continue

        try:
            incident  = IncidentEvent.model_validate_json(incident_path.read_text())
            reference = ReferenceReport.model_validate_json(reference_path.read_text())
        except Exception as exc:
            _console.print(f"[red]  Skipping {case_dir.name}:[/red] parse error — {exc}")
            continue

        _console.print(f"[dim]── {case_dir.name}[/dim] ({incident.id} · {incident.type})")

        fixture_data = _load_fixtures(fixtures_dir)
        report = coordinator.run(incident, fixtures_dir)
        judge_output = judge.score(report, reference, fixture_data = fixture_data)

        result = EvalResult(
            incident_id = incident.id,
            judge_output = judge_output,
            generated_report = report,
        )
        results.append(result)

        scores_by_dim = {s.dimension: s.score for s in judge_output.scores}
        score_str = "  ".join(
            f"{d}={scores_by_dim.get(d, '?')}/3" for d in RUBRIC_DIMENSIONS
        )
        _console.print(f"   {score_str}  → [bold]{judge_output.total}/{judge_output.max_total}[/bold]\n")

    if results:
        _print_summary(results)

    return results


def _print_summary(results: list[EvalResult]) -> None:
    table = Table(title = "Eval Summary", show_lines = True)
    table.add_column("Incident")
    for dim in RUBRIC_DIMENSIONS:
        table.add_column(dim.replace("_", " "), justify = "center")
    table.add_column("Total", justify = "right")

    for r in results:
        scores_by_dim = {s.dimension: str(s.score) for s in r.judge_output.scores}
        row = [r.incident_id]
        row += [scores_by_dim.get(d, "-") for d in RUBRIC_DIMENSIONS]
        row += [f"{r.judge_output.total}/{r.judge_output.max_total}"]
        table.add_row(*row)

    _console.print(table)

    total     = sum(r.judge_output.total for r in results)
    max_total = sum(r.judge_output.max_total for r in results)
    pct       = int(100 * total / max_total) if max_total else 0
    _console.print(f"\nAggregate: [bold]{total}/{max_total}[/bold] ({pct}%)\n")
