"""4.6 Aggregate report: build, print, write CSV."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .schema import AggregateEvalReport, EvalSummary, RankingEvalResult, ResearchFailure


def build_report(
    *,
    data_mode: str,
    account_count: int,
    structural: EvalSummary,
    leakage: EvalSummary,
    citation: EvalSummary,
    ranking: RankingEvalResult,
    consistency: EvalSummary,
    research_failures: Sequence[ResearchFailure] = (),
) -> AggregateEvalReport:
    failures = list(research_failures)
    overall = (
        structural.failed == 0
        and leakage.failed == 0
        and citation.failed == 0
        and consistency.failed == 0
        and ranking.status != "fail"
        and not failures
    )
    return AggregateEvalReport(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        data_mode=data_mode,
        account_count=account_count,
        research_failures=failures,
        structural=structural,
        leakage=leakage,
        citation=citation,
        ranking=ranking,
        consistency=consistency,
        overall_pass=overall,
    )


def print_report(report: AggregateEvalReport) -> None:
    for s in (report.structural, report.leakage, report.citation, report.consistency):
        print(f"{s.name}: {s.passed}/{s.total - s.skipped} passed ({s.skipped} skipped), score={s.score:.2f}")
    r = report.ranking
    if r.status == "skip":
        print(f"ranking: skipped ({r.detail})")
    else:
        print(f"ranking: precision@{r.k}={r.precision_at_k:.2f} ({r.status})")
    if report.research_failures:
        print(f"research failures: {len(report.research_failures)}")
    print("OVERALL: PASS" if report.overall_pass else "OVERALL: FAIL")


CSV_COLUMNS = ["generated_at", "data_mode", "category", "account", "check", "status", "detail"]


def report_rows(report: AggregateEvalReport) -> list[dict]:
    """Flatten the report to one row per check result, then one `_summary` row per
    category, the ranking row, research failures and a final overall row."""

    def row(category, account, check, status, detail=""):
        return {
            "generated_at": report.generated_at,
            "data_mode": report.data_mode,
            "category": category,
            "account": account,
            "check": check,
            "status": status,
            "detail": detail,
        }

    rows = []
    summaries = (report.structural, report.leakage, report.citation, report.consistency)
    for s in summaries:
        rows += [row(s.name, r.account, r.check, r.status, r.detail) for r in s.results]
    r = report.ranking
    rows.append(
        row(
            "ranking",
            "*",
            "ranking.precision_at_k",
            r.status,
            f"k={r.k}; precision_at_k={r.precision_at_k}; gold={' | '.join(r.gold_top_k)}; "
            f"produced={' | '.join(r.produced_top_k)}; {r.detail}".rstrip("; ").strip(),
        )
    )
    rows += [row("research", f.account, "research.failed", "fail", f.error) for f in report.research_failures]
    for s in summaries:
        rows.append(
            row(
                s.name,
                "*",
                "_summary",
                "",
                f"total={s.total}; passed={s.passed}; failed={s.failed}; skipped={s.skipped}; score={s.score:.2f}",
            )
        )
    rows.append(
        row("overall", "*", "overall_pass", "pass" if report.overall_pass else "fail", f"account_count={report.account_count}")
    )
    return rows


def write_report_csv(report: AggregateEvalReport, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(report_rows(report))
