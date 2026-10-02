"""The fetch_url tool executes URLs the model chooses, based on search results
it doesn't fully control - so the SSRF guard is the one piece of this
prototype that genuinely needs a test, not just a manual smoke check.
"""
from plugin.fetch import is_safe_url


def test_rejects_non_http_scheme():
    ok, _ = is_safe_url("file:///etc/passwd")
    assert not ok


def test_rejects_localhost():
    ok, _ = is_safe_url("http://localhost:8080/admin")
    assert not ok


def test_rejects_loopback_ip():
    ok, _ = is_safe_url("http://127.0.0.1/secret")
    assert not ok


def test_rejects_cloud_metadata_ip():
    ok, _ = is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not ok


def test_rejects_private_ip_literal():
    ok, _ = is_safe_url("http://10.0.0.5/internal")
    assert not ok


def test_allows_public_https_url():
    ok, _ = is_safe_url("https://www.reuters.com/business/media-telecom/")
    assert ok
