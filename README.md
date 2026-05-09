# sev-investigator

A multi-step LLM agent that investigates production incidents. Given a structured incident event, it runs a planner→executor loop, gathering evidence by calling tools, then synthesizes a structured root-cause analysis report.

## Why multi-step?

A single LLM call can't investigate an incident well. It doesn't know which logs to pull, which service to look at first, or when it has enough evidence to stop. A multi-step agent does:

- **Planner** decides what to investigate next, given what's already been found
- **Executor** calls the right tool with the right arguments
- **Synthesizer** writes the final report only after enough evidence is collected

This mirrors how a human on-call engineer thinks: form a hypothesis, gather evidence, revise, repeat, then conclude.

## Why skill loading by incident type?

A deploy-related incident calls for different investigation heuristics than a dependency outage. Skills let you encode that domain knowledge without polluting the core agent logic. Each skill defines a system prompt fragment, a tool whitelist, and default hypothesis categories.

## Architecture

```
                 ┌─────────────────┐
                 │  Incident Event │
                 │  (entry point)  │
                 └────────┬────────┘
                          ▼
                 ┌─────────────────┐
                 │   Coordinator   │  Loads skill-pack, manages state,
                 │                 │  emits trace events
                 └────────┬────────┘
                          ▼
            ┌─────────────┴─────────────┐
            ▼                           ▼
   ┌─────────────────┐         ┌─────────────────┐
   │     Planner     │ ◀────── │    Executor     │
   │   (LLM call)   │         │  (LLM + tools)  │
   │  Decides: what  │ ──────▶ │  Calls tools,   │
   │  to investigate │         │  gathers data   │
   │  next?          │         │                 │
   └─────────────────┘         └─────────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │   Synthesizer   │
                              │   (LLM call)    │
                              │  Produces final │
                              │  RCA report     │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │  Investigation  │
                              │  Report (JSON)  │
                              └─────────────────┘
```

The coordinator runs up to 8 planner→executor iterations. All LLM outputs are structured via Pydantic with no free-form text parsing.

## Setup

```bash
git clone https://github.com/your-username/sev-investigator
cd sev-investigator
pip install -e ".[dev]"

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

✓ Done  run_id=06d3fad5
```

**Run the eval harness:**

```bash
sev-investigator eval samples/eval_set/
```

Scores each case against a reference report using an LLM-as-judge:

```
Evaluating 3 cases...

── eval_001 (eval-001 · deploy_related)
   root_cause_accuracy=3/3  evidence_quality=3/3  hypothesis_completeness=2/3  mitigation_utility=3/3  hallucination=3/3  → 14/15

── eval_002 (eval-002 · config_change)
   root_cause_accuracy=3/3  evidence_quality=3/3  hypothesis_completeness=3/3  mitigation_utility=3/3  hallucination=3/3  → 15/15

── eval_003 (eval-003 · dependency_outage)
   root_cause_accuracy=3/3  evidence_quality=2/3  hypothesis_completeness=3/3  mitigation_utility=3/3  hallucination=3/3  → 14/15

Aggregate: 43/45 (95%)
```

## Sample incidents

Three main scenarios and three eval cases, each with deterministic fixture data so the agent's reasoning is fully traceable:

| Incident | Type | Root cause the agent finds |
|---|---|---|
| `incident_001_bad_deploy` | `deploy_related` | Deploy at 14:23 introduced a null pointer in promo code handler; errors begin at 14:25 |
| `incident_002_config_change` | `config_change` | Feature flag `use_payment_cache=false` at 10:05 dropped cache hit rate to 0%; latency spikes |
| `incident_003_dependency_outage` | `dependency_outage` | `auth-db` healthcheck down; all live auth lookups fail with ETIMEDOUT |

Mock tools read deterministic fixture data from `samples/<incident>/fixtures/`. No external API calls. The same incident always produces the same evidence, making the eval reproducible.

## Observability

The agent observes itself. Every LLM call, tool call, and state transition emits a structured event to `traces/{run_id}.jsonl`:

```json
{"timestamp": "2026-04-15T14:31:08.719037+00:00", "event_type": "planner_call",
 "span_id": "planner-0", "parent_span_id": "coordinator",
 "payload": {"step": 0, "action": "investigate", "next_tool": "get_recent_deploys",
             "reasoning": "Check whether a deploy preceded the incident."},
 "tokens": {"prompt": 628, "completion": 73}, "latency_ms": 2329.0}
```

The span hierarchy (`coordinator` → `planner-N` → `executor-N` → `tool-N` → `synthesizer`) lets you reconstruct the full investigation tree and answer questions like: how many tokens did each step cost? Which tool call took longest? A full example trace is at `samples/example_trace.jsonl`.

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
├── agent/              # coordinator, planner, executor, synthesizer
├── traces/             # Trace recorder (JSONL)
└── eval/               # LLM-as-judge runner
samples/
├── incident_00{1,2,3}*/       # Main incidents + fixtures
└── eval_set/eval_00{1,2,3}/   # Eval cases with reference reports
tests/                  # pytest; LLM is always mocked
```

## Design notes

**Structured outputs everywhere.** Every LLM call uses `client.beta.chat.completions.parse` with a Pydantic schema. The agent never parses free-form text, which eliminates an entire class of reliability bugs.

**Prompts as constants.** All prompts live in `src/prompts.py` and are imported where needed. No inline f-strings in agent code. This makes prompt iteration visible in diffs and keeps prompt content out of business logic.

**Mock tools are deterministic.** Fixture files are keyed by service name within each incident directory. Given the same incident, the agent always sees the same evidence, making the eval reproducible and the reasoning auditable.

**Skills are the domain knowledge layer.** Each skill encodes investigation heuristics for one class of incident. Adding a new incident type means adding a skill class and fixtures, not touching the agent loop.

**Provider-agnostic LLM wrapper.** `llm.py` is a thin facade over the OpenAI SDK. Set `OPENAI_MODEL` in `.env` to swap models without code changes.
