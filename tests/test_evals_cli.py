import glob
import csv
import sys

from evals.run_evals import main


def _purge(monkeypatch):
    for mod in ("plugin.research", "anthropic"):
        monkeypatch.delitem(sys.modules, mod, raising=False)


def test_mock_cli_exit_zero_and_no_sdk_import(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _purge(monkeypatch)
    assert main(["--mock", "--report-out", str(tmp_path)]) == 0
    assert "plugin.research" not in sys.modules
    assert "anthropic" not in sys.modules


def test_mock_cli_report_contents(tmp_path):
    assert main(["--mock", "--report-out", str(tmp_path)]) == 0
    stamped = glob.glob(str(tmp_path / "report_*.csv"))
    assert len(stamped) == 1 and (tmp_path / "latest.csv").exists()
    for path in (stamped[0], str(tmp_path / "latest.csv")):
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        assert {r["data_mode"] for r in rows} == {"mock"}
    by = lambda cat: [r for r in rows if r["category"] == cat and r["check"] != "_summary"]  # noqa: E731
    assert not [r for r in by("structural") if r["status"] == "fail"]
    (ranking,) = by("ranking")
    assert ranking["status"] == "pass"
    for key in ("leakage", "citation"):
        assert {r["status"] for r in by(key)} == {"skip"}
    assert [r["status"] for r in by("consistency")] == ["skip"]
    overall = by("overall")[0]
    assert overall["status"] == "pass" and overall["detail"] == "account_count=12"


def test_limit(tmp_path):
    main(["--mock", "--limit", "3", "--report-out", str(tmp_path)])
    with open(tmp_path / "latest.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r for r in rows if r["category"] == "overall"][0]["detail"] == "account_count=3"
