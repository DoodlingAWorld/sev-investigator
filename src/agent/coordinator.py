from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console

from sev_investigator.agent import MAX_REFLECTION_ROUNDS, MAX_STEPS
from sev_investigator.agent import critic, executor, planner, synthesizer
from sev_investigator.schemas.agent_state import AgentState
from sev_investigator.schemas.incident import IncidentEvent
from sev_investigator.schemas.report import InvestigationReport
from sev_investigator.skills import get_skill
from sev_investigator.tools import set_fixtures_dir
from sev_investigator.traces.recorder import Recorder

_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

_console = Console()


def run(incident: IncidentEvent, fixtures_dir: Path) -> InvestigationReport:
    """Run a full investigation: load skill, planner→executor loop, then synthesize."""
    set_fixtures_dir(fixtures_dir)
    try:
        return _run(incident)
    finally:
        set_fixtures_dir(None)


def _run(incident: IncidentEvent) -> InvestigationReport:
    skill = get_skill(incident.type)
    state = AgentState(incident = incident, skill_name = skill.name)

    _console.print(f"\n[bold]sev-investigator[/bold] — {incident.title}")
    _console.print(
        f"[dim]id:[/dim] {incident.id}  "
        f"[dim]type:[/dim] {incident.type}  "
        f"[dim]severity:[/dim] {incident.severity}\n"
    )

    with Recorder(state.run_id) as rec:
        rec.emit(
            "investigation_start",
            payload = {
                "incident_id": incident.id,
                "incident_title": incident.title,
                "type": incident.type,
                "skill": skill.name,
            },
            span_id = "coordinator",
        )

        budget_exhausted = False
        while state.step_count < MAX_STEPS:
            decision = planner.run(state, skill, rec)
            _console.print(
                f"[cyan][planner][/cyan]    → {decision.action}  "
                f"[dim]{decision.reasoning[:80]}[/dim]"
            )

            if decision.action == "synthesize":
                break

            # next_step is guaranteed non-None here by PlannerDecision's model_validator
            if decision.next_step is None:
                break

            evidence = executor.run(decision.next_step, state, rec)
            _console.print(
                f"[green][executor][/green]   → {evidence.tool}({_fmt_args(evidence.args)})"
            )

            state.evidence.append(evidence)
            state.step_count += 1
        else:
            budget_exhausted = True
            _console.print(
                f"\n[bold yellow][coordinator][/bold yellow] step budget exhausted "
                f"({MAX_STEPS} steps) — synthesizing with partial evidence."
            )

        _console.print("\n[yellow][synthesizer][/yellow] writing report...")
        report = synthesizer.run(state, rec)

        while state.reflection_rounds < MAX_REFLECTION_ROUNDS:
            critique = critic.run(state, report, rec)
            state.critiques.append(critique)
            _console.print(
                f"[magenta][critic][/magenta]      → {critique.verdict}"
                + (f"  [dim]{critique.issues[0][:80]}[/dim]" if critique.issues else "")
            )

            if critique.verdict == "accept":
                break

            state.reflection_rounds += 1

            if critique.verdict == "investigate_more" and state.step_count < MAX_STEPS:
                while state.step_count < MAX_STEPS:
                    decision = planner.run(state, skill, rec, guidance = critique.guidance)
                    _console.print(
                        f"[cyan][planner][/cyan]    → {decision.action}  "
                        f"[dim]{decision.reasoning[:80]}[/dim]"
                    )
                    if decision.action == "synthesize" or decision.next_step is None:
                        break
                    evidence = executor.run(decision.next_step, state, rec)
                    _console.print(
                        f"[green][executor][/green]   → {evidence.tool}({_fmt_args(evidence.args)})"
                    )
                    state.evidence.append(evidence)
                    state.step_count += 1
            elif critique.verdict == "investigate_more":
                _console.print(
                    "[bold yellow][coordinator][/bold yellow] investigate_more requested "
                    "but step budget exhausted — revising with existing evidence."
                )

            report = synthesizer.run(state, rec, prior_critique = critique)

        cap_hit = bool(state.critiques) and state.critiques[-1].verdict != "accept"
        rec.emit(
            "reflection_complete",
            payload = {
                "rounds_used": state.reflection_rounds,
                "final_verdict": state.critiques[-1].verdict if state.critiques else "none",
                "cap_hit": cap_hit,
            },
            span_id = "reflection",
            parent_span_id = "coordinator",
        )

        rec.emit(
            "investigation_complete",
            payload = {
                "steps_taken": state.step_count,
                "budget_exhausted": budget_exhausted,
                "hypotheses_count": len(report.hypotheses),
            },
            span_id = "coordinator_end",
            parent_span_id = "coordinator",
        )

    _persist_report(report)
    _console.print(f"\n[bold green]✓ Done[/bold green]  run_id={report.run_id}\n")
    return report


def _persist_report(report: InvestigationReport) -> None:
    _REPORTS_DIR.mkdir(exist_ok=True)
    out = _REPORTS_DIR / f"{report.run_id}.json"
    out.write_text(json.dumps(report.model_dump(mode="json"), indent=2))


def _fmt_args(args: dict[str, Any]) -> str:
    """Render the first three tool args as a compact inline string for display."""
    parts = []
    for k, v in list(args.items())[:3]:
        v_repr = repr(v)
        if len(v_repr) > 40:
            v_repr = v_repr[:37] + "..."
        parts.append(f"{k}={v_repr}")
    return ", ".join(parts)
