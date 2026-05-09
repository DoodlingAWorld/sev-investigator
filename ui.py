"""Streamlit UI for browsing sev-investigator traces and investigation reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st

# ── Path config ───────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent
_TRACES_DIR = _ROOT / "traces"
_REPORTS_DIR = _ROOT / "reports"

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data
def _load_trace(run_id: str) -> list[dict[str, Any]]:
    path = _TRACES_DIR / f"{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@st.cache_data
def _load_report(run_id: str) -> dict[str, Any] | None:
    path = _REPORTS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _available_runs() -> list[str]:
    trace_ids = {p.stem for p in _TRACES_DIR.glob("*.jsonl")}
    return sorted(trace_ids, reverse=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_label(event: dict[str, Any]) -> str:
    et = event["event_type"]
    payload = event.get("payload", {})
    if et == "investigation_start":
        return f"Start — {payload.get('incident_title', '')}"
    if et == "planner_call":
        action = payload.get("action", "")
        tool = payload.get("next_tool", "")
        return f"Planner → {action}" + (f" ({tool})" if tool else "")
    if et == "executor_call":
        return f"Executor → {payload.get('tool', '')}"
    if et == "tool_call":
        args = payload.get("args", {})
        arg_str = ", ".join(f"{k}={repr(v)[:30]}" for k, v in list(args.items())[:2])
        return f"Tool: {payload.get('tool', '')}({arg_str})"
    if et == "synthesizer_call":
        return f"Synthesizer ({payload.get('evidence_count', '?')} evidence items)"
    if et == "investigation_complete":
        return f"Complete — {payload.get('steps_taken', '?')} steps"
    return et


def _confidence_color(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.5:
        return "orange"
    return "red"


# ── Pages ─────────────────────────────────────────────────────────────────────

def _page_trace(run_id: str) -> None:
    events = _load_trace(run_id)

    st.subheader("Investigation steps")

    planner_events = [e for e in events if e["event_type"] == "planner_call"]
    executor_events = [e for e in events if e["event_type"] == "executor_call"]
    tool_events     = [e for e in events if e["event_type"] == "tool_call"]

    for i, ev in enumerate(events):
        et = ev["event_type"]
        payload = ev.get("payload", {})
        tokens  = ev.get("tokens", {})
        latency = ev.get("latency_ms", 0.0)

        if et == "investigation_start":
            st.info(
                f"**Incident:** {payload.get('incident_title')}  \n"
                f"**Type:** {payload.get('type')}  |  **Skill:** {payload.get('skill')}"
            )
            continue

        if et == "investigation_complete":
            exhausted = payload.get("budget_exhausted", False)
            st.success(
                f"Investigation complete — **{payload.get('steps_taken')} steps**, "
                f"**{payload.get('hypotheses_count')} hypotheses**"
                + ("  ⚠️ budget exhausted" if exhausted else "")
            )
            continue

        if et == "planner_call":
            action = payload.get("action", "")
            color = "🟢" if action == "synthesize" else "🔵"
            with st.expander(
                f"{color} Planner step {payload.get('step')} → **{action}**"
                + (f"  ·  next: `{payload.get('next_tool')}`" if payload.get("next_tool") else ""),
                expanded=False,
            ):
                st.markdown(f"**Reasoning:** {payload.get('reasoning')}")
                col1, col2, col3 = st.columns(3)
                col1.metric("Prompt tokens", tokens.get("prompt", 0))
                col2.metric("Completion tokens", tokens.get("completion", 0))
                col3.metric("Latency", f"{latency:.0f} ms")
            continue

        if et == "executor_call":
            with st.expander(
                f"⚙️ Executor → `{payload.get('tool')}`",
                expanded=False,
            ):
                st.markdown(f"**Rationale:** {payload.get('rationale')}")
                col1, col2, col3 = st.columns(3)
                col1.metric("Prompt tokens", tokens.get("prompt", 0))
                col2.metric("Completion tokens", tokens.get("completion", 0))
                col3.metric("Latency", f"{latency:.0f} ms")
            continue

        if et == "tool_call":
            result = payload.get("result", {})
            args   = payload.get("args", {})
            with st.expander(
                f"🔧 Tool: `{payload.get('tool')}` — {latency:.0f} ms",
                expanded=False,
            ):
                st.markdown("**Arguments:**")
                st.json(args)
                st.markdown("**Result:**")
                st.json(result)
            continue

        if et == "synthesizer_call":
            col1, col2, col3 = st.columns(3)
            col1.metric("Prompt tokens", tokens.get("prompt", 0))
            col2.metric("Completion tokens", tokens.get("completion", 0))
            col3.metric("Latency", f"{latency:.0f} ms")
            st.caption(f"Synthesizer received {payload.get('evidence_count')} evidence items")
            continue

    st.divider()
    st.subheader("Token usage by span")

    span_labels, prompt_vals, completion_vals, latency_vals = [], [], [], []
    for ev in events:
        if ev.get("tokens"):
            span_labels.append(ev["span_id"])
            prompt_vals.append(ev["tokens"].get("prompt", 0))
            completion_vals.append(ev["tokens"].get("completion", 0))
            latency_vals.append(ev.get("latency_ms", 0.0))

    if span_labels:
        fig = go.Figure(data=[
            go.Bar(name="Prompt",     x=span_labels, y=prompt_vals,     marker_color="#4C78A8"),
            go.Bar(name="Completion", x=span_labels, y=completion_vals, marker_color="#72B7B2"),
        ])
        fig.update_layout(
            barmode="stack",
            xaxis_title="Span",
            yaxis_title="Tokens",
            height=300,
            margin=dict(t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, width="stretch")

        total_prompt     = sum(prompt_vals)
        total_completion = sum(completion_vals)
        total_latency    = sum(latency_vals)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total prompt tokens",     total_prompt)
        c2.metric("Total completion tokens", total_completion)
        c3.metric("Total latency",           f"{total_latency:.0f} ms")


def _page_report(run_id: str) -> None:
    report = _load_report(run_id)

    if report is None:
        st.warning(
            "No report found for this run. Reports are only saved for investigations run "
            "after report persistence was added. Re-run the investigation to generate one."
        )
        return

    st.subheader("Summary")
    st.write(report["summary"])

    st.subheader("Timeline")
    for entry in report.get("timeline", []):
        st.markdown(f"- {entry}")

    st.subheader("Root cause hypotheses")
    hypotheses = sorted(report.get("hypotheses", []), key=lambda h: h["rank"])
    for h in hypotheses:
        conf = h["confidence"]
        color = _confidence_color(conf)
        with st.expander(
            f"#{h['rank']} — {h['description']}  (confidence: :{color}[**{conf:.0%}**])",
            expanded=h["rank"] == 1,
        ):
            st.markdown("**Supporting evidence:**")
            for ev in h.get("supporting_evidence", []):
                st.markdown(f"- {ev}")

    st.subheader("Mitigations")
    priority_order = {"immediate": 0, "short_term": 1, "long_term": 2}
    mitigations = sorted(
        report.get("mitigations", []),
        key=lambda m: priority_order.get(m["priority"], 99),
    )
    for m in mitigations:
        badge = {"immediate": "🔴", "short_term": "🟡", "long_term": "🟢"}.get(m["priority"], "⚪")
        with st.expander(f"{badge} [{m['priority'].replace('_', ' ').title()}] {m['action']}"):
            st.markdown(f"**Rationale:** {m['rationale']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="sev-investigator",
        page_icon="🔍",
        layout="wide",
    )
    st.title("🔍 sev-investigator")

    runs = _available_runs()
    if not runs:
        st.warning("No traces found. Run an investigation first: `sev-investigator investigate <incident.json>`")
        return

    with st.sidebar:
        st.header("Run")
        selected = st.selectbox("Select run ID", runs)
        st.caption(f"{len(runs)} run(s) available")

        events = _load_trace(selected)
        start_event = next((e for e in events if e["event_type"] == "investigation_start"), None)
        if start_event:
            p = start_event["payload"]
            st.markdown(f"**{p.get('incident_title', '')}**")
            st.markdown(f"`{p.get('type', '')}` · `{p.get('skill', '')}`")

        page = st.radio("View", ["Trace", "Report"])

    if page == "Trace":
        _page_trace(selected)
    else:
        _page_report(selected)


if __name__ == "__main__":
    main()
