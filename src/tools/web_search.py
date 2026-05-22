"""Lightweight web search via DuckDuckGo's HTML endpoint.

No API key required. Returns up to `limit` results as a list of
{"title", "url", "snippet"} dicts. On any failure (timeout, parse error,
network) returns an empty list — sub-agents handle empty results gracefully.
"""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote

import httpx


_TIMEOUT_SECONDS = 15.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


_RESULT_PATTERN = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)

_TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    return unescape(_TAG_PATTERN.sub("", text)).strip()


def _resolve_redirect(href: str) -> str:
    """DuckDuckGo HTML wraps real URLs in /l/?uddg=...&rut=... — unwrap it."""
    if href.startswith("//duckduckgo.com/l/?"):
        match = re.search(r"uddg=([^&]+)", href)
        if match:
            return unquote(match.group(1))
    return href


async def web_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Run a DuckDuckGo HTML search. Returns up to `limit` results."""
    if not query or not query.strip():
        return []
    limit = max(1, min(limit, 10))

    url = "https://html.duckduckgo.com/html/"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
            response = await client.post(
                url,
                data={"q": query.strip()},
                headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            )
            response.raise_for_status()
            html = response.text
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for match in _RESULT_PATTERN.finditer(html):
        href = _resolve_redirect(match.group("href").strip())
        title = _strip_tags(match.group("title"))
        snippet = _strip_tags(match.group("snippet"))
        if not href or not title:
            continue
        results.append({"title": title[:200], "url": href, "snippet": snippet[:300]})
        if len(results) >= limit:
            break
    return results
