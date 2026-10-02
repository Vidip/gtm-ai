"""4.2 leakage check and 4.3 LLM-judge citation check."""
from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Callable, Optional

from plugin.fetch import fetch_and_extract
from plugin.schema import Account, OpportunityBrief

from .schema import CheckResult, EvalSummary

LEAKAGE_RATIO_THRESHOLD = 0.9

JUDGE_SYSTEM_PROMPT = (
    "You are a strict fact-checking judge. You are given a CLAIM and the text of a web page that "
    "is cited as its source. Decide whether the source text supports the claim. Judge only on what "
    "the source text says; do not use outside knowledge. Reply with JSON only, no prose: "
    '{"supports_claim": true|false, "reasoning": "<one or two sentences>"}'
)


def _norm(s: str) -> str:
    return " ".join(s.casefold().split())


def evaluate_leakage(accounts: list[Account], briefs: list[OpportunityBrief]) -> EvalSummary:
    by_name = {a.name: a for a in accounts}
    results: list[CheckResult] = []
    for b in briefs:
        check = "groundedness.leakage"
        acc = by_name.get(b.account)
        if acc is None:
            results.append(CheckResult(check=check, account=b.account, status="skip", detail="no matching account"))
            continue
        if acc.market_signal_hint is None or b.data_mode == "mock":
            reason = "mock brief" if b.data_mode == "mock" else "no market_signal_hint"
            results.append(CheckResult(check=check, account=b.account, status="skip", detail=reason))
            continue
        ratio = SequenceMatcher(None, _norm(acc.market_signal_hint), _norm(b.signal_summary)).ratio()
        leaked = ratio > LEAKAGE_RATIO_THRESHOLD
        results.append(
            CheckResult(
                check=check,
                account=b.account,
                status="fail" if leaked else "pass",
                detail=f"ratio={ratio:.3f}",
            )
        )
    return EvalSummary.from_results("leakage", results)


def _default_judge(claim: str, source_text: str, *, max_retries: int = 1, sleep_s: float = 1.5) -> dict:
    # Lazy imports: --mock never needs the SDK or plugin.research.
    import anthropic

    from plugin.research import MODEL, _extract_json

    client = anthropic.Anthropic()
    prompt = f"CLAIM:\n{claim}\n\nSOURCE TEXT:\n{source_text}"
    for attempt in range(max_retries + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=500,
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(getattr(blk, "text", "") for blk in resp.content)
            return _extract_json(text)
        except Exception:  # noqa: BLE001
            if attempt >= max_retries:
                raise
            time.sleep(sleep_s)
    raise RuntimeError("unreachable")


def evaluate_citations(
    briefs: list[OpportunityBrief],
    *,
    fetcher: Callable[[str], str] = fetch_and_extract,
    judge: Optional[Callable[[str, str], dict]] = None,
    max_sources_per_brief: int = 3,
) -> EvalSummary:
    check = "groundedness.citation"
    judge_fn = judge if judge is not None else _default_judge
    results: list[CheckResult] = []
    for b in briefs:
        if b.data_mode == "mock" or not b.sources:
            reason = "mock brief" if b.data_mode == "mock" else "no sources"
            results.append(CheckResult(check=check, account=b.account, status="skip", detail=reason))
            continue
        for src in b.sources[:max_sources_per_brief]:
            text = fetcher(src.url)
            if text.startswith("[fetch failed"):
                results.append(
                    CheckResult(check=check, account=b.account, status="skip", detail=f"{src.url}: {text}")
                )
                continue
            try:
                verdict = judge_fn(b.signal_summary, text)
                supports = verdict.get("supports_claim") if isinstance(verdict, dict) else None
                if not isinstance(supports, bool):
                    raise ValueError(f"judge returned no boolean supports_claim: {verdict!r}")
            except Exception as exc:  # noqa: BLE001
                results.append(
                    CheckResult(check=check, account=b.account, status="skip", detail=f"{src.url}: judge error: {exc}")
                )
                continue
            if supports:
                results.append(CheckResult(check=check, account=b.account, status="pass", detail=src.url))
            else:
                reasoning = verdict.get("reasoning", "")
                results.append(
                    CheckResult(check=check, account=b.account, status="fail", detail=f"{src.url}: {reasoning}")
                )
    return EvalSummary.from_results("citation", results)
