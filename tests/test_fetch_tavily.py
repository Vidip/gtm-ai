"""Tavily is the preferred extraction backend when TAVILY_API_KEY is set, with
a fall back to requests+BeautifulSoup if Tavily errors or isn't configured.
These tests mock the SDK/network boundary so they run with no real key.
"""
from unittest.mock import patch

from plugin import fetch


def test_uses_tavily_when_key_present(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key-for-tests")

    with patch("plugin.fetch._fetch_via_tavily", return_value="Example Corp launches X.") as mocked:
        result = fetch.fetch_and_extract("https://example.com/news")

    mocked.assert_called_once()
    assert result == "Example Corp launches X."


def test_falls_back_to_requests_when_tavily_sdk_missing(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key-for-tests")

    with patch("plugin.fetch._fetch_via_tavily", return_value=None):
        with patch("plugin.fetch._fetch_via_requests", return_value="fallback text") as mocked_fallback:
            result = fetch.fetch_and_extract("https://example.com/news")

    mocked_fallback.assert_called_once()
    assert result == "fallback text"


def test_skips_tavily_entirely_when_no_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    with patch("plugin.fetch._fetch_via_tavily") as mocked_tavily:
        with patch("plugin.fetch._fetch_via_requests", return_value="local text") as mocked_fallback:
            result = fetch.fetch_and_extract("https://example.com/news")

    mocked_tavily.assert_not_called()
    mocked_fallback.assert_called_once()
    assert result == "local text"


def test_blocked_url_never_reaches_either_backend(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key-for-tests")

    with patch("plugin.fetch._fetch_via_tavily") as mocked_tavily:
        with patch("plugin.fetch._fetch_via_requests") as mocked_fallback:
            result = fetch.fetch_and_extract("http://127.0.0.1/admin")

    mocked_tavily.assert_not_called()
    mocked_fallback.assert_not_called()
    assert "blocked" in result


def test_tavily_enabled_false_skips_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key-for-tests")
    monkeypatch.setenv("TAVILY_ENABLED", "false")
    from plugin import fetch

    assert fetch._tavily_enabled() is False
    monkeypatch.setenv("TAVILY_ENABLED", "true")
    assert fetch._tavily_enabled() is True
    monkeypatch.delenv("TAVILY_ENABLED")
    assert fetch._tavily_enabled() is True


def test_tavily_per_url_failure_returns_none_so_fallback_runs():
    fake_client = type("C", (), {"extract": lambda self, **kw: {"results": [], "failed_results": [{"url": "u", "error": "boom"}]}})()
    with patch("tavily.TavilyClient", return_value=fake_client):
        assert fetch._fetch_via_tavily("https://example.com/news", 1000) is None
