"""The planner turns a free-text goal into a validated JSON plan.

This is the simplest thing that works: one model call producing JSON, which
Pydantic then validates deterministically. If the model returns malformed JSON
we try a couple of small repairs before giving up. No fancy planning pipeline.
"""

from __future__ import annotations

import json
import re

from .models import ModelClient
from .task import Plan

_CAPABILITIES = ["research", "filesystem"]

_SYSTEM_PROMPT = """You convert a user goal into a short plan made of discrete steps.

Available capabilities:
- research  -> search the web / fetch pages and synthesize findings.
               input: {"query": "...", "instructions": "..."}
- filesystem -> write (or read) files in the shared workspace.
               input: {"action": "write", "path": "output/<file>.md", "content": "..."}

Reply with ONLY a JSON object, no markdown fences, shaped exactly like:

{"steps": [{"capability": "research", "input": {"query": "...", "instructions": "..."}, "purpose": "..."}], "notes": "..."}

Rules:
- Keep the plan to the fewest steps that get the job done (usually 2-5).
- For a report task: do the web research in one or more research steps, then have ONE
  final research step whose instructions asks for the complete report in Markdown
  (with clear section headings and a References list of markdown links).
- Always finish with a filesystem write step: path "output/<name>.md" and content
  exactly the string "$research" (the runtime substitutes the research output there).
- Every claim in the report must be backed by sources the research steps collect.
- "input" must use only the keys shown above for that capability.
"""


def _extract_json(text: str) -> str:
    """Pull the JSON object out of the model output, tolerating stray text."""
    text = text.strip()
    # Strip code fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    # Find the outermost {...}.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text


class Planner:
    def __init__(self, model: ModelClient):
        self.model = model

    def plan(self, goal: str, model: str | None = None) -> Plan:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": goal},
        ]
        result = self.model.complete(messages, model=model)
        raw = result.text
        for attempt in range(3):
            try:
                return Plan.model_validate_json(_extract_json(raw))
            except Exception as exc:  # noqa: BLE001 - validation failure
                # Last attempt: raise so the runtime can escalate models.
                if attempt == 2:
                    raise ValueError(f"planner returned invalid JSON: {exc}") from exc
                repair = (
                    "Your previous reply was not valid JSON. Reply with ONLY the "
                    "JSON object described earlier, nothing else."
                )
                result = self.model.complete(
                    [*messages, {"role": "assistant", "content": raw},
                     {"role": "user", "content": repair}],
                    model=model,
                )
                raw = result.text
        raise ValueError("planner failed to produce valid JSON")
