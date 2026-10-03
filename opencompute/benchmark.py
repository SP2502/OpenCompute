"""The general OpenCompute benchmark.

This is the baseline measurement we need before we can test OpenCompute's core
hypothesis (same useful work, less unnecessary computation). It runs a real,
general-purpose task -- compare three open-source projects -- through the full
pipeline and reports the numbers we care about.

The subject is deliberately generic and configurable, so the benchmark can be
pointed at any comparison without changing the runtime.
"""

from __future__ import annotations

import time
from typing import Optional

from .core.runtime import Runtime

_DEFAULT_GOAL = (
    "Research three open-source software projects, collect relevant information "
    "from their official documentation or repositories, compare them, create a "
    "Markdown report, and verify that the report contains the required sections "
    "and source URLs."
)


def build_goal(subject: Optional[str] = None) -> str:
    if subject:
        return (
            f"Research {subject}, collect relevant information from their official "
            "documentation or repositories, compare them, create a Markdown report, "
            "and verify that the report contains the required sections and source URLs."
        )
    return _DEFAULT_GOAL


def run_benchmark(runtime: Runtime, subject: Optional[str] = None) -> dict:
    """Run the benchmark once and return its metrics as a dict."""
    goal = build_goal(subject)
    print(f"Benchmark goal: {goal}\n")

    start = time.perf_counter()
    task = runtime.run(goal, task_id="benchmark")
    wall = time.perf_counter() - start

    # Last verification verdict from the event log (the task status mirrors it).
    passed = task.status == "succeeded"

    metrics = {
        "success": passed,
        "model_calls": task.model_calls,
        "input_tokens": task.tokens_in,
        "output_tokens": task.tokens_out,
        "total_tokens": task.total_tokens,
        "model_cost": task.total_cost,
        "cost_exact": task.cost_exact,
        "cost_estimated": task.cost_estimated,
        "unknown_calls": task.unknown_calls,
        "execution_time": wall,
        "verification": "passed" if passed else "failed",
        "retries": task.retries,
        "escalations": task.escalation,
        "output_path": task.output_path,
    }

    print("\n=== Benchmark result ===")
    print(f"task success:     {metrics['success']}")
    print(f"verification:     {metrics['verification']}")
    print(f"model calls:      {metrics['model_calls']}")
    print(f"input tokens:     {metrics['input_tokens']}")
    print(f"output tokens:    {metrics['output_tokens']}")
    print(f"total tokens:     {metrics['total_tokens']}")
    print(f"model cost:      ${metrics['model_cost']:.6f} (USD)")
    print(f"execution time:   {metrics['execution_time']:.2f}s")
    print(f"retries:          {metrics['retries']}")
    print(f"escalations:      {metrics['escalations']}")
    return metrics
