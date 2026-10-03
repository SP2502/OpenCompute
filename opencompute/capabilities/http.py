"""HTTP capability: make a simple, deterministic HTTP request.

This is a general-purpose capability (a JSON GET/POST with a timeout), intended
to show how a non-AI capability composes with the others. It never calls a
model: the request, status, and body are all plain code.

Input:
    {"method": "GET", "url": "https://...", "timeout": 10}   # GET
    {"method": "POST", "url": "...", "json": {...}, "headers": {...}, "timeout": 10}

Output:
    {"status": "ok", "status_code": 200, "url": "...", "content_type": "...",
     "text": "<body, truncated>", "bytes": N}
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import Capability, CapabilityContext

_MAX_BODY = 20_000


class HttpCapability(Capability):
    name = "http"
    description = "Make a plain HTTP GET/POST request to a URL."

    def execute(self, input: dict, ctx: CapabilityContext) -> dict:
        method = (input.get("method") or "GET").upper()
        url = (input.get("url") or "").strip()
        timeout = input.get("timeout", 10)
        if not url:
            return {"status": "failed", "error": "http step missing 'url'"}
        if not (url.startswith("http://") or url.startswith("https://")):
            return {"status": "failed", "error": f"only http/https allowed: {url}"}
        if method not in ("GET", "POST"):
            return {"status": "failed", "error": f"unsupported method: {method}"}

        headers = dict(input.get("headers") or {})
        data = None
        if method == "POST":
            payload = input.get("json")
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            if data is not None:
                headers.setdefault("Content-Type", "application/json")

        req = urllib.request.Request(url, headers=headers, data=data, method=method)
        ctx.log("action", {"capability": "http", "method": method, "url": url})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "status": "ok",
                    "status_code": resp.status,
                    "url": url,
                    "content_type": resp.headers.get("Content-Type", ""),
                    "text": body[:_MAX_BODY],
                    "bytes": len(body),
                }
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            code = getattr(exc, "code", None)
            return {"status": "failed", "error": str(exc), "status_code": code}
