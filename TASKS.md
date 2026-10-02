# Media-Opportunity Radar — Task Breakdown

Status key: ✅ done · 🔲 pending

## PT1 — Input ingestion & company profiling
Read a file path, turn it into normalized per-company profiles.

- [x] 1.1 Accept a file path via CLI (`--input`, `--sheet`) — [main.py](main.py)
- [x] 1.2 Parse the workbook, validate the expected header row, fail fast with a clear
      error on mismatch — [plugin/loader.py](plugin/loader.py)
- [x] 1.3 Normalize each row into an `Account` profile: name, industry, deal stage/size,
      last activity, and the three synthetic CRM-context fields — [plugin/schema.py](plugin/schema.py)
- [x] 1.4 Handle missing/empty synthetic fields gracefully (6 of 12 sample rows have no
      notes/signal/relationship data at all) — `Optional[...]` fields, no crash on `None`
- [x] 1.5 Unit tests: row count, presence/absence of optional fields —
      [tests/test_loader.py](tests/test_loader.py)
- [ ] 1.6 Friendlier CLI-level error message when the file path doesn't exist or the sheet
      name is wrong (currently surfaces the raw exception)

## PT2 — Web extraction & signal-finding
Turn one company profile into a grounded real-world signal.

- [x] 2.1 Wire Claude's server-side `web_search` tool for primary discovery (no crawler
      code needed) — [plugin/research.py](plugin/research.py)
- [x] 2.2 Build a custom `fetch_url` tool for full-text verification of one specific URL
      Claude already found — [plugin/fetch.py](plugin/fetch.py)
- [x] 2.2a Hybrid extraction backend: Tavily Extract when `TAVILY_API_KEY` is set (managed,
      handles JS-heavy pages better), falling back to local requests+BeautifulSoup
      automatically if the key is absent or a Tavily call fails — no vendor lock-in for
      running the plugin — [plugin/fetch.py](plugin/fetch.py)
- [x] 2.3 SSRF guard on `fetch_url`: scheme allowlist, DNS resolution + private/loopback/
      link-local/cloud-metadata IP rejection, applied before either backend runs —
      [plugin/fetch.py](plugin/fetch.py)
- [x] 2.4 Agentic tool-use loop: call → collect `fetch_url` calls → execute → feed back →
      repeat until Claude stops calling tools, capped at `MAX_TOOL_ROUNDS` —
      `_run_tool_loop()` in [plugin/research.py](plugin/research.py)
- [x] 2.5 Prompt design that keeps synthetic CRM hints clearly separated from real,
      web-sourced signal (model is told never to cite synthetic data as a real signal)
- [x] 2.6 Parse + validate the model's JSON reply into `OpportunityBrief` (Pydantic) —
      `_extract_json()` / `research_account()`
- [x] 2.7 Retry with backoff on a failed/malformed round — `research_account()`
- [x] 2.8 Offline mock path: deterministic stand-in signal from CRM fields only, no
      network/API key — [plugin/mock.py](plugin/mock.py)
- [x] 2.9 Security tests for the fetch guard (blocks localhost, private IPs, cloud
      metadata, non-http schemes) — [tests/test_fetch_safety.py](tests/test_fetch_safety.py)
- [x] 2.10 Tests for the Tavily/fallback switch (mocked, no real key/network needed) —
      [tests/test_fetch_tavily.py](tests/test_fetch_tavily.py)

## PT3 — Report generation
Turn a set of briefs into the rep-facing artifact.

- [x] 3.1 Rank accounts by tier then urgency — [plugin/rank.py](plugin/rank.py)
- [x] 3.2 Render page 1: ranked summary table (account, industry, tier, urgency, short
      signal) — [plugin/render_pdf.py](plugin/render_pdf.py)
- [x] 3.3 Render one detail page per account: signal, why-now, recommended action, warm
      path, sources — [plugin/render_pdf.py](plugin/render_pdf.py)
- [x] 3.4 CLI wiring: `--mock`, `--limit`, `--workers`, `--output` — [main.py](main.py)
- [x] 3.5 End-to-end pipeline test in mock mode (load → rank → render, asserts a real PDF
      is produced) — [tests/test_mock_pipeline.py](tests/test_mock_pipeline.py)

## PT4 — Evals
Judge whether PT2's signals and PT3's report are actually good, not just that the
pipeline runs without crashing. **Not yet built.**

- [x] 4.1 Structural eval: every brief has required fields populated; every `sources[].url`
      is well-formed; no brief claims `confidence: High` with zero sources
- [x] 4.2 Groundedness eval (leakage check): flag any brief whose `signal_summary` is
      suspiciously close to the *synthetic* `market_signal_hint` text — a sign the model
      repeated the fake hint instead of finding (or honestly failing to find) a real one
- [x] 4.3 Groundedness eval (citation check): for each cited source, fetch it and use an
      LLM-judge call to verify the source text actually supports the claim in
      `signal_summary` — catches real-sounding but unsupported claims
- [x] 4.4 Ranking-quality eval: compare produced tier/urgency ordering against a small
      hand-labeled "gold" top-N fixture; report precision@k
- [x] 4.5 Consistency eval: run `research_account` twice on the same account, measure how
      often tier/urgency/signal agree — low agreement flags an unreliable account
- [x] 4.6 Aggregate eval report (pass/fail counts + scores) printed to console and written
      as JSON for tracking over time
- [x] 4.7 CLI entrypoint, e.g. `python -m evals.run_evals --mock` /
      `python -m evals.run_evals --input data/sample_accounts.xlsx`
