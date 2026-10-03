# OpenCompute

**An experimental, open-source runtime for composing AI capabilities into self-hosted workflows.**

OpenCompute is an early-stage, student-built project. It tries to answer one question: instead of picking one big AI agent, what if you could wire together small, replaceable capabilities (search, files, ...) behind one runtime that plans, executes, verifies, and recovers — and only spends the compute it actually needs?

This is the first milestone: a small, understandable core that already runs a real task end to end.

> This is not a production platform, and it does not try to compete with
> products like Perplexity Computer. It is a learning project: a serious working
> prototype with simple, readable code.

## What it does today

Milestone 2 runs this loop:

```
goal  ->  planner (1 LLM call -> validated JSON plan)
      ->  capabilities (research, filesystem, http)
      ->  shared context (later steps can reference earlier output)
      ->  deterministic markdown verifier
      ->  on failure, one escalation to a stronger model, then verify again
      ->  report + SQLite event log + model cost/token accounting
```

It has three capabilities:

- `research` — search the web, fetch pages, synthesize a sourced summary.
- `filesystem` — read/write files, confined to the workspace.
- `http` — a plain HTTP GET/POST (deterministic; no model involved).

## Quick start

```bash
pip install -e ".[dev]"

export OPENAI_API_KEY=sk-...            # any OpenAI-compatible provider
export OPENAI_BASE_URL=...              # optional (OpenRouter, Ollama, ...)
export OPENCOMPUTE_MODEL=gpt-4o-mini            # default model
export OPENCOMPUTE_STRONG_MODEL=gpt-4o          # escalation fallback

opencompute run "Research three weather API providers and create a markdown comparison report."
```

That prints a timeline, writes `workspace/output/weather-api-comparison.md`, and
records every event in `workspace/state/events.db` (SQLite).

```
Planning...
✓ Plan created (3 steps)
Researching: ...
  ✓ collected 4 source(s)
...
Verifying...
✓ Verification passed

Cost: $0.0000 (estimated; 3 model calls)
```

## Configuration

Everything lives in environment variables, not a config file:

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | provider key (required) | — |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint | OpenRouter/Ollama-friendly, optional |
| `OPENCOMPUTE_MODEL` | default model | `gpt-4o-mini` |
| `OPENCOMPUTE_STRONG_MODEL` | escalation fallback | `gpt-4o` |
| `OPENCOMPUTE_WORKSPACE` | workspace directory | `./workspace` |

## Cost honesty

Every model call is recorded with token counts (input/output/total), a
confidence tag, latency, and the step it belongs to. Confidence is one of:

- `exact` — a known per-token price and real token counts.
- `estimated` — token counts present, but the price is an approximation.
- `unknown` — no usable price; not added to the dollar total.

The lookup table (`opencompute/core/models.py`) is approximate USD per million
tokens. Unknown-cost calls are counted but never mixed into a dollar figure.

## Benchmark

```bash
opencompute benchmark                # three open-source projects
opencompute benchmark --subject "three databases"
```

This runs a general-purpose task (compare three open-source projects) through
the full pipeline and reports: task success, model calls, input/output/total
tokens, model cost, execution time, verification result, retries, and
escalations. It is the baseline for testing whether OpenCompute really does the
same useful work with less unnecessary computation.

## Project layout

```
opencompute/
  core/            task, events, database, models, planner, runtime
  capabilities/    base, filesystem, research, http, web
  verification/    markdown (deterministic verifier)
  benchmark.py     the general-purpose benchmark
  cli.py           the command line
tests/             offline tests (a fake model keeps them fast)
```

## Running tests

```bash
PYTHONPATH=. python -m pytest -q
```

The suite uses a fake model and fake search, so it runs offline in well under a
second.

## Known limitations (Milestone 2)

- One escalation is supported, and it re-runs the whole task with the stronger
  model.
- The shared context is short-term only (in-memory per run); there is no
  persistence of derived state between separate runs yet.
- Verification is a single deterministic Markdown checker; there is no quality
  estimator or task-type-specific verifier yet.
- No browser, coding, or computer-use capabilities; no plugin system; no Web UI.

## Status

Milestone 2 of 7. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design and
roadmap, and [`SECURITY.md`](SECURITY.md) for the threat model.
