"""Redirects must be re-checked hop by hop so a public page can't bounce the
fetcher to a private/metadata address. No network: requests.get and DNS are faked."""
from unittest.mock import MagicMock, patch

from plugin import fetch


def _resp(status=200, location=None, html="<html><body>hello</body></html>"):
    r = MagicMock()
    r.is_redirect = location is not None
    r.headers = {"Location": location} if location else {"Content-Type": "text/html"}
    r.raw.read.return_value = html.encode()
    return r


def _safe(url):
    return ("127.0.0.1" not in url and "169.254" not in url, "non-public address")


def test_redirect_to_loopback_is_blocked():
    with patch("plugin.fetch.is_safe_url", side_effect=_safe):
        with patch("plugin.fetch.requests.get", side_effect=[_resp(location="http://127.0.0.1/admin")]) as get:
            result = fetch._fetch_via_requests("https://public.example/page", 1000)
    assert result.startswith("[fetch failed: blocked")
    assert get.call_count == 1  # the private URL was never requested


def test_redirect_to_metadata_is_blocked():
    with patch("plugin.fetch.is_safe_url", side_effect=_safe):
        with patch("plugin.fetch.requests.get", side_effect=[_resp(location="http://169.254.169.254/latest")]):
            result = fetch._fetch_via_requests("https://public.example/page", 1000)
    assert result.startswith("[fetch failed: blocked")


def test_safe_redirect_is_followed():
    with patch("plugin.fetch.is_safe_url", side_effect=_safe):
        with patch("plugin.fetch.requests.get", side_effect=[_resp(location="/new"), _resp()]) as get:
            result = fetch._fetch_via_requests("https://public.example/old", 1000)
    assert result == "hello"
    assert get.call_args_list[1].args[0] == "https://public.example/new"


def test_redirect_loop_stops():
    with patch("plugin.fetch.is_safe_url", side_effect=_safe):
        with patch("plugin.fetch.requests.get", side_effect=lambda *a, **k: _resp(location="/again")):
            result = fetch._fetch_via_requests("https://public.example/a", 1000)
    assert result == "[fetch failed: too many redirects]"
