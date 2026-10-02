"""Ranking for the summary table at the front of the PDF."""
from __future__ import annotations

from .schema import OpportunityBrief


def rank_briefs(briefs: list[OpportunityBrief]) -> list[OpportunityBrief]:
    return sorted(briefs, key=lambda b: b.rank_key())
