# sev-investigator

<img width="1687" height="918" alt="Screenshot 2026-05-09 195432" src="https://github.com/user-attachments/assets/5b0daa93-36fa-492c-84da-f5e288629737" />
<img width="1687" height="872" alt="Screenshot 2026-05-09 195441" src="https://github.com/user-attachments/assets/18c87f1b-fcaa-4397-bbf2-f66dd368bcef" />
<img width="1310" height="746" alt="Screenshot 2026-05-09 195456" src="https://github.com/user-attachments/assets/3e882526-887f-492e-9240-e3a7ea310e83" />


A multi-step LLM agent that investigates production incidents. Given a structured incident event, it runs a planner→executor loop, gathering evidence by calling tools, then synthesizes a structured root-cause analysis report — and then critiques its own output.

## Why multi-step?

A single LLM call can't investigate an incident well. It doesn't know which logs to pull, which service to look at first, or when it has enough evidence to stop. A multi-step agent does:

- **Planner** decides what to investigate next, given what's already been found
- **Executor** calls the right tool with the right arguments
- **Synthesizer** writes the final report only after enough evidence is collected

This mirrors how a human on-call engineer thinks: form a hypothesis, gather evidence, revise, repeat, then conclude.

## Why self-critique?

A single planner→executor pass commits to the first plausible explanation it finds. In adversarial scenarios — a deploy that looks causal but isn't, a dependency that looks unhealthy but is actually being overwhelmed by retries — the agent reaches a confident but wrong conclusion.

The **critic** does a second-pass evaluation of the synthesized report against the collected evidence. It can:

- **Accept** the report when evidence supports the conclusion
- **Revise** when the report overstates, hallucinates, or misses a mitigation derivable from existing evidence
- **Investigate more** when the fundamental hypothesis may be wrong and a specific unchecked tool call could confirm or refute it

The `investigate_more` path is the key mechanism: the critic sends the agent back into the planner→executor loop with specific guidance ("the config_diff window was too narrow — check 12 hours back"), the agent gathers new evidence, and the synthesizer re-drafts the report. This is the [Reflexion](https://arxiv.org/abs/2303.11366) / Self-Refine pattern applied to incident investigation.

In practice, the critic catches patterns like:
- Error messages containing explicit configuration values (`pool_size=5`) combined with an empty config_diff query — signal that the change happened hours before, not at deploy time
- A `degraded` dependency status combined with retry storms in logs — signal that the dependency is healthy but overwhelmed by a misconfigured caller timeout, not actually failing

## Why skill loading by incident type?

A deploy-related incident calls for different investigation heuristics than a dependency outage. Skills let you encode that domain knowledge without polluting the core agent logic. Each skill defines a system prompt fragment and a tool whitelist.

## Architecture

```
                 ┌─────────────────┐
                 │  Incident Event │
                 └────────┬────────┘
                           ▼
                 ┌─────────────────┐
                 │   Coordinator   │  Loads skill, initializes state,
                 │                 │  emits trace events
                 └────────┬────────┘
                           ▼
         ┌─────────────────────────────────┐
         │  Planner ↔ Executor loop        │
         │  (up to 8 steps per round)      │
         │                                 │
         │  Planner: what to investigate?  │
         │  Executor: calls tool, returns  │
         │  EvidenceItem                   │
         └────────────────┬────────────────┘
                           ▼
                 ┌─────────────────┐
                 │   Synthesizer   │
                 └────────┬────────┘
                           ▼
                 ┌─────────────────┐   investigate_more   ┌──────────────────┐
                 │     Critic      │─────────────────────▶│ Re-investigation  │
                 │  (up to 2       │                       │ Planner re-enters │
                 │   rounds)       │◀──────────────────────│ with guidance;   │
                 └────────┬────────┘   new evidence        │ Synthesizer re-  │
                          │                                │ drafts report    │
                     accept/revise                         └──────────────────┘
                           ▼
                 ┌─────────────────┐
                 │  Investigation  │
                 │  Report (JSON)  │
                 └─────────────────┘
```

All LLM outputs are structured via Pydantic — no free-form text parsing anywhere.

## Setup

```bash
git clone https://github.com/DoodlingAWorld/sev-investigator
cd sev-investigator
pip install -e ".[dev]"       # core + tests
pip install -e ".[dev,ui]"    # also includes Streamlit UI

cp .env.example .env
# Add your OPENAI_API_KEY to .env
```

## Usage

**Run an investigation:**

```bash
sev-investigator investigate samples/incident_001_bad_deploy.json
```

The agent loop prints live as it works:

```
sev-investigator — order-service 5xx spike
id: inc-001  type: deploy_related  severity: sev2

[planner]    → investigate  Checking for recent deploys near the incident start time.
[executor]   → get_recent_deploys(service='order-service', since='2026-04-15T00:00:00Z', ...)
[planner]    → investigate  Deploy at 14:23 found. Checking logs for errors after deploy time.
[executor]   → query_logs(service='order-service', start='2026-04-15T14:23:00Z', level='ERROR')
[planner]    → synthesize  NullPointerException logs correlate with deploy. Sufficient evidence.

[synthesizer] writing report...
      → accept

✓ Done  run_id=06d3fad5
```

When the critic fires `investigate_more`, the loop continues:

```
[synthesizer] writing report...
      → investigate_more  Error messages show pool_size=5 but config_diff only covered 5 minutes.
[planner]    → investigate  Checking config diff over a 24-hour window to find earlier changes.
[executor]   → get_config_diff(service='payments-service', since='2026-06-09T16:00:00Z', ...)
[planner]    → synthesize  Found db_connection_pool_size reduced 100→5 at 12:00. Sufficient.

[synthesizer] writing report...
      → accept
```

**Run the eval harness:**

```bash
sev-investigator eval samples/eval_set/
```

**Browse traces and reports in the UI:**

```bash
streamlit run ui.py
```

Opens at `http://localhost:8501`. Select any past run from the sidebar to see:

- **Trace view**: each planner/executor/tool step as an expandable card with reasoning, token counts, and latency, plus a token usage chart across all spans
- **Report view**: synthesized summary, timeline, ranked hypotheses, and mitigations sorted by priority

## Sample incidents

Three main investigation scenarios plus six eval cases — three straightforward and three adversarial:

| Incident | Type | What the agent finds |
|---|---|---|
| `incident_001_bad_deploy` | `deploy_related` | Deploy introduced a null pointer in promo code handler; errors begin at 14:25 |
| `incident_002_config_change` | `config_change` | Feature flag `use_payment_cache=false` dropped cache hit rate to 0%; latency spikes |
| `incident_003_dependency_outage` | `dependency_outage` | `auth-db` healthcheck down; all live auth lookups fail with ETIMEDOUT |

**Adversarial eval cases** (designed so the obvious first hypothesis is wrong):

| Eval case | Type | Trap | Correct answer |
|---|---|---|---|
| `eval_004` | `deploy_related` | SDK deploy at 15:55 looks causal; errors start at 16:00 | `db_connection_pool_size` reduced 100→5 at 12:00 — pool finally exhausts at peak load |
| `eval_005` | `dependency_outage` | auth-service shows `degraded`; logs show 503s | `auth_timeout_ms` reduced 5000→50ms; auth-service latency is ~280ms, so every request times out; 5-retry policy produces 10× request volume |
| `eval_006` | `config_change` | `max_upload_size_mb` increased 50→500 precedes OOM crashes | Config change is correct and needed; `FileProcessor` loads entire files into memory instead of streaming — fix the code, not the config |

## Eval results

The harness scores each case against a reference report using an LLM-as-judge on five dimensions (0–3 each). Results with `MAX_REFLECTION_ROUNDS=2`:

```
── eval_001 (eval-001 · deploy_related)
   root_cause_accuracy=3  evidence_quality=3  hypothesis_completeness=3  mitigation_utility=3  hallucination=3  → 15/15

── eval_002 (eval-002 · config_change)
   root_cause_accuracy=3  evidence_quality=3  hypothesis_completeness=3  mitigation_utility=2  hallucination=3  → 14/15

── eval_003 (eval-003 · dependency_outage)
   root_cause_accuracy=3  evidence_quality=3  hypothesis_completeness=3  mitigation_utility=2  hallucination=3  → 14/15

── eval_004 (eval-004 · deploy_related)   ← adversarial
   root_cause_accuracy=3  evidence_quality=2  hypothesis_completeness=2  mitigation_utility=2  hallucination=2  → 11/15

── eval_005 (eval-005 · dependency_outage)  ← adversarial
   root_cause_accuracy=2  evidence_quality=2  hypothesis_completeness=2  mitigation_utility=2  hallucination=2  → 10/15

── eval_006 (eval-006 · config_change)   ← adversarial
   root_cause_accuracy=1  evidence_quality=2  hypothesis_completeness=1  mitigation_utility=0  hallucination=3  → 7/15

Aggregate: 71/90 (78%)
```

**Reflection lift on adversarial cases** (rounds=0 → rounds=2):

| Case | Without reflection | With reflection | Δ |
|---|---|---|---|
| eval_004 (deploy red herring) | 6/15 | 11/15 | +5 |
| eval_005 (retry storm) | 2/15 | 10/15 | +8 |
| eval_006 (latent bug) | 5/15 | 7/15 | +2 |
| **All 6 cases** | **56/90 (62%)** | **71/90 (78%)** | **+15** |

LLM output is non-deterministic so individual runs vary; the improvement direction on adversarial cases is consistent across runs.

## Observability

The agent observes itself. Every LLM call, tool call, and state transition emits a structured event to `traces/{run_id}.jsonl`:

```json
{"timestamp": "2026-05-09T23:12:07.036310+00:00", "event_type": "planner_call",
 "span_id": "planner-0", "parent_span_id": "coordinator",
 "payload": {"step": 0, "action": "investigate", "next_tool": "get_recent_deploys",
             "reasoning": "The incident description indicates that a deploy landed shortly before the error spike began, so checking the recent deploys will provide foundational context for the investigation."},
 "tokens": {"prompt": 633, "completion": 72}, "latency_ms": 1437.0}
```

The span hierarchy (`coordinator` → `planner-N` → `executor-N` → `tool-N` → `synthesizer` → `critic` → `synthesizer-rev-1`) lets you reconstruct the full investigation tree including any reflection rounds.

## Why LLM-as-judge for eval?

Reference reports capture what a correct investigation should conclude, but comparing structured JSON mechanically misses semantic equivalence. An LLM judge scores on a rubric instead:

- **Root cause accuracy**: did the agent identify the correct cause?
- **Evidence quality**: did it collect and cite the right evidence?
- **Hypothesis completeness**: did it consider plausible alternatives?
- **Mitigation utility**: are the suggested actions actionable?
- **Hallucination**: did the report invent facts not in the evidence?

Each dimension is scored 0–3. The judge receives the raw tool outputs alongside the reference so hallucination scoring is grounded in what the agent actually saw, not just what's plausible.

## Project structure

```
src/
├── cli.py              # Typer entry: investigate, eval
├── llm.py              # Thin OpenAI wrapper with token/latency metadata
├── prompts.py          # All LLM prompt constants (never inline)
├── schemas/            # Pydantic models for every data boundary
├── tools/              # Mock tools, read from fixture files
├── skills/             # Per-incident-type investigation strategies
├── agent/              # coordinator, planner, executor, synthesizer, critic
├── traces/             # Trace recorder (JSONL)
└── eval/               # LLM-as-judge runner
ui.py                   # Streamlit UI for browsing traces and reports
samples/
├── incident_00{1,2,3}*/          # Main incidents + fixtures
└── eval_set/eval_00{1,2,3,4,5,6}/ # 3 standard + 3 adversarial eval cases
reports/                # Generated reports (gitignored, paired with traces/)
tests/                  # pytest; LLM is always mocked
```

## Design notes

**Structured outputs everywhere.** Every LLM call uses `client.beta.chat.completions.parse` with a Pydantic schema. The agent never parses free-form text, which eliminates an entire class of reliability bugs.

**Prompts as constants.** All prompts live in `src/prompts.py` and are imported where needed. No inline f-strings in agent code. This makes prompt iteration visible in diffs and keeps prompt content out of business logic.

**Mock tools are deterministic.** Fixture files are keyed by service name within each incident directory. Given the same incident, the agent always sees the same evidence, making the eval reproducible and the reasoning auditable.

**Skills are the domain knowledge layer.** Each skill encodes investigation heuristics for one class of incident. Adding a new incident type means adding a skill class and fixtures, not touching the agent loop.

**The critic uses pattern matching, not general reasoning.** The critic prompt encodes specific evidence patterns that require re-investigation (e.g., configuration values in error messages combined with an empty config_diff result). This is more reliable than asking the critic to reason generally about report quality — general reasoning tends to fire too conservatively.

**Provider-agnostic LLM wrapper.** `llm.py` is a thin facade over the OpenAI SDK. Set `OPENAI_MODEL` in `.env` to swap models without code changes.
