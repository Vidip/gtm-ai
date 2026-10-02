"""Shared research fan-out used by main.py and evals/run_evals.py."""
from __future__ import annotations

import concurrent.futures as cf
from typing import Callable, Optional

from .mock import mock_research_account
from .schema import Account, OpportunityBrief

ResultCallback = Callable[[Account, Optional[OpportunityBrief], Optional[Exception]], None]


def _research_one(account: Account, mock: bool) -> tuple[Account, Optional[OpportunityBrief], Optional[Exception]]:
    try:
        if mock:
            return account, mock_research_account(account), None
        from .research import research_account  # lazy import: no SDK/key needed for --mock

        return account, research_account(account), None
    except Exception as exc:  # noqa: BLE001
        return account, None, exc


def research_all(
    accounts: list[Account],
    *,
    mock: bool,
    workers: int = 4,
    on_result: Optional[ResultCallback] = None,
) -> tuple[list[OpportunityBrief], list[tuple[str, Exception]]]:
    """Research every account; briefs come back in input order, failures as (name, exc)."""
    by_index: dict[int, OpportunityBrief] = {}
    failures: list[tuple[str, Exception]] = []
    with cf.ThreadPoolExecutor(max_workers=1 if mock else workers) as pool:
        futures = {pool.submit(_research_one, acc, mock): i for i, acc in enumerate(accounts)}
        for fut in cf.as_completed(futures):
            account, brief, err = fut.result()
            if brief is not None:
                by_index[futures[fut]] = brief
            else:
                failures.append((account.name, err))
            if on_result is not None:
                on_result(account, brief, err)
    return [by_index[i] for i in sorted(by_index)], failures
