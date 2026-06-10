from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _run_case(case_dir: Path, quiet: bool) -> EvalResult | None:
    incident_path  = case_dir / "incident.json"
    reference_path = case_dir / "reference_report.json"
    fixtures_dir   = case_dir / "fixtures"

    missing = [p for p in (incident_path, reference_path, fixtures_dir) if not p.exists()]
    if missing:
        _console.print(
            f"[red]  Skipping {case_dir.name}:[/red] "
            f"missing {[p.name for p in missing]}"
        )
        return None

    try:
        incident  = IncidentEvent.model_validate_json(incident_path.read_text())
        reference = ReferenceReport.model_validate_json(reference_path.read_text())
    except Exception as exc:
        _console.print(f"[red]  Skipping {case_dir.name}:[/red] parse error — {exc}")
        return None

    if not quiet:
        _console.print(f"[dim]── {case_dir.name}[/dim] ({incident.id} · {incident.type})\n")

    fixture_data = _load_fixtures(fixtures_dir)
    try:
        report = coordinator.run(incident, fixtures_dir, quiet=quiet)
    except Exception as exc:
        _console.print(f"[red]  {case_dir.name} crashed:[/red] {exc}")
        return None
    judge_output = judge.score(report, reference, fixture_data=fixture_data)

    result = EvalResult(
        incident_id=incident.id,
        judge_output=judge_output,
        generated_report=report,
    )

    scores_by_dim = {s.dimension: s.score for s in judge_output.scores}
    score_str = "  ".join(f"{d}={scores_by_dim.get(d, '?')}/3" for d in RUBRIC_DIMENSIONS)
    _console.print(
        f"[dim]{incident.id}[/dim]  {score_str}  "
        f"→ [bold]{judge_output.total}/{judge_output.max_total}[/bold]"
    )
    return result


def run(eval_dir: Path, quiet: bool = False) -> list[EvalResult]:
    """Run the agent on each eval case and score with the LLM judge.

    Cases run in parallel. Pass quiet=True to suppress per-step agent output
    and only show per-case scores and the final summary table.
    """
    cases = sorted(p for p in eval_dir.iterdir() if p.is_dir())

    if not cases:
        _console.print(f"[red]No eval cases found in {eval_dir}[/red]")
        return []

    _console.print(f"\nEvaluating [bold]{len(cases)}[/bold] cases...\n")

    results: list[EvalResult] = []
    with ThreadPoolExecutor(max_workers=len(cases)) as pool:
        futures = {pool.submit(_run_case, case_dir, quiet): case_dir for case_dir in cases}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)

    results.sort(key=lambda r: r.incident_id)

    if results:
        _console.print()
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
