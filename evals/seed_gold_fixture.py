"""One-off: write the provisional gold top-k fixture from deal stage / deal size.

    python -m evals.seed_gold_fixture [--input data/sample_accounts.xlsx] [--k 5] [--out PATH]
"""
from __future__ import annotations

import argparse
import json

from plugin.loader import load_accounts
from plugin.mock import _STAGE_TIER
from plugin.schema import Account

from .ranking import DEFAULT_GOLD_FIXTURE

NOTE = (
    "Seeded by evals/seed_gold_fixture.py from deal_stage/deal_size_cad (same stage priority as "
    'plugin/mock.py); set status to "human-labeled" when replaced by real GTM judgment.'
)


def seed_sort_key(a: Account) -> tuple:
    return (_STAGE_TIER.get(a.deal_stage, "C"), -(a.deal_size_cad or 0.0), a.name)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="data/sample_accounts.xlsx")
    p.add_argument("--sheet", default="Sample Accounts")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--out", default=str(DEFAULT_GOLD_FIXTURE))
    args = p.parse_args(argv)

    accounts = sorted(load_accounts(args.input, sheet_name=args.sheet), key=seed_sort_key)
    payload = {
        "status": "provisional",
        "note": NOTE,
        "k": args.k,
        "gold_top_k": [a.name for a in accounts[: args.k]],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    print(f"Wrote {args.out}: {payload['gold_top_k']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
