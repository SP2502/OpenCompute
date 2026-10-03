"""Command-line interface.

Usage:
    opencompute run "Research three weather API providers and create a report"

Configuration comes from environment variables (nothing is hard-coded):

    OPENAI_API_KEY          required, any OpenAI-compatible provider key
    OPENAI_BASE_URL         optional, for non-OpenAI endpoints (OpenRouter, Ollama...)
    OPENCOMPUTE_MODEL       default model (default: gpt-4o-mini)
    OPENCOMPUTE_STRONG_MODEL fallback model used on escalation (default: gpt-4o)
    OPENCOMPUTE_WORKSPACE   workspace directory (default: ./workspace)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .capabilities.filesystem import FilesystemCapability
from .capabilities.research import ResearchCapability
from .core.database import Database
from .core.models import OpenAICompatClient
from .core.runtime import Runtime

_CHECK = "✓"
_CROSS = "✗"


def _make_progress() -> callable:
    """Return an event -> friendly-line callback for the timeline."""
    saw_research_run = False

    def progress(kind: str, data: dict) -> None:
        nonlocal saw_research_run
        if kind == "plan_start":
            print("Planning...")
        elif kind == "plan_created":
            print(f"{_CHECK} Plan created ({len(data.get('steps', []))} steps)")
        elif kind == "step" and data.get("status") == "running":
            cap = data.get("capability")
            if cap == "research":
                saw_research_run = True
                print(f"Researching: {data.get('purpose') or ''}")
            elif cap == "filesystem" and data.get("purpose"):
                print(f"{data.get('purpose') or 'Writing file'}...")
        elif kind == "research":
            n = len(data.get("sources", []))
            print(f"  {_CHECK} collected {n} source(s)")
        elif kind == "step" and data.get("status") == "ok" and data.get("capability") == "filesystem":
            print(f"{_CHECK} Report written")
        elif kind == "step" and data.get("status") == "failed":
            print(f"{_CROSS} {data.get('capability')} failed: {data.get('error')}")
        elif kind == "verify_start":
            print("Verifying...")
        elif kind == "verify":
            mark = _CHECK if data.get("passed") else _CROSS
            print(f"{mark} Verification {'passed' if data.get('passed') else 'failed'}")
            for f in data.get("failures", []):
                print(f"    - {f}")
        elif kind == "escalate":
            print(f"  ↻ escalating to {data.get('to_model')}: {data.get('reason')}")
        elif kind == "cost":
            cost = data.get("estimated_cost", 0.0)
            kind_label = data.get("cost_kind", "unknown")
            print(f"\nCost: ${cost:.4f} ({kind_label}; {data.get('model_calls', 0)} model calls)")
            if kind_label == "unknown":
                print("  (provider prices not in the lookup table, so cost is unknown)")

    return progress


def _build_runtime() -> tuple[Runtime, Path, Database]:
    model_name = os.environ.get("OPENCOMPUTE_MODEL", "gpt-4o-mini")
    strong_name = os.environ.get("OPENCOMPUTE_STRONG_MODEL", "gpt-4o")
    base_url = os.environ.get("OPENAI_BASE_URL") or None

    model = OpenAICompatClient(default_model=model_name, base_url=base_url)
    workspace = Path(os.environ.get("OPENCOMPUTE_WORKSPACE", "workspace")).resolve()
    for sub in ("input", "research", "artifacts", "output", "logs"):
        (workspace / sub).mkdir(parents=True, exist_ok=True)
    db = Database(workspace / "state" / "events.db")

    capabilities = {
        "filesystem": FilesystemCapability(),
        "research": ResearchCapability(),
    }
    runtime = Runtime(
        model=model,
        capabilities=capabilities,
        workspace=workspace,
        db=db,
        strong_model=strong_name,
        cheap_model=model_name,
        on_event=_make_progress(),
    )
    return runtime, workspace, db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencompute", description="Compose AI capabilities into autonomous workflows.")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a goal end to end")
    run_p.add_argument("goal", nargs="+", help="the objective, e.g. \"Research three weather APIs\"")

    sub.add_parser("capabilities", help="list available capabilities")

    args = parser.parse_args(argv)

    if args.command == "capabilities":
        print("Available capabilities:\n  research    -- search + fetch + LLM synthesis\n  filesystem  -- read/write files in the workspace")
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        print("error: set OPENAI_API_KEY (and optionally OPENAI_BASE_URL) first.", file=sys.stderr)
        return 1

    goal = " ".join(args.goal)
    runtime, workspace, db = _build_runtime()
    task_id = f"task-{os.urandom(4).hex()}"
    print(f"Goal: {goal}\nWorkspace: {workspace}\n")
    task = runtime.run(goal, task_id=task_id)

    db.close()
    print(f"\nTask {task.id}: {task.status}")
    print(f"Report: {task.output_path or (workspace / 'output')}")
    return 0 if task.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
