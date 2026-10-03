"""Shared test doubles: a deterministic model and fake web functions.

These keep the test suite offline, fast, and reproducible -- the runtime logic is
what we're testing, not a live provider.
"""

from __future__ import annotations

import json

from opencompute.capabilities.web import SearchResult
from opencompute.core.models import ModelClient, ModelResult

GOOD_SUMMARY = """# Open-Source Projects Comparison

## Comparison
Project A is a web framework, Project B is a build tool, Project C is a database.

## References
- [Project A](https://project-a.dev)
- [Project B](https://project-b.dev)
"""

# Same content but missing the References section and any URL, so it should
# fail the deterministic verifier.
BAD_SUMMARY = """# Open-Source Projects Comparison

## Comparison
Project A is a web framework, Project B is a build tool, Project C is a database.
"""


def _plan_json() -> str:
    plan = {
        "steps": [
            {
                "capability": "research",
                "input": {"query": "open source projects", "instructions": "gather facts"},
                "purpose": "gather facts",
            },
            {
                "capability": "research",
                "input": {
                    "query": "open source projects comparison",
                    "instructions": "write the report",
                    "findings": "$research",
                },
                "purpose": "write report",
            },
            {
                "capability": "filesystem",
                "input": {"action": "write", "path": "output/comparison.md", "content": "$research"},
                "purpose": "save report",
            },
        ],
        "notes": "test plan",
    }
    return json.dumps(plan)


class FakeModel(ModelClient):
    """Always returns a valid plan and a good report."""

    default_model = "fake-cheap"

    def complete(self, messages, model=None):
        if any(m.get("role") == "system" for m in messages):
            return ModelResult(_plan_json(), cost_status="unknown")
        if "Instructions:" in messages[-1]["content"]:
            return ModelResult(GOOD_SUMMARY, prompt_tokens=100, completion_tokens=200, cost_status="unknown")
        return ModelResult("ok", cost_status="unknown")


class EscalationFake(FakeModel):
    """Good report only on the strong model; bad on the cheap model."""

    def complete(self, messages, model=None):
        if any(m.get("role") == "system" for m in messages):
            return ModelResult(_plan_json(), cost_status="unknown")
        if "Instructions:" in messages[-1]["content"]:
            if model and "strong" in model:
                return ModelResult(GOOD_SUMMARY, cost_status="unknown")
            return ModelResult(BAD_SUMMARY, cost_status="unknown")
        return ModelResult("ok", cost_status="unknown")


class PricedModel(FakeModel):
    """Returns a valid plan and a good report, with exact token costs."""

    default_model = "gpt-4o-mini"

    def complete(self, messages, model=None):
        if any(m.get("role") == "system" for m in messages):
            return ModelResult(_plan_json(), prompt_tokens=50, completion_tokens=50,
                               cost=0.0001, cost_status="estimated", provider="test")
        if "Instructions:" in messages[-1]["content"]:
            return ModelResult(GOOD_SUMMARY, prompt_tokens=100, completion_tokens=200,
                               cost=0.001, cost_status="estimated", provider="test")
        return ModelResult("ok", cost_status="unknown")


class BrokenJsonModel(FakeModel):
    """Returns invalid JSON on the first plan call, then fixes itself."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, model=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResult("not json at all", cost_status="unknown")
        return FakeModel.complete(self, messages, model=model)


def fake_search(query: str, max_results: int = 5) -> list[SearchResult]:
    return [
        SearchResult(title="Project A", url="https://project-a.dev", snippet="a web framework"),
        SearchResult(title="Project B", url="https://project-b.dev", snippet="a build tool"),
    ][:max_results]


def fake_fetch(url: str) -> str:
    return f"Fetched content for {url}"
