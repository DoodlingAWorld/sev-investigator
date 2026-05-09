from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Investigate production incidents with a multi-step LLM agent.")
console = Console()


@app.command()
def investigate(
    incident_path: Path = typer.Argument(..., help="Path to incident JSON file"),
) -> None:
    """Run a multi-step investigation on an incident and produce a root-cause report."""
    ...


@app.command(name="eval")
def eval_cmd(
    eval_dir: Path = typer.Argument(..., help="Directory containing eval cases"),
) -> None:
    """Score the agent against a labeled eval set using an LLM-as-judge."""
    ...


if __name__ == "__main__":
    app()
