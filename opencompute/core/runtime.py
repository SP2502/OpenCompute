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

    def complete(self, messages: list[dict], model: Optional[str] = None) -> ModelResult:
        chosen = model or self.active_model
        result = self.client.complete(messages, model=chosen)
        self.task.model_calls += 1
        self.task.tokens_in += result.prompt_tokens
        self.task.tokens_out += result.completion_tokens
        self.task.estimated_cost += result.cost
        # The most recent call decides the overall confidence level.
        self.task.cost_kind = result.cost_kind
        self.log("model_call", {
            "model": chosen,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "cost": round(result.cost, 6),
            "cost_kind": result.cost_kind,
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
        task = Task(goal=goal, id=task_id)
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
            output_path = self._execute(plan, task, tracing, task.id, stronger=True)
            verification = verify_markdown_report(output_path)
            self._emit("verify", task.id, {
                "passed": verification.passed,
                "checks": verification.checks,
                "failures": verification.failures,
            })

        task.status = "succeeded" if verification.passed else "failed"
        task.output_path = str(output_path)
        self._emit("cost", task.id, {
            "model_calls": task.model_calls,
            "tokens_in": task.tokens_in,
            "tokens_out": task.tokens_out,
            "estimated_cost": round(task.estimated_cost, 6),
            "cost_kind": task.cost_kind,
            "status": task.status,
        })
        self._emit("task_done", task.id, {"status": task.status})
        return task

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
        """Walk the steps, feeding research output into the final write."""
        research_parts: list[str] = []
        log = self._log_binder(task_id)
        ctx = CapabilityContext(workspace=self.workspace, log=log, model=tracing)
        written_path: Optional[Path] = None

        for i, step in enumerate(plan.steps):
            if step.capability not in self.capabilities:
                log("step", {"capability": step.capability, "status": "unavailable"})
                task.errors.append(f"unknown capability: {step.capability}")
                continue

            capability = self.capabilities[step.capability]
            log("step", {"index": i, "capability": step.capability,
                         "purpose": step.purpose, "status": "running"})

            # The plan writes the assembled research to the file with "$research".
            inputs = dict(step.input)
            if step.capability == "filesystem" and inputs.get("content") == "$research":
                inputs["content"] = "\n\n---\n\n".join(research_parts)
            result = capability.execute(inputs, ctx)

            if result.get("status") != "ok":
                log("step", {"index": i, "capability": step.capability,
                             "status": "failed", "error": result.get("error")})
                task.errors.append(result.get("error", "step failed"))
                continue

            log("step", {"index": i, "capability": step.capability,
                         "status": "ok", "purpose": step.purpose})

            if step.capability == "research":
                summary = result.get("summary", "")
                research_parts.append(summary)
                log("research", {"query": result.get("query", ""),
                                 "sources": result.get("sources", [])})
            elif step.capability == "filesystem":
                written_path = Path(result.get("path"))

        if written_path is not None:
            return written_path

        # Fallback: no filesystem step ran, so dump what research produced.
        final_path = self.workspace / "output" / "report.md"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text("\n\n---\n\n".join(research_parts), encoding="utf-8")
        return final_path

    def make_workspace(self) -> Path:
        for sub in ("input", "research", "artifacts", "output", "logs"):
            (self.workspace / sub).mkdir(parents=True, exist_ok=True)
        return self.workspace
