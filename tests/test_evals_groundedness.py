from evals.groundedness import evaluate_citations, evaluate_leakage
from plugin.schema import Account, OpportunityBrief, Source

HINT = "Hypothetical scenario: Preparing a Canadian launch for a new product."


def _acc(hint=HINT):
    return Account(name="Acme", industry="CPG", deal_stage="Proposal", market_signal_hint=hint)


def _brief(summary="x", mode="live", sources=None):
    return OpportunityBrief(
        account="Acme", industry="CPG", tier="A", urgency="High", signal_summary=summary,
        why_now="w", recommended_action="r", sources=sources or [], data_mode=mode,
    )


def test_leakage_identical_fails():
    r = evaluate_leakage([_acc()], [_brief(HINT)]).results[0]
    assert r.status == "fail" and "ratio=1.000" in r.detail


def test_leakage_case_whitespace_fails():
    r = evaluate_leakage([_acc()], [_brief("  " + HINT.upper().replace(" ", "   "))]).results[0]
    assert r.status == "fail"


def test_leakage_unrelated_passes():
    r = evaluate_leakage([_acc()], [_brief("The company announced record quarterly earnings in Ontario.")]).results[0]
    assert r.status == "pass"


def test_leakage_mock_skips():
    assert evaluate_leakage([_acc()], [_brief(f"[MOCK] {HINT}", mode="mock")]).results[0].status == "skip"


def test_leakage_no_hint_skips():
    assert evaluate_leakage([_acc(None)], [_brief("anything")]).results[0].status == "skip"


def _srcs(n):
    return [Source(title=str(i), url=f"https://example.com/{i}") for i in range(n)]


class Judge:
    def __init__(self, verdict=None, exc=None):
        self.verdict, self.exc, self.calls = verdict, exc, 0

    def __call__(self, claim, text):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.verdict


def test_citation_supported_passes():
    s = evaluate_citations([_brief(sources=_srcs(1))], fetcher=lambda u: "text", judge=Judge({"supports_claim": True}))
    assert s.results[0].status == "pass"


def test_citation_unsupported_fails_with_reasoning():
    j = Judge({"supports_claim": False, "reasoning": "R"})
    r = evaluate_citations([_brief(sources=_srcs(1))], fetcher=lambda u: "text", judge=j).results[0]
    assert r.status == "fail" and "R" in r.detail


def test_citation_fetch_failure_skips_without_judge():
    j = Judge({"supports_claim": True})
    r = evaluate_citations([_brief(sources=_srcs(1))], fetcher=lambda u: "[fetch failed: X]", judge=j).results[0]
    assert r.status == "skip" and j.calls == 0


def test_citation_judge_exception_skips():
    j = Judge(exc=RuntimeError("boom"))
    r = evaluate_citations([_brief(sources=_srcs(1))], fetcher=lambda u: "text", judge=j).results[0]
    assert r.status == "skip" and "boom" in r.detail


def test_citation_bad_judge_output_skips():
    j = Judge({"reasoning": "no bool"})
    assert evaluate_citations([_brief(sources=_srcs(1))], fetcher=lambda u: "t", judge=j).results[0].status == "skip"


def test_citation_cap_on_sources():
    calls = []
    j = Judge({"supports_claim": True})
    s = evaluate_citations(
        [_brief(sources=_srcs(5))], fetcher=lambda u: calls.append(u) or "t", judge=j, max_sources_per_brief=3
    )
    assert len(s.results) == 3 and len(calls) == 3


def test_citation_mock_or_no_sources_single_skip():
    s = evaluate_citations([_brief(mode="mock", sources=_srcs(2))], judge=Judge({"supports_claim": True}))
    assert len(s.results) == 1 and s.results[0].status == "skip"
    s = evaluate_citations([_brief(sources=[])], judge=Judge({"supports_claim": True}))
    assert len(s.results) == 1 and s.results[0].status == "skip"
