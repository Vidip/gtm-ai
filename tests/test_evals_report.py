import csv

from evals.report import CSV_COLUMNS, build_report, print_report, write_report_csv
from evals.schema import CheckResult, EvalSummary, RankingEvalResult, ResearchFailure


def _s(name, status="pass"):
    return EvalSummary.from_results(name, [CheckResult(check="c", account="a", status=status, detail="d")])


def _report(structural=None, ranking=None, failures=()):
    return build_report(
        data_mode="mock", account_count=2,
        structural=structural or _s("structural"), leakage=_s("leakage"), citation=_s("citation"),
        ranking=ranking or RankingEvalResult(status="pass", k=5, precision_at_k=1.0),
        consistency=_s("consistency"), research_failures=list(failures),
    )


def test_all_pass(capsys):
    r = _report()
    print_report(r)
    assert r.overall_pass and "OVERALL: PASS" in capsys.readouterr().out


def test_structural_failure_fails(capsys):
    r = _report(structural=_s("structural", "fail"))
    print_report(r)
    assert not r.overall_pass and "OVERALL: FAIL" in capsys.readouterr().out


def test_ranking_skip_still_passes():
    assert _report(ranking=RankingEvalResult(status="skip", k=0, detail="missing")).overall_pass


def test_research_failures_fail(capsys):
    r = _report(failures=[ResearchFailure(account="a", error="e")])
    print_report(r)
    assert not r.overall_pass and "research failures: 1" in capsys.readouterr().out


def test_csv_round_trip(tmp_path):
    r = _report(failures=[ResearchFailure(account="a", error="e")])
    p = tmp_path / "sub" / "r.csv"
    write_report_csv(r, p)
    with open(p, newline="") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == CSV_COLUMNS
    assert {r["data_mode"] for r in rows} == {"mock"}
    assert [r["detail"] for r in rows if r["check"] == "research.failed"] == ["e"]
    assert rows[-1]["check"] == "overall_pass" and rows[-1]["status"] == "fail"
    assert any(r["check"] == "_summary" and "score=" in r["detail"] for r in rows)


def test_all_skipped_score_zero():
    s = _s("x", "skip")
    assert s.score == 0.0 and s.skipped == 1
