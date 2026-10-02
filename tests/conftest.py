import pytest


@pytest.fixture(autouse=True)
def _isolate_env_flags(monkeypatch):
    """plugin/__init__ loads .env, so a developer's TAVILY_ENABLED / MAX_FETCH would leak
    into tests. Start every test from the defaults; tests set what they need."""
    monkeypatch.delenv("TAVILY_ENABLED", raising=False)
    monkeypatch.delenv("MAX_FETCH", raising=False)
