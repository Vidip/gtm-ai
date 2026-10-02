import subprocess
import sys

from plugin.loader import load_accounts
from plugin.orchestrate import research_all


def test_research_all_input_order_no_failures():
    accounts = load_accounts("data/sample_accounts.xlsx")
    briefs, failures = research_all(accounts, mock=True)
    assert [b.account for b in briefs] == [a.name for a in accounts]
    assert failures == []


def test_on_result_called_once_per_account():
    accounts = load_accounts("data/sample_accounts.xlsx")
    seen = []
    research_all(accounts, mock=True, on_result=lambda a, b, e: seen.append(a.name))
    assert sorted(seen) == sorted(a.name for a in accounts)


def test_failure_is_collected_not_raised(monkeypatch):
    import plugin.orchestrate as orch

    accounts = load_accounts("data/sample_accounts.xlsx")

    def boom(acc):
        raise RuntimeError("nope")

    monkeypatch.setattr(orch, "mock_research_account", boom)
    briefs, failures = research_all(accounts, mock=True)
    assert briefs == []
    assert len(failures) == len(accounts)


def test_main_mock_cli_still_works(tmp_path):
    accounts = load_accounts("data/sample_accounts.xlsx")
    proc = subprocess.run(
        [sys.executable, "main.py", "--mock", "--output", str(tmp_path / "b.pdf")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    for a in accounts:
        assert f"  ok    {a.name}" in proc.stdout
