# Architecture

OpenCompute is a runtime for composing AI capabilities into workflows. The
guiding rule is simple: **use ordinary software wherever it is reliable, and an
LLM only where judgement is genuinely needed.**

## The loop

```
understand  ->  plan  ->  select  ->  execute  ->  observe  ->  verify
                                                            |
                                            +-- passed -----+-- next / done
                                            +-- failed ----->  escalate (once) -> re-run
```

Milestone 1 implements a subset of this, in a single Python process.

## Components

### Task, Step, Plan (`core/task.py`)

- `Task` — the user goal plus runtime bookkeeping (counters, escalation, cost).
- `Step` / `Plan` — the planner's output, validated by Pydantic. `extra="forbid"`
  means a malformed plan is rejected deterministically rather than silently used.

### Events and database (`core/events.py`, `core/database.py`)

An append-only `events` table in SQLite. Every plan/step/model-call/verify/cost
moment writes a row. This is the audit log, the cost ledger, and (later) the
basis for recovery, all from one source of truth.

### Models (`core/models.py`)

One tiny `ModelClient` interface with `complete(messages, model) -> ModelResult`.
`OpenAICompatClient` is the standard implementation and works with any
OpenAI-compatible endpoint (OpenAI, OpenRouter, Together, DeepSeek, Ollama).
Cost is tagged `exact` / `estimated` / `unknown` for honesty.

### Planner (`core/planner.py`)

A single LLM call that returns a JSON plan, which Pydantic validates. On invalid
JSON it asks for a repair a few times. No hierarchical planning, no
task-classification — that is a later milestone.

### Capabilities (`capabilities/`)

The unit of work. Each capability is just `describe()` + `execute(input, ctx)`.

- `filesystem` — pure Python, no model. Writes are confined to the workspace and
  reject absolute/`..` paths. This is the clearest "don't use an LLM when code
  suffices" example.
- `research` — search + fetch + LLM synthesis. The search and fetch functions are
  injectable, so the same capability runs against DuckDuckGo today and a paid
  API tomorrow without touching the runtime.

`CapabilityContext` carries the workspace, an event logger, and an optional model
client. Nothing else.

### Verification (`verification/markdown.py`)

A deterministic checker: file exists, non-empty, has a heading, has the required
sections, and contains URLs. This stands in for a quality estimator — instead of
a made-up "94% quality", it checks hard facts. Pass/fail is enough for now.

### Runtime (`core/runtime.py`)

Walks the plan. Research output is collected and substituted into the final
`filesystem` write via the `$research` placeholder. After execution it verifies;
on failure it escalates once (sets the model to the strong fallback and re-runs),
then verifies again. Every action flows through `_emit`, which writes the event
log and calls an optional progress callback (used by the CLI).

## Data flow of the demo task

```
goal
 -> planner:  [research (gather), research (write report), filesystem (write)]
 -> research x2:  each searches, fetches, synthesizes (calls the model)
 -> filesystem:    "$research" -> report text -> output/<name>.md
 -> verify_markdown_report(output/<name>.md)
 -> (on fail) escalate -> re-run -> verify again
```

## Known limitation: inter-step data flow

Each research step is independent — a later step does not yet receive an
earlier step's `summary`. Milestone 2 should pass prior step outputs into
subsequent steps (a simple `memory` keyed by capability name is enough to start).

## Roadmap (Milestones)

1. **Runtime core + demok** — done (this code): planner, two capabilities,
   verifier, one escalation, event log, cost tracking, CLI.
2. **Composition** — inter-step data flow, more capabilities, shared state.
3. **Reliability** — richer verification, recovery strategies (retry/rollback).
4. **Security** — permissions, sandboxing, audit hardening.
5. **Optimization** — model routing, a cost engine, caching, context selection.
6. **Interoperability** — MCP, plugin system, agent-to-agent protocols.
7. **Product layer** — Web UI, parallelism, observability.

## Design principles

- **Deterministic first.** Files, JSON, timeouts, and validation are code, not
  prompts.
- **Quality before cost.** Never drop verification or safety to save tokens.
- **Model-agnostic.** Any OpenAI-compatible provider; no vendor lock-in.
- **Small surface.** Add a method or class only when a real need exists.
