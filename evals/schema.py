"""Result models for the eval suite."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

EvalStatus = Literal["pass", "fail", "skip"]


class CheckResult(BaseModel):
    check: str
    account: str  # account name, or "*" for a whole-category skip
    status: EvalStatus
    detail: str = ""


class EvalSummary(BaseModel):
    name: str
    total: int
    passed: int
    failed: int
    skipped: int
    score: float
    results: list[CheckResult] = Field(default_factory=list)

    @classmethod
    def from_results(cls, name: str, results: list[CheckResult]) -> "EvalSummary":
        passed = sum(r.status == "pass" for r in results)
        failed = sum(r.status == "fail" for r in results)
        skipped = sum(r.status == "skip" for r in results)
        judged = len(results) - skipped
        return cls(
            name=name,
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            score=passed / judged if judged else 0.0,
            results=results,
        )


class RankingEvalResult(BaseModel):
    name: Literal["ranking"] = "ranking"
    status: EvalStatus
    k: int
    precision_at_k: Optional[float] = None
    gold_top_k: list[str] = Field(default_factory=list)
    produced_top_k: list[str] = Field(default_factory=list)
    detail: str = ""


class ResearchFailure(BaseModel):
    account: str
    error: str


class AggregateEvalReport(BaseModel):
    generated_at: str
    data_mode: Literal["live", "mock"]
    account_count: int
    research_failures: list[ResearchFailure] = Field(default_factory=list)
    structural: EvalSummary
    leakage: EvalSummary
    citation: EvalSummary
    ranking: RankingEvalResult
    consistency: EvalSummary
    overall_pass: bool
