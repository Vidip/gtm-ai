"""MAX_FETCH is enforced in code, per account. A fake Claude client and fake fetcher: no network."""
from types import SimpleNamespace
from unittest.mock import patch

from plugin import research
from plugin.schema import Account


def _account():
    return Account(name="Acme", industry="CPG", deal_stage="Discovery")


def _fetch_block(i):
    return SimpleNamespace(type="tool_use", name="fetch_url", id=f"t{i}", input={"url": f"https://e.com/{i}"})


class FakeClient:
    def __init__(self, n_urls):
        self.n = n_urls
        self.calls = 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        self.last = kw
        if self.calls == 1:
            return SimpleNamespace(content=[_fetch_block(i) for i in range(self.n)])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")])


def test_cap_stops_extra_fetches(monkeypatch):
    monkeypatch.setenv("MAX_FETCH", "2")
    with patch("plugin.research.fetch_and_extract", return_value="page") as f:
        research._run_tool_loop(FakeClient(5), _account())
    assert f.call_count == 2


def test_no_cap_when_unset(monkeypatch):
    monkeypatch.delenv("MAX_FETCH", raising=False)
    with patch("plugin.research.fetch_and_extract", return_value="page") as f:
        research._run_tool_loop(FakeClient(5), _account())
    assert f.call_count == 5


def test_blank_or_invalid_means_no_cap(monkeypatch):
    for v in ("", "abc", "-3"):
        monkeypatch.setenv("MAX_FETCH", v)
        assert research._max_fetch() is None
    monkeypatch.setenv("MAX_FETCH", "0")
    assert research._max_fetch() == 0


def test_prompt_and_tool_reflect_cap():
    assert "at most 10" in research._system_prompt(10)
    assert "as many times as you need" in research._system_prompt(None)
    assert "at most 10" in research._fetch_tool(10)["description"]


def test_prompt_has_warm_path_search_and_no_unfilled_placeholders():
    p = research._system_prompt(None)
    assert "Warm path" in p and "{fetch_rule}" not in p
    assert "{limit}" not in research._fetch_tool(None)["description"]
