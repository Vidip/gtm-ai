"""4.1 Structural checks on briefs."""
from __future__ import annotations

from urllib.parse import urlparse

from plugin.schema import OpportunityBrief

from .schema import CheckResult, EvalSummary

_REQUIRED = ("account", "industry", "signal_summary", "why_now", "recommended_action")


def _valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def evaluate_structural(briefs: list[OpportunityBrief]) -> EvalSummary:
    results: list[CheckResult] = []
    for b in briefs:
        empty = [f for f in _REQUIRED if not (getattr(b, f) or "").strip()]
        results.append(
            CheckResult(
                check="structural.required_fields",
                account=b.account,
                status="fail" if empty else "pass",
                detail=f"empty fields: {empty}" if empty else "",
            )
        )
        bad = [s.url for s in b.sources if not _valid_url(s.url)]
        results.append(
            CheckResult(
                check="structural.source_urls",
                account=b.account,
                status="fail" if bad else "pass",
                detail=f"malformed urls: {bad}" if bad else "",
            )
        )
        conf_bad = b.confidence == "High" and not b.sources
        results.append(
            CheckResult(
                check="structural.confidence_vs_sources",
                account=b.account,
                status="fail" if conf_bad else "pass",
                detail="confidence High with zero sources" if conf_bad else "",
            )
        )
    return EvalSummary.from_results("structural", results)
