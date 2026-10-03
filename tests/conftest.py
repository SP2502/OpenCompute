"""Shared test doubles: a deterministic model and fake web functions.

These keep the test suite offline, fast, and reproducible -- the runtime logic is
what we're testing, not a live provider.
"""

from __future__ import annotations

import json

from opencompute.capabilities.web import SearchResult
from opencompute.core.models import ModelClient, ModelResult

GOOD_SUMMARY = """# Weather API Comparison

## Comparison
Open-Meteo is free, OpenWeatherMap has a free tier, WeatherAPI offers a limited free plan.

## References
- [Open-Meteo](https://open-meteo.com)
- [OpenWeatherMap](https://openweathermap.org)
"""

# Same content but missing the References section and any URL, so it should
# fail the deterministic verifier.
BAD_SUMMARY = """# Weather API Comparison

## Comparison
Open-Meteo is free, OpenWeatherMap has a free tier, WeatherAPI offers a limited free plan.
"""


def _plan_json() -> str:
    plan = {
        "steps": [
            {
                "capability": "research",
                "input": {"query": "weather api providers", "instructions": "find providers"},
                "purpose": "collect providers",
            },
            {
                "capability": "research",
                "input": {"query": "weather api comparison", "instructions": "write the report"},
                "purpose": "write report",
            },
            {
                "capability": "filesystem",
                "input": {"action": "write", "path": "output/weather-api-comparison.md", "content": "$research"},
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
            return ModelResult(_plan_json(), cost_kind="unknown")
        if "Instructions:" in messages[-1]["content"]:
            return ModelResult(GOOD_SUMMARY, prompt_tokens=100, completion_tokens=200, cost_kind="unknown")
        return ModelResult("ok", cost_kind="unknown")


class EscalationFake(FakeModel):
    """Good report only on the strong model; bad on the cheap model."""

    def complete(self, messages, model=None):
        if any(m.get("role") == "system" for m in messages):
            return ModelResult(_plan_json(), cost_kind="unknown")
        if "Instructions:" in messages[-1]["content"]:
            if model and "strong" in model:
                return ModelResult(GOOD_SUMMARY, cost_kind="unknown")
            return ModelResult(BAD_SUMMARY, cost_kind="unknown")
        return ModelResult("ok", cost_kind="unknown")


class BrokenJsonModel(FakeModel):
    """Returns invalid JSON on the first plan call, then fixes itself."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, model=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResult("not json at all", cost_kind="unknown")
        return FakeModel.complete(self, messages, model=model)


def fake_search(query: str, max_results: int = 5) -> list[SearchResult]:
    return [
        SearchResult(title="Open-Meteo", url="https://open-meteo.com", snippet="free weather"),
        SearchResult(title="OpenWeatherMap", url="https://openweathermap.org", snippet="freemium"),
    ][:max_results]


def fake_fetch(url: str) -> str:
    return f"Fetched content for {url}"
