from evals.consistency import consistency_skipped_summary, evaluate_consistency
from plugin.schema import Account, OpportunityBrief


def _acc(n="Acme"):
    return Account(name=n, industry="i", deal_stage="Proposal")


def _brief(tier="A", urgency="High", summary="s"):
    return OpportunityBrief(account="Acme", industry="i", tier=tier, urgency=urgency, signal_summary=summary,
                            why_now="w", recommended_action="r")


def test_tier_difference_fails():
    seq = iter([_brief("A"), _brief("B")])
    r = evaluate_consistency([_acc()], researcher=lambda a: next(seq)).results[0]
    assert r.status == "fail" and "tier" in r.detail and "'A'" in r.detail and "'B'" in r.detail


def test_same_tier_urgency_passes_despite_different_signal():
    seq = iter([_brief(summary="one thing"), _brief(summary="totally other")])
    r = evaluate_consistency([_acc()], researcher=lambda a: next(seq)).results[0]
    assert r.status == "pass" and "signal_similarity=" in r.detail


def test_called_runs_times_per_account():
    calls = []
    evaluate_consistency([_acc("a"), _acc("b")], runs=3, researcher=lambda a: calls.append(a.name) or _brief())
    assert calls.count("a") == 3 and calls.count("b") == 3


def test_researcher_exception_skips():
    def boom(a):
        raise RuntimeError("x")

    assert evaluate_consistency([_acc()], researcher=boom).results[0].status == "skip"


def test_skipped_summary():
    s = consistency_skipped_summary("r")
    assert s.total == 1 and s.skipped == 1 and s.results[0].account == "*"
