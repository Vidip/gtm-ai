"""Deterministic, offline stand-in for research_account().

No network, no API key. Lets the whole pipeline (load -> rank -> render) be
exercised and reviewed without spending on live web search. Never claims a
real-world signal - every field is clearly derived from the synthetic sheet.
"""
from __future__ import annotations

from .schema import Account, OpportunityBrief

_STAGE_TIER = {
    "Negotiation": "A",
    "Proposal": "A",
    "Qualified": "B",
    "Discovery": "B",
    "Prospecting": "C",
    "Closed Lost": "C",
}
_STAGE_URGENCY = {
    "Negotiation": "High",
    "Proposal": "High",
    "Qualified": "Medium",
    "Discovery": "Medium",
    "Prospecting": "Low",
    "Closed Lost": "Medium",  # re-engagement window, not truly cold
}


def mock_research_account(account: Account) -> OpportunityBrief:
    tier = _STAGE_TIER.get(account.deal_stage, "C")
    urgency = _STAGE_URGENCY.get(account.deal_stage, "Low")

    if account.market_signal_hint:
        signal_summary = f"[MOCK] {account.market_signal_hint}"
    else:
        signal_summary = (
            f"[MOCK] No synthetic signal on file; deal stage is '{account.deal_stage}' "
            "with no recorded activity."
        )

    why_now = (
        f"[MOCK] Deal stage '{account.deal_stage}'"
        + (f" last touched {account.last_activity}" if account.last_activity else " with no logged activity")
        + " implies this tier/urgency."
    )

    if account.rep_notes:
        recommended_action = f"[MOCK] Follow up on: {account.rep_notes}"
    else:
        recommended_action = "[MOCK] No rep notes on file; recommend a discovery touch this week."

    return OpportunityBrief(
        account=account.name,
        industry=account.industry,
        tier=tier,
        urgency=urgency,
        signal_summary=signal_summary,
        why_now=why_now,
        recommended_action=recommended_action,
        warm_path=f"[MOCK] {account.relationship_context}" if account.relationship_context else None,
        sources=[],
        confidence="Low",
        data_mode="mock",
    )
