"""A tiny SQLite-backed store for the event log and task state.

One table, ``events``, records an append-only history. The runtime reads and
writes through this module so nothing about persistence leaks into the rest of
the code. SQLite is local, zero-config, and more than enough for Milestone 1.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .events import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind     TEXT NOT NULL,
    task_id  TEXT NOT NULL,
    payload  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task ON events (task_id, seq);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def log(self, kind: str, task_id: str, data: dict[str, Any]) -> Event:
        """Append one event and return it with its sequence number assigned."""
        cur = self._conn.execute(
            "INSERT INTO events (kind, task_id, payload) VALUES (?, ?, ?)",
            (kind, task_id, json.dumps(data, default=str)),
        )
        self._conn.commit()
        ev = Event(kind=kind, task_id=task_id, data=data, seq=cur.lastrowid)
        return ev

    def events_for(self, task_id: str) -> list[Event]:
        rows = self._conn.execute(
            "SELECT seq, kind, task_id, payload FROM events WHERE task_id = ? ORDER BY seq",
            (task_id,),
        ).fetchall()
        return [Event.from_row(tuple(r)) for r in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
