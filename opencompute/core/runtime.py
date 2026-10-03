"""The runtime loop: understand -> plan -> execute -> verify -> (escalate | done).

This is the heart of OpenCompute, kept deliberately small. It:

    1. asks the planner for a validated plan
    2. walks the steps, dispatching each to its capability
    3. writes research output into the final filesystem step
    4. verifies the result deterministically
    5. on failure, escalates once to a stronger model and retries

Cost is tracked on the Task as a side effect of every model call, and every
meaningful moment is written to the event log.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .database import Database
from .models import ModelClient, ModelResult
from .planner import Planner
from .task import Task

from ..capabilities.base import Capability, CapabilityContext
from ..verification.markdown import verify_markdown_report

# For a bare "$capability" reference this is the field considered its main
# output (so "$research" means the summary text, "$http" the body, etc.).
_PRIMARY = {"research": "summary", "filesystem": "path", "http": "text"}


def _resolve(value, memory: dict):
    """Replace "$capability" / "$capability.field" references with stored step
    output. This is deliberately a tiny, explicit string substitution -- not a
    memory system. Unresolved references are left as literal text."""
    if isinstance(value, str) and value.startswith("$") and len(value) > 1:
        parts = value[1:].split(".")
        item = memory.get(parts[0])
        if item is None:
            return value
        if len(parts) == 1:
            key = _PRIMARY.get(parts[0])
            return item.get(key) if key and isinstance(item, dict) else item
        for p in parts[1:]:
            if isinstance(item, dict) and p in item:
                item = item[p]
            else:
                return value
        return item
    if isinstance(value, dict):
        return {k: _resolve(v, memory) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, memory) for v in value]
    return value


class TracingModel:
    """Wraps a ModelClient so every call updates the task's counters/log."""

    def __init__(
        self,
        client: ModelClient,
        task: Task,
        log,
        active_model: Optional[str] = None,
    ):
        self.client = client
        self.task = task
        self.log = log
        self.active_model = active_model or client.default_model
        # Filled in by the runtime just before each step so model events carry
        # an attribution (which step, for what purpose).
        self.step_id = ""
        self.purpose = ""

    def complete(self, messages: list[dict], model: Optional[str] = None) -> ModelResult:
        chosen = model or self.active_model
        result = self.client.complete(messages, model=chosen)

        # Aggregate into the task, splitting cost by confidence so we never
        # blur an exact number with a guess.
        self.task.model_calls += 1
        self.task.tokens_in += result.prompt_tokens
        self.task.tokens_out += result.completion_tokens
        if result.cost_status == "exact":
            self.task.cost_exact += result.cost
            self.task.exact_calls += 1
        elif result.cost_status == "estimated":
            self.task.cost_estimated += result.cost
            self.task.estimated_calls += 1
        else:
            self.task.unknown_calls += 1
            # Unknown-cost calls are not added to a dollar total.

        self.log("model_call", {
            "model": chosen,
            "provider": result.provider,
            "input_tokens": result.prompt_tokens,
            "output_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "cost": round(result.cost, 6),
            "cost_status": result.cost_status,
            "latency": round(result.latency, 4),
            "step_id": self.step_id,
            "purpose": self.purpose,
        })
        return result


class Runtime:
    def __init__(
        self,
        model: ModelClient,
        capabilities: dict[str, Capability],
        workspace: Path,
        db: Database,
        strong_model: Optional[str] = None,
        cheap_model: Optional[str] = None,
        on_event=None,
    ):
        self.model = model
        self.capabilities = capabilities
        self.workspace = Path(workspace)
        self.db = db
        self.cheap_model = cheap_model or model.default_model
        self.strong_model = strong_model or model.default_model
        self.planner = Planner(model)  # planner gets the raw client; trace via runtime
        self.on_event = on_event

    def _emit(self, kind: str, task_id: str, data: dict) -> None:
        """Log to the database, then notify the optional progress callback."""
        self.db.log(kind, task_id, data)
        if self.on_event is not None:
            self.on_event(kind, data)

    def run(self, goal: str, task_id: str = "") -> Task:
        import time

        task = Task(goal=goal, id=task_id)
        task.started_at = time.time()
        self._emit("task_created", task.id, {"goal": goal})

        # --- plan ---
        self._emit("plan_start", task.id, {})
        tracing = TracingModel(self.model, task, self._log_binder(task.id),
                               active_model=self.cheap_model)
        plan = None
        try:
            plan = self.planner.plan(goal, model=self.cheap_model)
        except ValueError:
            # The cheap model could not produce a valid plan: escalate once.
            self._escalate(task, tracing, "planner returned invalid JSON")
            plan = self.planner.plan(goal, model=self.strong_model)

        task.plan = plan
        self._emit("plan_created", task.id, {"steps": [s.purpose or s.capability for s in plan.steps]})

        # --- execute ---
        output_path = self._execute(plan, task, tracing, task.id)

        # --- verify ---
        self._emit("verify_start", task.id, {"path": str(output_path)})
        verification = verify_markdown_report(output_path)
        self._emit("verify", task.id, {
            "passed": verification.passed,
            "checks": verification.checks,
            "failures": verification.failures,
        })

        if not verification.passed and task.escalation == 0:
            self._escalate(task, tracing, "; ".join(verification.failures))
            task.retries += 1
            output_path = self._execute(plan, task, tracing, task.id, stronger=True)
            verification = verify_markdown_report(output_path)
            self._emit("verify", task.id, {
                "passed": verification.passed,
                "checks": verification.checks,
                "failures": verification.failures,
            })

        task.status = "succeeded" if verification.passed else "failed"
        task.output_path = str(output_path)
        task.finished_at = time.time()
        self._emit("cost", task.id, self._cost_summary(task))
        self._emit("task_done", task.id, {"status": task.status})
        return task

    def _cost_summary(self, task: Task) -> dict:
        """The task-level cost report, used by both the event log and the CLI."""
        return {
            "status": task.status,
            "model_calls": task.model_calls,
            "input_tokens": task.tokens_in,
            "output_tokens": task.tokens_out,
            "total_tokens": task.total_tokens,
            "model_cost": round(task.total_cost, 6),
            "cost_exact": round(task.cost_exact, 6),
            "cost_estimated": round(task.cost_estimated, 6),
            "exact_calls": task.exact_calls,
            "estimated_calls": task.estimated_calls,
            "unknown_calls": task.unknown_calls,
            "escalations": task.escalation,
            "retries": task.retries,
            "duration": round(task.duration, 3),
        }

    # -- internals ----------------------------------------------------------

    def _log_binder(self, task_id: str):
        def log(kind: str, data: dict) -> None:
            self._emit(kind, task_id, data)
        return log

    def _escalate(self, task: Task, tracing: TracingModel, reason: str) -> None:
        task.escalation += 1
        tracing.active_model = self.strong_model
        self._emit("escalate", task.id, {"reason": reason, "to_model": self.strong_model})

    def _execute(self, plan, task, tracing, task_id, stronger=False) -> Path:
        """Walk the steps, feeding each step's output into a shared context that
        later steps can reference by name (e.g. "$research")."""
        log = self._log_binder(task_id)
        memory: dict = {}  # short-term shared state: capability name -> result
        ctx = CapabilityContext(workspace=self.workspace, log=log, model=tracing,
                                context=memory)
        written_path: Optional[Path] = None

        for i, step in enumerate(plan.steps):
            if step.capability not in self.capabilities:
                log("step", {"capability": step.capability, "status": "unavailable"})
                task.errors.append(f"unknown capability: {step.capability}")
                continue

            capability = self.capabilities[step.capability]
            tracing.step_id = f"{task_id}:{i}"
            tracing.purpose = step.purpose
            log("step", {"index": i, "capability": step.capability,
                         "purpose": step.purpose, "status": "running"})

            # Resolve $references (e.g. "$research", "$research.sources") against
            # the shared context, rather than dumping it all into every step.
            inputs = _resolve(step.input, memory)
            result = capability.execute(inputs, ctx)

            if result.get("status") != "ok":
                log("step", {"index": i, "capability": step.capability,
                             "status": "failed", "error": result.get("error")})
                task.errors.append(result.get("error", "step failed"))
                continue

            log("step", {"index": i, "capability": step.capability,
                         "status": "ok", "purpose": step.purpose})
            log("capability", {"capability": step.capability, "result_keys": list(result.keys())})
            memory[step.capability] = result

            if step.capability == "research":
                log("research", {"query": result.get("query", ""),
                                 "sources": result.get("sources", [])})
            elif step.capability == "filesystem":
                written_path = Path(result.get("path"))

        if written_path is not None:
            return written_path

        # Fallback: no filesystem step ran, so dump what research produced.
        final_path = self.workspace / "output" / "report.md"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        summary = (memory.get("research") or {}).get("summary", "")
        final_path.write_text(summary, encoding="utf-8")
        return final_path

    def make_workspace(self) -> Path:
        for sub in ("input", "research", "artifacts", "output", "logs"):
            (self.workspace / sub).mkdir(parents=True, exist_ok=True)
        return self.workspace
