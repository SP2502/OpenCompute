"""Filesystem capability: deterministic file operations, no model involved.

This is the clearest "use normal software, not an LLM" example in the project.
It can write a file under the workspace and read one back. Paths are joined
under the workspace root so a bad plan cannot escape it.
"""

from __future__ import annotations

import os

from .base import Capability, CapabilityContext


class FilesystemCapability(Capability):
    name = "filesystem"
    description = "Read and write files inside the shared workspace."

    def execute(self, input: dict, ctx: CapabilityContext) -> dict:
        action = input.get("action", "write")
        path = input.get("path") or ""
        # Keep everything inside the workspace; reject absolute or ../ paths.
        target = (ctx.workspace / path).resolve()
        if not str(target).startswith(str(ctx.workspace.resolve())):
            return {"status": "failed", "error": f"path escapes workspace: {path}"}

        if action == "write":
            content = input.get("content", "")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return {"status": "ok", "path": str(target), "bytes": target.stat().st_size}

        if action == "read":
            if not target.exists():
                return {"status": "failed", "error": f"file not found: {path}"}
            return {"status": "ok", "content": target.read_text(encoding="utf-8")}

        return {"status": "failed", "error": f"unknown action: {action}"}
