"""Research capability: search + fetch + LLM synthesis.

The capability collects sources for a query, then hands them to the model along
with the user's instructions so it produces a sourced summary. The actual web
search and fetch are swappable functions so the same capability works offline,
with a paid API, or in a sandbox with its own tools.
"""

from __future__ import annotations

from typing import Callable, Optional

from .base import Capability, CapabilityContext
from .web import SearchResult, duckduckgo_search, fetch_text

_SYNTHESIS_PROMPT = """You are a research assistant. Use ONLY the sources below.
Write a concise, factual summary that answers the user's instructions.

Instructions:
{instructions}

Sources (each marked with a [n] index):
{sources}

Requirements:
- Cite every factual claim with the bracketed index of its source, e.g. [1].
- If a claim is not found in the sources, do not invent it.
- Prefer official/primary sources.
End with a "References" line listing each source as a markdown link.
"""


class ResearchCapability(Capability):
    name = "research"
    description = "Search the web, fetch pages, and synthesize a sourced summary."

    def __init__(
        self,
        search_fn: Callable[[str, int], list[SearchResult]] = duckduckgo_search,
        fetch_fn: Callable[[str], str] = fetch_text,
        max_sources: int = 4,
    ):
        self.search_fn = search_fn
        self.fetch_fn = fetch_fn
        self.max_sources = max_sources

    def execute(self, input: dict, ctx: CapabilityContext) -> dict:
        query = (input.get("query") or "").strip()
        instructions = (input.get("instructions") or "").strip()
        if not query:
            return {"status": "failed", "error": "research step missing 'query'"}

        ctx.log("action", {"capability": "research", "query": query})
        hits = self.search_fn(query, self.max_sources)
        if not hits:
            return {"status": "failed", "error": f"no search results for: {query}"}

        # Fetch the top pages (best-effort; a failed fetch is skipped).
        sources: dict[int, dict] = {}
        for i, hit in enumerate(hits, start=1):
            body = self.fetch_fn(hit.url)
            sources[i] = {
                "title": hit.title,
                "url": hit.url,
                "snippet": hit.snippet,
                "text": body,
            }

        if ctx.model is None:
            return {
                "status": "failed",
                "error": "research requires a model client on the context",
            }

        source_block = "\n\n".join(
            f"[{i}] {s['title']}\n    url: {s['url']}\n    {s['text'][:4000]}"
            for i, s in sources.items()
        )
        result = ctx.model.complete(
            [{
                "role": "user",
                "content": _SYNTHESIS_PROMPT.format(
                    instructions=instructions or query,
                    sources=source_block,
                ),
            }]
        )

        return {
            "status": "ok",
            "query": query,
            "summary": result.text,
            "sources": [
                {"title": s["title"], "url": s["url"]} for s in sources.values()
            ],
        }
