"""Data contracts shared across the pipeline."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

Tier = Literal["A", "B", "C"]
Urgency = Literal["High", "Medium", "Low"]


class Account(BaseModel):
    """One row from the 'Sample Accounts' sheet."""

    name: str
    industry: str
    deal_stage: str
    deal_size_cad: Optional[float] = None
    last_activity: Optional[str] = None
    rep_notes: Optional[str] = None
    market_signal_hint: Optional[str] = None
    relationship_context: Optional[str] = None


class Source(BaseModel):
    title: str
    url: str


class OpportunityBrief(BaseModel):
    """One rep-ready card. This is the JSON shape the model must return."""

    account: str
    industry: str
    tier: Tier
    urgency: Urgency
    signal_summary: str = Field(..., description="1-2 sentences: what's happening at this account right now")
    why_now: str = Field(..., description="Why this matters for an outbound/renewal push this quarter")
    recommended_action: str = Field(..., description="One concrete next step for the rep")
    warm_path: Optional[str] = Field(None, description="Best relationship route in, if any")
    sources: list[Source] = Field(default_factory=list)
    confidence: Literal["High", "Medium", "Low"] = "Medium"
    data_mode: Literal["live", "mock"] = "live"

    def rank_key(self) -> tuple:
        tier_rank = {"A": 0, "B": 1, "C": 2}[self.tier]
        urgency_rank = {"High": 0, "Medium": 1, "Low": 2}[self.urgency]
        return (tier_rank, urgency_rank)
