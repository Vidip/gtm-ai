"""Exercises the full load -> research(mock) -> rank -> render chain with no
network and no API key, so CI (or a reviewer with no ANTHROPIC_API_KEY) can
still confirm the plumbing works end to end.
"""
from plugin.loader import load_accounts
from plugin.mock import mock_research_account
from plugin.rank import rank_briefs
from plugin.render_pdf import render_pdf


def test_full_pipeline_mock_mode(tmp_path):
    accounts = load_accounts("data/sample_accounts.xlsx")
    briefs = [mock_research_account(a) for a in accounts]
    ranked = rank_briefs(briefs)

    assert len(ranked) == len(accounts)
    assert all(b.data_mode == "mock" for b in ranked)
    # A-tier/high-urgency accounts should sort before C-tier/low-urgency ones.
    tiers = [b.tier for b in ranked]
    assert tiers == sorted(tiers)

    out_pdf = tmp_path / "briefs.pdf"
    render_pdf(ranked, str(out_pdf))
    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 1000
