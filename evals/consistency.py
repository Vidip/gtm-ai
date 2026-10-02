"""4.5 Run-to-run consistency of tier/urgency (signal similarity is informational)."""
from __future__ import annotations

from difflib import SequenceMatcher
from itertools import combinations
from typing import Callable, Optional

from plugin.schema import Account, OpportunityBrief

from .schema import CheckResult, EvalSummary

CHECK = "consistency.agreement"


def consistency_skipped_summary(reason: str) -> EvalSummary:
    return EvalSummary.from_results(
        "consistency", [CheckResult(check=CHECK, account="*", status="skip", detail=reason)]
    )


def evaluate_consistency(
    accounts: list[Account],
    *,
    runs: int = 2,
    researcher: Optional[Callable[[Account], OpportunityBrief]] = None,
) -> EvalSummary:
    if researcher is None:
        from plugin.research import research_account  # lazy: needs SDK/key

        researcher = research_account

    results: list[CheckResult] = []
    for acc in accounts:
        try:
            briefs = [researcher(acc) for _ in range(runs)]
        except Exception as exc:  # noqa: BLE001
            results.append(CheckResult(check=CHECK, account=acc.name, status="skip", detail=f"researcher error: {exc}"))
            continue
        diffs = []
        for field in ("tier", "urgency"):
            vals = sorted({getattr(b, field) for b in briefs})
            if len(vals) > 1:
                diffs.append(f"{field} differs: {vals}")
        sims = [
            SequenceMatcher(None, x.signal_summary, y.signal_summary).ratio()
            for x, y in combinations(briefs, 2)
        ]
        sim = min(sims) if sims else 1.0
        detail = "; ".join(diffs + [f"signal_similarity={sim:.3f}"])
        results.append(
            CheckResult(check=CHECK, account=acc.name, status="fail" if diffs else "pass", detail=detail)
        )
    return EvalSummary.from_results("consistency", results)
