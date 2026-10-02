"""Run the eval suite.

    python -m evals.run_evals --mock
    python -m evals.run_evals --input data/sample_accounts.xlsx
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from plugin.loader import load_accounts
from plugin.orchestrate import research_all
from plugin.rank import rank_briefs
from plugin.schema import Account, OpportunityBrief

from .consistency import consistency_skipped_summary, evaluate_consistency
from .groundedness import evaluate_citations, evaluate_leakage
from .ranking import DEFAULT_GOLD_FIXTURE, evaluate_ranking
from .report import build_report, print_report, write_report_csv
from .schema import ResearchFailure
from .structural import evaluate_structural


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/sample_accounts.xlsx")
    p.add_argument("--sheet", default="Sample Accounts")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--mock", action="store_true")
    p.add_argument("--consistency-runs", type=int, default=2)
    p.add_argument("--consistency-sample", type=int, default=3)
    p.add_argument("--gold-fixture", default=str(DEFAULT_GOLD_FIXTURE))
    p.add_argument("--max-citations-per-brief", type=int, default=3)
    p.add_argument("--report-out", default="evals/out")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    accounts = load_accounts(args.input, sheet_name=args.sheet)
    if args.limit:
        accounts = accounts[: args.limit]
    mode = "mock" if args.mock else "live"
    print(f"Loaded {len(accounts)} accounts from {args.input!r} (mode: {mode})")

    def _print_result(account: Account, brief: OpportunityBrief | None, err: Exception | None) -> None:
        if brief is not None:
            print(f"  ok    {account.name}")
        else:
            print(f"  FAILED {account.name}: {err}", file=sys.stderr)

    briefs, failures = research_all(accounts, mock=args.mock, workers=args.workers, on_result=_print_result)
    if not briefs:
        print("No briefs produced; nothing to evaluate.", file=sys.stderr)
        return 1

    ranked = rank_briefs(briefs)
    structural = evaluate_structural(briefs)
    leakage = evaluate_leakage(accounts, briefs)
    citation = evaluate_citations(briefs, max_sources_per_brief=args.max_citations_per_brief)
    ranking = evaluate_ranking(ranked, fixture_path=args.gold_fixture)
    if args.mock:
        consistency = consistency_skipped_summary("mock mode is deterministic by design, see plugin/mock.py")
    else:
        consistency = evaluate_consistency(
            accounts[: args.consistency_sample], runs=args.consistency_runs
        )

    report = build_report(
        data_mode=mode,
        account_count=len(accounts),
        structural=structural,
        leakage=leakage,
        citation=citation,
        ranking=ranking,
        consistency=consistency,
        research_failures=[ResearchFailure(account=n, error=str(e)) for n, e in failures],
    )
    print()
    print_report(report)

    out = Path(args.report_out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    write_report_csv(report, out / f"report_{stamp}.csv")
    write_report_csv(report, out / "latest.csv")
    return 0 if report.overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
