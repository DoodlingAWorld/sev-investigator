# sev-investigator

A multi-step LLM agent that investigates production incidents. Given a structured incident event, it runs a planner→executor loop, gathering evidence by calling tools, then synthesizes a structured root-cause analysis report.

## Why multi-step?

A single LLM call can't investigate an incident well. It doesn't know which logs to pull, which service to look at first, or when it has enough evidence to stop. A multi-step agent does:

- **Planner** decides what to investigate next, given what's already been found
- **Executor** calls the right tool with the right arguments
- **Synthesizer** writes the final report only after enough evidence is collected

This mirrors how a human on-call engineer thinks: form a hypothesis, gather evidence, revise, repeat, then conclude.

Also reduces context load on a single LLM.

## Why skill loading by incident type?

A deploy-related incident calls for different investigation heuristics than a dependency outage. 
Skills let you encode that domain knowledge. Each skill defines a system prompt fragment, a tool whitelist, and default hypothesis categories without polluting the core agent logic.

## Architecture - visualized with OpenAI

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
   │     Planner     │ <────── │    Executor     │
   │   (LLM call)    │         │  (LLM + tools)  │
   │  Decides: what  │ ──────> │  Calls tools,   │
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

The coordinator runs up to 8 planner→executor iterations. All LLM outputs are structured via Pydantic so no free-form text parsing.

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

The agent loop prints live to the terminal as it works:

```
[sev-investigator] Incident: order-service 5xx spike — type: deploy_related
[planner]    → investigate: check recent deploys for order-service
[executor]   → get_recent_deploys(service="order-service", since="2026-04-15T14:00")
[executor]   ← deploy at 14:23 — commit abc1234, author: eng-bot, 12 files changed
[planner]    → investigate: check logs around deploy time
[executor]   → query_logs(service="order-service", start="2026-04-15T14:20", end="2026-04-15T14:35")
[executor]   ← NullPointerException in OrderProcessor.handle() starting at 14:25
[planner]    → synthesize
[synthesizer] → writing report...

Report written to: traces/run_abc123/report.json
Trace written to:  traces/run_abc123/trace.jsonl
```

**Run the eval harness:**

```bash
sev-investigator eval samples/eval_set/
```

Scores each incident against a reference report using an LLM-as-judge:

```
Evaluating 5 incidents...
  eval_001: root_cause=3/3  evidence=3/3  hypotheses=2/3  mitigations=3/3  hallucination=3/3 → 14/15
  eval_002: root_cause=3/3  evidence=2/3  hypotheses=3/3  mitigations=2/3  hallucination=3/3 → 13/15
  ...
Aggregate: 91% (68/75)
```

## Sample incidents

Three scenarios with fixture data that makes agent reasoning traceable:

| Incident | Type | What the agent finds |
|---|---|---|
| `incident_001_bad_deploy` | `deploy_related` | Deploy at 14:23, null pointer in new code starting at 14:25 |
| `incident_002_config_change` | `config_change` | Feature flag change dropped cache hit rate, causing latency spike |
| `incident_003_dependency_outage` | `dependency_outage` | Upstream `auth-db` healthcheck failing, cascading to auth-gateway |

Mock tools read deterministic fixture data from `samples/<incident>/fixtures/` — no external API calls.

## Observability

The agent observes itself. Every LLM call, tool call, and state transition emits a structured event to `traces/{run_id}.jsonl`:

```json
{"timestamp": "2026-04-15T14:31:02Z", "event_type": "llm_call", "span_id": "planner-3",
 "parent_span_id": "coordinator", "payload": {"action": "investigate", "reasoning": "..."},
 "tokens": {"prompt": 812, "completion": 64}, "latency_ms": 340}
```

This makes post-hoc debugging straightforward and demonstrates the eat-your-own-dogfood principle: a tool about observability should itself be observable.

## Why LLM-as-judge for eval?

Reference reports capture what a correct investigation should conclude, but comparing free-form JSON mechanically misses semantic equivalence. An LLM judge scores on a rubric instead:

- **Root cause accuracy** — did the agent identify the correct cause?
- **Evidence quality** — did it collect and cite the right evidence?
- **Hypothesis completeness** — did it consider plausible alternatives?
- **Mitigation utility** — are the suggested actions actionable?
- **Hallucination** — did the report invent facts not in the evidence?

Each dimension is scored 0–3. The rubric is in `docs/eval_rubric.md`.

## Project structure

```
src/sev_investigator/
├── cli.py              # Typer entry: investigate, eval
├── llm.py              # Thin OpenAI wrapper
├── schemas/            # Pydantic models for every boundary
├── tools/              # Mock tools, read from fixture files
├── skills/             # Per-incident-type investigation strategies
├── agent/              # coordinator, planner, executor, synthesizer
├── traces/             # Trace recorder (JSONL)
└── eval/               # Runner + LLM-as-judge
samples/                # Incidents + fixtures + eval set
docs/                   # Architecture notes, all prompts, eval rubric
tests/                  # pytest; LLM is mocked in all tests
```

## Design notes

**Structured outputs everywhere.** Every LLM call uses `client.beta.chat.completions.parse` with a Pydantic schema. The agent never parses free-form text — this eliminates an entire class of reliability bugs.

**Prompts as constants.** All prompts live in `docs/prompts.md` and are imported as Python constants. No inline f-strings. This makes prompt iteration visible in diffs.

**Mock tools are deterministic.** Fixture files are keyed by service + time range. Given the same incident, the agent always sees the same evidence — making the eval reproducible and the reasoning auditable.

**Provider-agnostic LLM wrapper.** `llm.py` is a thin facade. Swapping from `gpt-4o-mini` to any other model requires changing one import.
