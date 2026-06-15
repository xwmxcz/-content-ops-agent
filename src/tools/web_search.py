"""Web search adapter used by tool-calling agents.

Stable search APIs are tried first when configured. Keyless HTML fallbacks are
kept only as a best-effort local/demo option because search engines may return
anti-bot pages instead of results.
"""
from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import unquote

import httpx

from src.utils import config


SearchResult = dict[str, str]
SearchResponse = list[SearchResult] | dict[str, Any]

_TIMEOUT_SECONDS = 15.0
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_DDG_RESULT_PATTERN = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>'
    r'.*?<a[^>]+class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
    re.DOTALL,
)
_BING_ITEM_PATTERN = re.compile(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(?P<body>.*?)</li>', re.DOTALL)
_BING_LINK_PATTERN = re.compile(
    r'<h2[^>]*>.*?<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?</h2>',
    re.DOTALL,
)
_BING_SNIPPET_PATTERN = re.compile(r"<p[^>]*>(?P<snippet>.*?)</p>", re.DOTALL)


class SearchProviderError(RuntimeError):
    pass


async def web_search(query: str, limit: int = 5) -> SearchResponse:
    """Search the web with configured providers and return normalized results."""
    query = (query or "").strip()
    if not query:
        return []

    limit = max(1, min(int(limit or 5), 10))
    errors: list[str] = []

    for provider in _provider_order():
        try:
            results = await _search_provider(provider, query, limit)
        except SearchProviderError as exc:
            errors.append(f"{provider}: {exc}")
            continue
        except Exception as exc:
            errors.append(f"{provider}: {exc.__class__.__name__}")
            continue

        relevant = _filter_relevant_results(results, query)
        if relevant:
            return relevant[:limit]
        errors.append(f"{provider}: no reliable results")

    return {
        "error": "All configured search providers failed or returned no reliable results.",
        "details": errors,
        "results": [],
    }


def _provider_order() -> list[str]:
    configured = (config.WEB_SEARCH_PROVIDER or "auto").lower()
    if configured and configured != "auto":
        return [configured]

    providers: list[str] = []
    if config.SERPER_API_KEY:
        providers.append("serper")
    if config.TAVILY_API_KEY:
        providers.append("tavily")
    if config.BRAVE_SEARCH_API_KEY:
        providers.append("brave")
    if config.SEARXNG_BASE_URL:
        providers.append("searxng")
    providers.extend(["duckduckgo", "bing"])
    return providers


async def _search_provider(provider: str, query: str, limit: int) -> list[SearchResult]:
    if provider == "serper":
        return await _search_serper(query, limit)
    if provider == "tavily":
        return await _search_tavily(query, limit)
    if provider == "brave":
        return await _search_brave(query, limit)
    if provider == "searxng":
        return await _search_searxng(query, limit)
    if provider == "duckduckgo":
        return await _search_duckduckgo(query, limit)
    if provider == "bing":
        return await _search_bing(query, limit)
    raise SearchProviderError(f"unknown provider `{provider}`")


async def _search_serper(query: str, limit: int) -> list[SearchResult]:
    if not config.SERPER_API_KEY:
        raise SearchProviderError("SERPER_API_KEY is not configured")

    payload = {
        "q": query,
        "num": limit,
        "hl": "zh-cn" if _has_cjk(query) else "en",
        "gl": "cn" if _has_cjk(query) else "us",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "https://google.serper.dev/search",
            json=payload,
            headers={"X-API-KEY": config.SERPER_API_KEY, "User-Agent": _USER_AGENT},
        )
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")
    data = response.json()
    return _normalize_items(data.get("organic", []), title_key="title", url_key="link", snippet_key="snippet")


async def _search_tavily(query: str, limit: int) -> list[SearchResult]:
    if not config.TAVILY_API_KEY:
        raise SearchProviderError("TAVILY_API_KEY is not configured")

    payload = {
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "max_results": limit,
        "search_depth": "basic",
        "include_answer": False,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post("https://api.tavily.com/search", json=payload)
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")
    data = response.json()
    return _normalize_items(data.get("results", []), title_key="title", url_key="url", snippet_key="content")


async def _search_brave(query: str, limit: int) -> list[SearchResult]:
    if not config.BRAVE_SEARCH_API_KEY:
        raise SearchProviderError("BRAVE_SEARCH_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": limit},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
                "User-Agent": _USER_AGENT,
            },
        )
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")
    data = response.json()
    return _normalize_items(data.get("web", {}).get("results", []), title_key="title", url_key="url", snippet_key="description")


async def _search_searxng(query: str, limit: int) -> list[SearchResult]:
    if not config.SEARXNG_BASE_URL:
        raise SearchProviderError("SEARXNG_BASE_URL is not configured")

    base = config.SEARXNG_BASE_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(
            f"{base}/search",
            params={
                "q": query,
                "format": "json",
                "language": "zh-CN" if _has_cjk(query) else "en",
                "categories": "general",
            },
            headers={"User-Agent": _USER_AGENT},
        )
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")
    if "json" not in response.headers.get("content-type", ""):
        raise SearchProviderError("non-JSON response")
    data = response.json()
    return _normalize_items(data.get("results", []), title_key="title", url_key="url", snippet_key="content")


async def _search_duckduckgo(query: str, limit: int) -> list[SearchResult]:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")
    if response.status_code == 202 or _is_duckduckgo_challenge(response.text):
        raise SearchProviderError("DuckDuckGo returned an anti-bot challenge")

    results: list[SearchResult] = []
    for match in _DDG_RESULT_PATTERN.finditer(response.text):
        href = _resolve_duckduckgo_redirect(match.group("href").strip())
        title = _strip_tags(match.group("title"))
        snippet = _strip_tags(match.group("snippet"))
        if href and title:
            results.append(_result(title, href, snippet, "duckduckgo"))
        if len(results) >= limit:
            break
    return results


async def _search_bing(query: str, limit: int) -> list[SearchResult]:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(
            "https://www.bing.com/search",
            params={
                "q": query,
                "mkt": "zh-CN" if _has_cjk(query) else "en-US",
                "setlang": "zh-CN" if _has_cjk(query) else "en-US",
            },
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
    if response.status_code >= 400:
        raise SearchProviderError(f"HTTP {response.status_code}")

    results: list[SearchResult] = []
    for item in _BING_ITEM_PATTERN.finditer(response.text):
        body = item.group("body")
        link = _BING_LINK_PATTERN.search(body)
        if not link:
            continue
        snippet_match = _BING_SNIPPET_PATTERN.search(body)
        title = _strip_tags(link.group("title"))
        url = link.group("href").strip()
        snippet = _strip_tags(snippet_match.group("snippet")) if snippet_match else ""
        if url and title:
            results.append(_result(title, url, snippet, "bing"))
        if len(results) >= limit * 3:
            break
    return results


def _normalize_items(items: list[dict[str, Any]], *, title_key: str, url_key: str, snippet_key: str) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in items:
        title = str(item.get(title_key) or "").strip()
        url = str(item.get(url_key) or "").strip()
        snippet = str(item.get(snippet_key) or "").strip()
        source = str(item.get("source") or item.get("engine") or "").strip()
        if title and url:
            results.append(_result(title, url, snippet, source))
    return results


def _filter_relevant_results(results: list[SearchResult], query: str) -> list[SearchResult]:
    return [result for result in results if _looks_relevant(result, query)]


def _looks_relevant(result: SearchResult, query: str) -> bool:
    haystack = f"{result.get('title', '')} {result.get('snippet', '')} {result.get('url', '')}".lower()
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{3,}", query)]
    if words:
        hits = sum(1 for word in set(words) if word in haystack)
        required = 1 if len(set(words)) <= 2 else 2
        if hits >= required:
            return True
        return False

    cjk_chars = [ch for ch in query if "\u4e00" <= ch <= "\u9fff"]
    if cjk_chars:
        hits = sum(1 for ch in set(cjk_chars) if ch in haystack)
        required = min(2, len(set(cjk_chars)))
        if hits >= required:
            return True
        return False

    return bool(haystack)

def _result(title: str, url: str, snippet: str, source: str) -> SearchResult:
    result = {"title": title[:200], "url": url, "snippet": snippet[:500]}
    if source:
        result["source"] = source
    return result


def _strip_tags(text: str) -> str:
    return unescape(_TAG_PATTERN.sub("", text)).strip()


def _resolve_duckduckgo_redirect(href: str) -> str:
    if href.startswith("//duckduckgo.com/l/?"):
        match = re.search(r"uddg=([^&]+)", href)
        if match:
            return unquote(match.group(1))
    return href


def _is_duckduckgo_challenge(html: str) -> bool:
    lowered = html.lower()
    return "anomaly" in lowered and "challenge" in lowered


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)
