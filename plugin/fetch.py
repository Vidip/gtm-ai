"""Fetch + extract readable text from a single, specific URL.

This backs the custom `fetch_url` tool exposed to Claude in research.py, used
*alongside* Claude's built-in web_search tool for higher-trust verification of
one source Claude already found. The URL comes from model/search output, not
from us, so it is treated as untrusted input: only http(s) is allowed, and the
resolved hostname is checked against loopback/private/link-local ranges and
the cloud metadata address before any request is made - regardless of which
backend below actually performs the fetch.

Two backends:
  - Tavily Extract (preferred, if TAVILY_API_KEY is set): a managed extraction
    API purpose-built for "give me clean text for this URL" - handles JS-heavy
    pages and boilerplate removal better than a local parser, and the fetch
    happens from Tavily's infrastructure rather than ours.
  - requests + BeautifulSoup (fallback, always available): zero extra API key,
    keeps the plugin runnable with only ANTHROPIC_API_KEY set.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

_TIMEOUT_S = 8
_MAX_BYTES = 2_000_000
_USER_AGENT = "OpportunityRadarBot/1.0 (+prototype research tool)"
_BLOCKED_HOST_SUFFIXES = (".local",)
_METADATA_IP = "169.254.169.254"
_MAX_REDIRECTS = 3


def is_safe_url(url: str) -> tuple[bool, str]:
    """Returns (ok, reason). Rejects anything that isn't a plain public http(s) URL."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "unparseable URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"scheme {parsed.scheme!r} not allowed"
    if not parsed.hostname:
        return False, "no hostname"
    if parsed.hostname.lower().endswith(_BLOCKED_HOST_SUFFIXES):
        return False, "blocked host suffix"

    try:
        resolved = socket.gethostbyname(parsed.hostname)
    except socket.gaierror:
        return False, "DNS resolution failed"

    if resolved == _METADATA_IP:
        return False, "cloud metadata address"

    ip = ipaddress.ip_address(resolved)
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return False, f"resolves to non-public address ({resolved})"

    return True, "ok"


def _fetch_via_tavily(url: str, max_chars: int) -> str | None:
    """Returns extracted text, or None to signal 'fall back to requests+bs4'."""
    try:
        from tavily import TavilyClient  # lazy: only needed on this path
    except ImportError:
        return None

    try:
        client = TavilyClient()  # reads TAVILY_API_KEY from the environment
        response = client.extract(urls=[url], extract_depth="basic", format="text")
    except Exception:
        return None  # any SDK/network/auth error -> fall back, don't fail the account

    for result in response.get("results", []):
        if result.get("url") == url or len(response.get("results", [])) == 1:
            content = result.get("raw_content") or ""
            if content:
                return content[:max_chars]

    # Per-URL failure (failed_results) or empty content: fall back to requests+bs4.
    return None


def _fetch_via_requests(url: str, max_chars: int) -> str:
    try:
        # Redirects are followed manually so every hop passes is_safe_url():
        # a public page must not be able to bounce us to loopback/metadata.
        for hop in range(_MAX_REDIRECTS + 1):
            resp = requests.get(
                url,
                timeout=_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
                stream=True,
                allow_redirects=False,
            )
            if not resp.is_redirect:
                break
            location = resp.headers.get("Location")
            resp.close()
            if not location:
                return "[fetch failed: redirect without Location]"
            if hop == _MAX_REDIRECTS:
                return "[fetch failed: too many redirects]"
            url = urljoin(url, location)
            safe, reason = is_safe_url(url)
            if not safe:
                return f"[fetch failed: blocked - redirect to {reason}]"

        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower():
            return f"[fetch failed: unsupported content-type {content_type!r}]"

        raw = resp.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(raw) > _MAX_BYTES:
            raw = raw[:_MAX_BYTES]

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned = "\n".join(lines)

        if not cleaned:
            return "[fetch failed: no extractable text]"

        return cleaned[:max_chars]
    except requests.exceptions.RequestException as exc:
        return f"[fetch failed: {type(exc).__name__}]"


def _tavily_enabled() -> bool:
    """Tavily is used only if a key is set AND TAVILY_ENABLED is not false/0/no/off
    (unset counts as enabled, so existing setups behave as before)."""
    if os.environ.get("TAVILY_ENABLED", "true").strip().lower() in {"false", "0", "no", "off"}:
        return False
    return bool(os.environ.get("TAVILY_API_KEY"))


def fetch_and_extract(url: str, max_chars: int = 6000) -> str:
    """Best-effort fetch + main-text extraction. Never raises: failures come back
    as a short '[fetch failed: ...]' string so the caller's tool-use loop can
    continue and the model can decide what to do next.

    Uses Tavily Extract when TAVILY_API_KEY is set and TAVILY_ENABLED is not false, else falls back to a local
    requests+BeautifulSoup extractor - either way, is_safe_url() runs first.
    """
    safe, reason = is_safe_url(url)
    if not safe:
        return f"[fetch failed: blocked - {reason}]"

    if _tavily_enabled():
        result = _fetch_via_tavily(url, max_chars)
        if result is not None:
            return result
        # Tavily unavailable/failed for this URL - degrade gracefully rather
        # than losing the account's whole research round over one vendor hiccup.

    return _fetch_via_requests(url, max_chars)
