"""Core data types for OpenCompute: a task and the plan it is broken into.

These are deliberately plain. A ``Task`` is the user's goal plus bookkeeping.
A ``Plan`` is an ordered list of ``Step`` objects that the planner produces and
the runtime walks through one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class Step(BaseModel):
    """One planned action.

    ``capability`` names a registered capability (``"research"`` or
    ``"filesystem"``). ``input`` is a small free-form mapping that describes
    what the capability should do (for example ``{"query": "..."}`` or
    ``{"action": "write", "path": "...", "content": "..."}``).
    ``purpose`` is a human-readable note so the timeline and logs are readable.
    """

    model_config = ConfigDict(extra="forbid")

    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""


class Plan(BaseModel):
    """The validated output of the planner.

    ``steps`` is the ordered list of actions. ``notes`` is optional free text
    the planner can attach for a human reader.
    """

    model_config = ConfigDict(extra="forbid")

    steps: list[Step]
    notes: str = ""


@dataclass
class Task:
    """The user's objective plus the state the runtime tracks around it."""

    goal: str
    id: str = ""
    status: str = "created"
    plan: Optional[Plan] = None
    current_step_index: int = 0
    model_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    # Cost accounting, split by confidence so we never blur exact and guessed.
    cost_exact: float = 0.0
    cost_estimated: float = 0.0
    exact_calls: int = 0
    estimated_calls: int = 0
    unknown_calls: int = 0
    # Used for the single escalation (cheaper model -> stronger).
    escalation: int = 0
    # Verification retries (re-executions after a failed verify).
    retries: int = 0
    # Wall-clock timing for benchmark measurement.
    started_at: float = 0.0
    finished_at: float = 0.0
    # Path of the final artifact produced, filled in by the runtime.
    output_path: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at

    @property
    def total_cost(self) -> float:
        # Only exact + estimated are known; unknown calls are excluded from $.
        return self.cost_exact + self.cost_estimated
