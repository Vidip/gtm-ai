import json

from evals.ranking import DEFAULT_GOLD_FIXTURE, evaluate_ranking
from evals.seed_gold_fixture import seed_sort_key
from plugin.loader import load_accounts
from plugin.schema import Account, OpportunityBrief


def _briefs(names):
    return [
        OpportunityBrief(account=n, industry="i", tier="A", urgency="High", signal_summary="s",
                         why_now="w", recommended_action="r")
        for n in names
    ]


def _fixture(tmp_path, names, k):
    p = tmp_path / "gold.json"
    p.write_text(json.dumps({"status": "provisional", "k": k, "gold_top_k": names}))
    return p


def test_full_overlap_passes(tmp_path):
    r = evaluate_ranking(_briefs(["a", "b", "z"]), fixture_path=_fixture(tmp_path, ["b", "a"], 2))
    assert r.precision_at_k == 1.0 and r.status == "pass"


def test_zero_overlap_fails(tmp_path):
    r = evaluate_ranking(_briefs(["a", "b"]), fixture_path=_fixture(tmp_path, ["c", "d"], 2))
    assert r.precision_at_k == 0.0 and r.status == "fail"


def test_missing_fixture_skips(tmp_path):
    r = evaluate_ranking(_briefs(["a"]), fixture_path=tmp_path / "nope.json")
    assert r.status == "skip" and r.precision_at_k is None and "nope.json" in r.detail


def test_checked_in_fixture_matches_sample_accounts():
    data = json.loads(DEFAULT_GOLD_FIXTURE.read_text())
    assert isinstance(data["k"], int) and isinstance(data["gold_top_k"], list)
    assert len(data["gold_top_k"]) == data["k"]
    names = {a.name for a in load_accounts("data/sample_accounts.xlsx")}
    assert set(data["gold_top_k"]) <= names


def test_seed_sort_tolerates_none_size_and_unknown_stage():
    accts = [
        Account(name="a", industry="i", deal_stage="Proposal", deal_size_cad=None),
        Account(name="b", industry="i", deal_stage="Weird Stage", deal_size_cad=5.0),
        Account(name="c", industry="i", deal_stage="Proposal", deal_size_cad=9.0),
    ]
    assert [a.name for a in sorted(accts, key=seed_sort_key)] == ["c", "a", "b"]
