"""Minimal, dependency-free web helpers: a search and a page fetch.

These use only the Python standard library so OpenCompute runs with no API key
for basic web lookup. DuckDuckGo's HTML endpoint is free and needs no account,
though it is rate-limited; a faster/paid search (Serper, Tavily, Brave, etc.)
can be swapped in later by passing a different function to the research
capability.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) OpenCompute/0.1"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def duckduckgo_search(query: str, max_results: int = 5) -> list[SearchResult]:
    """Search DuckDuckGo's HTML endpoint and return title/url/snippet tuples."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
        {"q": query}
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        page = resp.read().decode("utf-8", errors="replace")

    results: list[SearchResult] = []
    # Each hit is an <a class="result__a" href="...">Title</a> followed by a
    # snippet in a <a class="result__snippet">...</a>.
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
        r'.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        page,
        re.DOTALL,
    ):
        href = html.unescape(match.group(1))
        # DuckDuckGo wraps real URLs in a redirect; strip it out.
        parsed = urllib.parse.urlparse(href)
        qs = urllib.parse.parse_qs(parsed.query)
        if "uddg" in qs:
            href = qs["uddg"][0]
        title = html.unescape(re.sub(r"<[^>]+>", "", match.group(2))).strip()
        snippet = html.unescape(re.sub(r"<[^>]+>", "", match.group(3))).strip()
        if href.startswith("http"):
            results.append(SearchResult(title=title, url=href, snippet=snippet))
        if len(results) >= max_results:
            break
    return results


def fetch_text(url: str, max_chars: int = 20000) -> str:
    """Fetch a URL and return a stripped-down text body, or '' on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    # Crude but good enough: drop script/style, then tags, collapse whitespace.
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text[:max_chars]
