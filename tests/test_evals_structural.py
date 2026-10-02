from evals.structural import evaluate_structural
from plugin.schema import OpportunityBrief, Source


def _brief(**kw):
    base = dict(
        account="Acme",
        industry="Retail",
        tier="A",
        urgency="High",
        signal_summary="Acme opened a store.",
        why_now="Q4 push.",
        recommended_action="Call the CMO.",
        sources=[Source(title="t", url="https://example.com/a")],
        confidence="High",
    )
    base.update(kw)
    return OpportunityBrief(**base)


def _by_check(summary, check):
    return [r for r in summary.results if r.check == check]


def test_three_results_per_brief():
    assert len(evaluate_structural([_brief(), _brief(account="B")]).results) == 6


def test_empty_required_field_fails():
    s = evaluate_structural([_brief(recommended_action="  ")])
    r = _by_check(s, "structural.required_fields")[0]
    assert r.status == "fail" and "recommended_action" in r.detail


def test_bad_url_fails():
    s = evaluate_structural([_brief(sources=[Source(title="x", url="not-a-url")])])
    assert _by_check(s, "structural.source_urls")[0].status == "fail"


def test_high_confidence_without_sources_fails():
    s = evaluate_structural([_brief(sources=[])])
    assert _by_check(s, "structural.confidence_vs_sources")[0].status == "fail"
    assert _by_check(s, "structural.source_urls")[0].status == "pass"


def test_good_brief_passes_everything():
    s = evaluate_structural([_brief()])
    assert s.passed == 3 and s.failed == 0
