from src.tools import web_search
from src.utils import config


def test_provider_order_prefers_configured_api_keys(monkeypatch):
    monkeypatch.setattr(config, "WEB_SEARCH_PROVIDER", "auto")
    monkeypatch.setattr(config, "SERPER_API_KEY", "serper-key")
    monkeypatch.setattr(config, "TAVILY_API_KEY", "")
    monkeypatch.setattr(config, "BRAVE_SEARCH_API_KEY", "brave-key")
    monkeypatch.setattr(config, "SEARXNG_BASE_URL", "")

    assert web_search._provider_order()[:2] == ["serper", "brave"]


def test_provider_order_honors_explicit_provider(monkeypatch):
    monkeypatch.setattr(config, "WEB_SEARCH_PROVIDER", "tavily")

    assert web_search._provider_order() == ["tavily"]


def test_filter_relevant_results_rejects_unrelated_bing_noise():
    results = [
        {"title": "Amazon.com: Books", "url": "https://www.amazon.com/books", "snippet": "Online shopping"},
        {"title": "河北周末徒步路线推荐", "url": "https://example.com/hebei", "snippet": "适合周末出行"},
    ]

    assert web_search._filter_relevant_results(results, "河北徒步路线") == [results[1]]


def test_normalize_serper_items():
    results = web_search._normalize_items(
        [{"title": "OpenAI", "link": "https://openai.com", "snippet": "AI research"}],
        title_key="title",
        url_key="link",
        snippet_key="snippet",
    )

    assert results == [{"title": "OpenAI", "url": "https://openai.com", "snippet": "AI research"}]


def test_duckduckgo_challenge_detection():
    html = "<html><body>anomaly challenge</body></html>"

    assert web_search._is_duckduckgo_challenge(html) is True
