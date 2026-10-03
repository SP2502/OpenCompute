"""The capability interface and the small context handed to each capability.

A capability is the unit of work the runtime can schedule: ``research`` and
``filesystem`` for now. The contract is deliberately tiny -- a name, a short
``describe()``, and ``execute(input, ctx)`` returning a result dict.

"Add something only when you actually need it" is the rule here, so there is no
cancellation, health checks, or cost estimation yet. Those can grow later
without touching the runtime loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.models import ModelClient


@dataclass
class CapabilityContext:
    """What a capability needs while running.

    ``workspace`` is the scratch directory (input/research/artifacts/output).
    ``log`` appends a timeline event. ``model`` is optional because pure
    code (filesystem) never calls a model.
    """

    workspace: Path
    log: Callable[[str, dict], None]
    model: Optional[ModelClient] = None


class Capability:
    name: str = ""
    description: str = ""

    def describe(self) -> str:
        return self.description

    def execute(self, input: dict, ctx: CapabilityContext) -> dict:
        """Run one step. Returns a dict with at least a ``status`` key and
        whatever extra fields the runtime should log/remember."""
        raise NotImplementedError
