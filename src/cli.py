from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from sev_investigator.agent import coordinator
from sev_investigator.schemas.incident import IncidentEvent

app = typer.Typer(help="Investigate production incidents with a multi-step LLM agent.")
_console = Console()


@app.command()
def investigate(
    incident_path: Path = typer.Argument(..., help="Path to incident JSON file"),
    output: Path = typer.Option(None, "--output", "-o", help="Write report JSON to this file"),
) -> None:
    """Run a multi-step investigation on an incident and produce a root-cause report."""
    if not incident_path.exists():
        _console.print(f"[red]Error:[/red] incident file not found: {incident_path}")
        raise typer.Exit(1)

    incident = IncidentEvent.model_validate_json(incident_path.read_text())
    fixtures_dir = incident_path.parent / incident_path.stem / "fixtures"

    if not fixtures_dir.exists():
        _console.print(f"[red]Error:[/red] fixtures directory not found: {fixtures_dir}")
        raise typer.Exit(1)

    report = coordinator.run(incident, fixtures_dir)

    report_json = report.model_dump_json(indent = 2)

    if output:
        output.write_text(report_json)
        _console.print(f"Report written to [bold]{output}[/bold]")
    else:
        _console.print(report_json)


@app.command(name="eval")
def eval_cmd(
    eval_dir: Path = typer.Argument(..., help="Directory containing eval cases"),
) -> None:
    """Score the agent against a labeled eval set using an LLM-as-judge."""
    _console.print("[dim]Eval harness not yet implemented.[/dim]")


if __name__ == "__main__":
    app()
