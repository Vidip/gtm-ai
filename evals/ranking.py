"""4.4 Ranking quality: precision@k against a gold top-k fixture."""
from __future__ import annotations

import json
from pathlib import Path

from plugin.schema import OpportunityBrief

from .schema import RankingEvalResult

RANKING_PASS_THRESHOLD = 0.6
DEFAULT_GOLD_FIXTURE = Path(__file__).parent / "fixtures" / "gold_ranking.json"


def evaluate_ranking(
    ranked_briefs: list[OpportunityBrief], *, fixture_path: str | Path = DEFAULT_GOLD_FIXTURE
) -> RankingEvalResult:
    path = Path(fixture_path)
    if not path.exists():
        return RankingEvalResult(status="skip", k=0, detail=f"gold fixture not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    k = int(data["k"])
    gold = list(data["gold_top_k"])
    produced = [b.account for b in ranked_briefs[:k]]
    precision = len(set(gold) & set(produced)) / k
    return RankingEvalResult(
        status="pass" if precision >= RANKING_PASS_THRESHOLD else "fail",
        k=k,
        precision_at_k=precision,
        gold_top_k=gold,
        produced_top_k=produced,
    )
