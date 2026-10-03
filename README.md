# OpenCompute

**An experimental, open-source runtime for composing AI capabilities into self-hosted workflows.**

OpenCompute is an early-stage, student-built project. It tries to answer one question: instead of picking one big AI agent, what if you could wire together small, replaceable capabilities (search, files, ...) behind one runtime that plans, executes, verifies, and recovers — and only spends the compute it actually needs?

This is the first milestone: a small, understandable core that already runs a real task end to end.

> This is not a production platform, and it does not try to compete with
> products like Perplexity Computer. It is a learning project: a serious working
> prototype with simple, readable code.

## What it does today

Milestone 1 runs this loop:

```
goal  ->  planner (1 LLM call -> validated JSON plan)
      ->  capabilities (research, filesystem)
      ->  deterministic markdown verifier
      ->  on failure, one escalation to a stronger model, then verify again
      ->  report + SQLite event log
```

It has exactly two capabilities:

- `research` — search the web, fetch pages, synthesize a sourced summary.
- `filesystem` — read/write files, confined to the workspace.

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

Model calls are recorded with token counts (when the provider returns them) and a
confidence tag:

- `exact` — real token counts and a known per-token price.
- `estimated` — token counts present, price is an approximation.
- `unknown` — provider price not in the lookup table.

The lookup table (`opencompute/core/models.py`) is approximate USD per million
tokens. It is deliberately marked "estimated" and is easy to extend.

## Project layout

```
opencompute/
  core/            task, events, database, models, planner, runtime
  capabilities/    base, filesystem, research, web
  verification/    markdown (deterministic verifier)
  cli.py           the command line
tests/             offline tests (a fake model keeps them fast)
```

## Running tests

```bash
PYTHONPATH=. python -m pytest -q
```

The suite uses a fake model and fake search, so it runs offline in well under a
second.

## Known limitations (Milestone 1)

- Research steps are independent: a later research step does not yet receive an
  earlier step's findings. (Inter-step data flow is a Milestone 2 goal.)
- Exactly one escalation is supported, and it re-runs the whole task with the
  stronger model.
- Verification is a single deterministic Markdown checker; there is no quality
  estimator or task-type-specific verifier yet.
- No browser, coding, or computer-use capabilities; no plugin system; no Web UI.

## Status

Milestone 1 of 7. See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the design and
roadmap, and [`SECURITY.md`](SECURITY.md) for the threat model.
