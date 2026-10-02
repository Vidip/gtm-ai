#!/usr/bin/env python3
"""Media-Opportunity Radar
=========================

Reads the "Sample Accounts" sheet, produces one rep-ready opportunity brief
per account (grounded in real web signals via Claude's web_search tool,
fused with the synthetic CRM context), ranks accounts by tier/urgency, and
renders everything into a single PDF.

Usage
-----
    python main.py --input data/sample_accounts.xlsx --output out/briefs.pdf
    python main.py --mock                      # no API key needed, offline demo
    python main.py --limit 3 --workers 3        # partial run, parallel research
"""
from __future__ import annotations

import argparse
import sys
import time

from plugin.loader import load_accounts
from plugin.orchestrate import research_all
from plugin.rank import rank_briefs
from plugin.render_pdf import render_pdf
from plugin.schema import Account, OpportunityBrief


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/sample_accounts.xlsx", help="Path to the accounts .xlsx or .csv")
    p.add_argument("--sheet", default="Sample Accounts", help="Sheet name to read (.xlsx only)")
    p.add_argument("--output", default="out/briefs.pdf", help="Path to write the PDF")
    p.add_argument("--limit", type=int, default=None, help="Only process the first N accounts")
    p.add_argument("--workers", type=int, default=4, help="Parallel research calls (live mode only)")
    p.add_argument("--mock", action="store_true", help="Skip the API entirely; use deterministic offline stand-ins")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    accounts = load_accounts(args.input, sheet_name=args.sheet)
    if args.limit:
        accounts = accounts[: args.limit]
    print(f"Loaded {len(accounts)} accounts from {args.input!r} (mode: {'mock' if args.mock else 'live'})")

    def _print_result(account: Account, brief: OpportunityBrief | None, err: Exception | None) -> None:
        if brief is not None:
            print(f"  ok    {account.name}")
        else:
            print(f"  FAILED {account.name}: {err}", file=sys.stderr)

    start = time.time()
    briefs, failures = research_all(accounts, mock=args.mock, workers=args.workers, on_result=_print_result)

    if not briefs:
        print("No briefs produced; nothing to render.", file=sys.stderr)
        return 1

    ranked = rank_briefs(briefs)
    render_pdf(ranked, args.output)

    elapsed = time.time() - start
    print(f"\nWrote {len(ranked)} briefs to {args.output} in {elapsed:.1f}s")
    if failures:
        print(f"{len(failures)} account(s) failed and were omitted: {[n for n, _ in failures]}", file=sys.stderr)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
