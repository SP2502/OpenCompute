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
`ModelResult` carries text, input/output tokens, a `cost_status`
(`exact` / `estimated` / `unknown`), the provider, and latency. The runtime wraps
this in a tracing layer that buckets cost by confidence and attributes every
call to a step id and purpose.

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
  API tomorrow without touching the runtime. It accepts optional `findings`
  input so a later research step can build on earlier findings.
- `http` — a deterministic GET/POST with a timeout. It never calls a model and
  exists to show a non-AI capability composing with the others.

`CapabilityContext` carries the workspace, an event logger, an optional model
client, and the shared context. Nothing else.

### Shared context (`runtime._resolve`)

Between steps, the runtime keeps a small in-memory map of each capability's most
recent result. A step's `input` may reference earlier output with `$capability`
or `$capability.field` (e.g. `"findings": "$research"`), and the runtime
substitutes the value just before execution. The bare `$capability` form resolves
to a capability's primary output (the main field) (`summary` for research, `path` for
filesystem, `text` for http).

This is deliberately a tiny, explicit substitution — not a memory system. Only
the fields a step explicitly references are injected, so context is never
blindly dumped into every model call.

### Verification (`verification/markdown.py`)

A deterministic checker: file exists, non-empty, has a heading, has the required
sections, and contains URLs. This stands in for a quality estimator — instead of
a made-up "94% quality", it checks hard facts. Pass/fail is enough for now.

### Runtime (`core/runtime.py`)

Walks the plan. Each step's `$references` are resolved against the shared
context, then the capability runs; its result is stored back into the context.
After execution the runtime verifies; on failure it escalates once (sets the
model to the strong fallback and re-runs), then verifies again. Every action
flows through `_emit`, which writes the event log and calls an optional
progress callback (used by the CLI). The run is timed, and model cost is
aggregated on the `Task` (exact / estimated / unknown, plus totals).

## Data flow of the benchmark task

```
goal
 -> planner:  [research (gather), research (write report, findings=$research),
               filesystem (write, content=$research)]
 -> research (gather):  search + fetch + synthesize -> context["research"]
 -> research (write):   findings substitute the prior summary, synthesize report
 -> filesystem:         "$research" -> report text -> output/<name>.md
 -> verify_markdown_report(output/<name>.md)
 -> (on fail) escalate -> re-run -> verify again
```

## Benchmark

`opencompute/benchmark.py` runs a general comparison task (three open-source
projects, configurable via `--subject`) through the pipeline and reports task
success, model/token counts, cost, execution time, verification, retries, and
escalations. It is the baseline for testing the central hypothesis later.

## Roadmap (Milestones)

1. **Runtime core** — done: planner, two capabilities, verifier, one
escalation, event log, CLI.
2. **Composition + measurement** — done (this code): inter-step context,
   token/cost accounting, an HTTP capability, and the benchmark.
3. **Reliability** — richer verification, recovery strategies (retry/rollback).
4. **Security** — permissions, sandboxing, audit hardening.
5. **Optimization** — model routing, a cost engine, caching, context selection.
6. **Interoperability** — MCP, plugin system, agent-to-agent protocols.
7. **Product layer** — Web UI, parallelism, observability.

## The central hypothesis

The long-term goal is "same useful work, less unnecessary computation". OpenCompute
will split each task into deterministic work (free code) and AI work (the cheapest
model that reliably passes verification), then escalate only on evidence. Milestone 2
does not implement routing or an optimizer — it builds the measurement layer needed
to test that hypothesis honestly in Milestone 3 and beyond.

## Design principles

- **Deterministic first.** Files, JSON, timeouts, and validation are code, not
  prompts.
- **Quality before cost.** Never drop verification or safety to save tokens.
- **Model-agnostic.** Any OpenAI-compatible provider; no vendor lock-in.
- **Small surface.** Add a method or class only when a real need exists.
