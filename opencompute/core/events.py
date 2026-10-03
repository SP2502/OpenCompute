"""Append-only execution history.

Every meaningful thing the runtime does is recorded as an ``Event``. The
``kind`` is one of a small fixed set of strings; ``data`` holds whatever JSON
fits that event. This is the backbone of the audit log and cost transparency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Event:
    kind: str  # e.g. "plan", "capability", "action", "verify", "cost", ...
    task_id: str
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_row(self) -> tuple:
        """Flatten into a tuple the SQLite layer can insert."""
        return (
            self.seq,
            self.kind,
            self.task_id,
            json.dumps(self.data, default=str),
        )

    @classmethod
    def from_row(cls, row) -> "Event":
        seq, kind, task_id, payload = row
        return cls(
            seq=seq,
            kind=kind,
            task_id=task_id,
            data=json.loads(payload) if payload else {},
        )
