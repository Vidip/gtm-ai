# PT4 — Evals: Architecture

## Status

| Gate         | Status                          |
|--------------|---------------------------------|
| Architecture | **approved** |
| Dev          | blocked (waiting on Architecture) |
| Review       | blocked (waiting on Dev)        |
| QA           | blocked (waiting on Review)     |

Dev/Review/QA lines are copied from [WORKFLOW.md](../WORKFLOW.md) (PT4 section), which stays
the source of truth for gate status. Scope is the PT4 subtask list in [TASKS.md](../TASKS.md)
(4.1–4.7); checkboxes there are not duplicated here.

This document is based on the `### PT4 Architecture` section of WORKFLOW.md. It keeps every
decision from that section and adds the clarifications listed next. **Where the two differ,
this document wins.**

### Clarifications vs. WORKFLOW.md (found during review)

None of these change scope. Each one resolves a gap a dev agent would otherwise have to guess
at. All are cheap to change later.

| # | Gap in the WORKFLOW.md section | Resolution here |
|---|---|---|
| C1 | `research_all()` did not say who prints the `ok` / `FAILED` lines, so it was unclear how `main.py` would keep its stdout byte-for-byte. | `research_all()` takes an optional `on_result` callback and prints nothing itself. `main.py` passes a callback that prints the existing lines. |
| C2 | `research_all()` returned briefs in `as_completed` order. That order is nondeterministic, and `rank_briefs()` uses a stable sort, so ties in tier and urgency (5 B/Medium accounts in the sample data) were ordered by thread timing. | `research_all()` returns briefs in **input-account order**, whatever order they complete in. |
| C3 | 4.3 says `_extract_json` is reused from `plugin.research`. A module-level import of it would load `plugin.research` in `--mock`, which breaks the 4.5/4.7 acceptance criterion "mock never imports `plugin.research`". | `plugin.research` (and `anthropic`) may only be imported **inside** the default-judge / default-researcher code paths, never at module top level in `evals/`. |
| C4 | The sys.modules assertion in 4.5/4.7 would fail falsely if another test had already imported `plugin.research`. | The test first calls `monkeypatch.delitem(sys.modules, "plugin.research", raising=False)` (and likewise for `anthropic`), then asserts neither one is back in `sys.modules` after `main([...])`. |
| C5 | The gold-fixture seeding sort `-deal_size_cad` crashes when `deal_size_cad is None`, `_STAGE_TIER[stage]` raises a KeyError on unknown stages, and equal values had no tie-break. | Sort key: `(_STAGE_TIER.get(a.deal_stage, "C"), -(a.deal_size_cad or 0.0), a.name)`. |
| C6 | Default fixture path `"evals/fixtures/gold_ranking.json"` depended on the current working directory. | Default is `Path(evals.__file__).parent / "fixtures" / "gold_ranking.json"`. The `--gold-fixture` CLI flag still overrides it. |
| C7 | 4.3 granularity was unclear: one `CheckResult` per brief or per source? | One per judged source. A brief with no sources, or in mock mode, gets exactly **one** skip result for the whole brief. |
| C8 | The design did not say whether an *injected* judge or researcher that raises is skipped, or crashes the eval. | Any exception from `judge` → that source is `skip`, with the exception text in `detail`. Any exception from `researcher` → that account is `skip` in consistency. Neither is raised. |
| C9 | The design did not say who builds the single mock-mode consistency skip summary. | `evals/consistency.py` exposes `consistency_skipped_summary(reason: str) -> EvalSummary`. `run_evals.py` calls it in `--mock`. |
| C10 | The design did not say how the eval CLI handles accounts whose research failed, or a run that produced zero briefs. | Failures are recorded in a new `AggregateEvalReport.research_failures` field and force `overall_pass=False`. Zero briefs → print an error to stderr, write no report, exit `1`. |
| C11 | Mock-mode exit `0` (4.7) depends on ranking precision ≥ 0.6. That was not shown to hold. | It holds: the sample data has exactly 3 A-tier accounts (Negotiation/Proposal). The mock and the seeded gold fixture both put them in the top 5, so precision@5 ≥ 3/5 = 0.6. The A-tier rule comes from `_STAGE_TIER`. The test asserts it (AC 4.7). |
| C12 | `evals/out/` is a generated-artifact directory. | Add `evals/out/` to `.gitignore` (create the file if it is missing). |

---

## Scope

Judge whether PT2's signals and PT3's ranking are *good*, not only that the pipeline runs.
In scope:

- 4.1 structural checks
- 4.2 leakage check
- 4.3 LLM-judge citation check
- 4.4 precision@k against a gold top-k
- 4.5 run-to-run consistency
- 4.6 aggregate report (console + JSON)
- 4.7 CLI

Out of scope:

- Changing PT2/PT3 behaviour.
- Evaluating the PDF rendering itself.
- Any new paid API. The 4.3 judge reuses the existing Anthropic key/model. The 4.3 fetch reuses `plugin.fetch` (including its optional Tavily backend).

Dependency rule: `evals/` imports from `plugin/`. `plugin/` never imports from `evals/`.

---

## Files / modules

### Added

| Path | Responsibility |
|---|---|
| `evals/__init__.py` | Package marker. |
| `evals/schema.py` | Pydantic result models (see Data schemas). |
| `evals/structural.py` | 4.1 `evaluate_structural()` |
| `evals/groundedness.py` | 4.2 `evaluate_leakage()`, 4.3 `evaluate_citations()`, plus the private default LLM judge |
| `evals/ranking.py` | 4.4 `evaluate_ranking()`, `DEFAULT_GOLD_FIXTURE` |
| `evals/consistency.py` | 4.5 `evaluate_consistency()`, `consistency_skipped_summary()` |
| `evals/report.py` | 4.6 `build_report()`, `print_report()`, `write_report_json()` |
| `evals/run_evals.py` | 4.7 CLI, `main(argv=None) -> int`, runnable as `python -m evals.run_evals` |
| `evals/seed_gold_fixture.py` | One-off script that writes the provisional gold fixture (4.4) |
| `evals/fixtures/gold_ranking.json` | Checked-in gold top-k fixture (provisional) |
| `plugin/orchestrate.py` | `research_all()`, extracted from `main.py`, shared by both CLIs |
| `tests/test_evals_structural.py`, `tests/test_evals_groundedness.py`, `tests/test_evals_ranking.py`, `tests/test_evals_consistency.py`, `tests/test_evals_report.py`, `tests/test_evals_cli.py`, `tests/test_orchestrate.py` | Offline tests: no network, no API key |

### Changed

| Path | Change |
|---|---|
| `main.py` | Replace `_research_one` and the inline `ThreadPoolExecutor` loop with `plugin.orchestrate.research_all(..., on_result=<printer>)`. Its CLI flags, stdout/stderr lines (`"  ok    {name}"`, `"  FAILED {name}: {err}"`), and exit codes (0 / 1 / 2) stay unchanged. |
| `.gitignore` | Add `evals/out/` (C12). |

No changes to `plugin/schema.py`, `plugin/research.py`, `plugin/mock.py`, `plugin/fetch.py`, or `plugin/rank.py`.

---

## Data schemas (`evals/schema.py`)

```python
EvalStatus = Literal["pass", "fail", "skip"]

class CheckResult(BaseModel):
    check: str            # "structural.required_fields" | "structural.source_urls" |
                          # "structural.confidence_vs_sources" | "groundedness.leakage" |
                          # "groundedness.citation" | "consistency.agreement"
    account: str          # account name, or "*" for a whole-category skip
    status: EvalStatus
    detail: str = ""      # non-empty whenever status != "pass"

class EvalSummary(BaseModel):
    name: str             # "structural" | "leakage" | "citation" | "consistency"
    total: int            # == len(results)
    passed: int
    failed: int
    skipped: int
    score: float          # passed / (total - skipped); 0.0 if total == skipped
    results: list[CheckResult] = Field(default_factory=list)

    @classmethod
    def from_results(cls, name: str, results: list[CheckResult]) -> "EvalSummary": ...
        # single place that computes the counts and the score; every evaluator uses it

class RankingEvalResult(BaseModel):
    name: Literal["ranking"] = "ranking"
    status: EvalStatus    # "skip" if the fixture file is absent
    k: int
    precision_at_k: Optional[float] = None
    gold_top_k: list[str] = Field(default_factory=list)
    produced_top_k: list[str] = Field(default_factory=list)
    detail: str = ""

class ResearchFailure(BaseModel):          # added (C10)
    account: str
    error: str                              # str(exception)

class AggregateEvalReport(BaseModel):
    generated_at: str                       # ISO 8601 UTC, e.g. "2026-10-01T12:00:00Z"
    data_mode: Literal["live", "mock"]
    account_count: int                      # accounts loaded (after --limit)
    research_failures: list[ResearchFailure] = Field(default_factory=list)  # added (C10)
    structural: EvalSummary
    leakage: EvalSummary
    citation: EvalSummary
    ranking: RankingEvalResult
    consistency: EvalSummary
    overall_pass: bool
```

Gold fixture (`evals/fixtures/gold_ranking.json`):

```json
{
  "status": "provisional",
  "note": "Seeded by evals/seed_gold_fixture.py from deal_stage/deal_size_cad ... set status to \"human-labeled\" when replaced by real GTM judgment.",
  "k": 5,
  "gold_top_k": ["<exact Account.name>", "..."]
}
```

`status` and `note` are informational only. The eval code reads only `k` and `gold_top_k`.

Module constants:

- `LEAKAGE_RATIO_THRESHOLD = 0.9` (groundedness.py)
- `RANKING_PASS_THRESHOLD = 0.6` (ranking.py)

---

## Flow

```
                 python -m evals.run_evals [--mock | --input X.xlsx] ...
                                     |
                                     v
                  plugin.loader.load_accounts(input, sheet)  -> [:limit]
                                     |
                                     v
        plugin.orchestrate.research_all(accounts, mock, workers, on_result=print)
            mock: plugin.mock.mock_research_account     live: plugin.research.research_account (lazy import)
                                     |
                     briefs (input order) + failures --------------------+
                                     |                                   |
                    zero briefs? --yes--> stderr msg, exit 1             |
                                     | no                                |
                                     v                                   |
                        plugin.rank.rank_briefs(briefs)                  |
                                     |                                   |
     +-----------------+-------------+--------------+-----------------+  |
     v                 v                            v                 v  |
 4.1 structural   4.2 leakage            4.3 citations          4.4 ranking
 (all briefs)     (accounts+briefs;      (briefs; mock->skip;   (ranked briefs
                   mock->skip)            fetcher+LLM judge)     vs gold fixture)
     |                 |                            |                 |  |
     |      4.5 consistency: live -> evaluate_consistency(accounts[:sample], runs)
     |                   mock -> consistency_skipped_summary(...)     |  |
     +-----------------+-------------+--------------+-----------------+  |
                                     v                                   |
       4.6 build_report(..., research_failures) <------------------------+
                                     |
                 print_report()  +  write_report_json()  -> <out>/report_<ts>.json
                                     |                       <out>/latest.json
                                     v
                       exit 0 if overall_pass else 1
```

---

## Interfaces

### `plugin/orchestrate.py`

```python
ResultCallback = Callable[[Account, Optional[OpportunityBrief], Optional[Exception]], None]

def research_all(
    accounts: list[Account],
    *,
    mock: bool,
    workers: int = 4,
    on_result: ResultCallback | None = None,
) -> tuple[list[OpportunityBrief], list[tuple[str, Exception]]]:
```

- Thread pool size is `max_workers = 1 if mock else workers`, the same as today's `main.py`.
- Live mode imports `plugin.research` lazily, the same as today's `_research_one`.
- `on_result` is called once per account, in completion order, from the main thread.
- The returned `briefs` list is in input-account order (C2). `failures` is a list of `(account.name, exc)`.
- This function never raises because of a single account's failure.

### `evals/structural.py`

```python
def evaluate_structural(briefs: list[OpportunityBrief]) -> EvalSummary  # name="structural"
```

Each brief gets exactly 3 results:

1. `required_fields`: `account`, `industry`, `signal_summary`, `why_now`, and `recommended_action` are all non-empty after `.strip()`. If any are empty, `detail` lists the names of the empty fields.
2. `source_urls`: every `urlparse(s.url)` has scheme `http` or `https` and a non-empty `netloc`. If any fail, `detail` lists the bad URLs. With zero sources this check passes trivially.
3. `confidence_vs_sources`: fails iff `confidence == "High"` and `len(sources) == 0`.

### `evals/groundedness.py`

```python
def evaluate_leakage(accounts: list[Account], briefs: list[OpportunityBrief]) -> EvalSummary  # name="leakage"
```

- Briefs are matched to accounts by `account.name == brief.account`. Briefs with no matching account are skipped, with `detail="no matching account"`.
- `skip` if `market_signal_hint is None` or `brief.data_mode == "mock"`.
- Otherwise, normalize both strings with `" ".join(s.casefold().split())` and compute `ratio = SequenceMatcher(None, hint_norm, summary_norm).ratio()`.
- `fail` iff `ratio > LEAKAGE_RATIO_THRESHOLD`. `detail` always includes `ratio=<.3f>`.

```python
def evaluate_citations(
    briefs: list[OpportunityBrief],
    *,
    fetcher: Callable[[str], str] = fetch_and_extract,     # from plugin.fetch (module-level import OK)
    judge: Callable[[str, str], dict] | None = None,       # (claim, source_text) -> {"supports_claim": bool, "reasoning": str}
    max_sources_per_brief: int = 3,
) -> EvalSummary  # name="citation"
```

- A brief in mock mode, or with no sources, gets **one** `skip` result (C7).
- Otherwise, for each `src in brief.sources[:max_sources_per_brief]`:
  - If `text = fetcher(src.url)` starts with `"[fetch failed"`, the result is `skip` and **the judge is not called**.
  - Otherwise call `judge(brief.signal_summary, text)`. If the judge raises, or returns something without a bool `supports_claim`, the result is `skip` (C8).
  - The result is `pass` iff `supports_claim is True`. Otherwise it is `fail` with `detail = reasoning`.
- `detail` always includes the source URL.

Default judge (when `judge is None`), built lazily the first time it is needed (C3):

- Imports `anthropic` and `plugin.research.MODEL` / `_extract_json` inside the function.
- Makes one `client.messages.create(model=MODEL, max_tokens=500, system=JUDGE_SYSTEM_PROMPT, ...)` call per source, with no tools.
- The prompt asks for JSON only: `{"supports_claim": bool, "reasoning": str}`, judged strictly on whether the source text supports the claim.
- Retries once after a short sleep (`max_retries=1`, `sleep_s=1.5`). The final failure propagates to the caller above and becomes a `skip`.

### `evals/ranking.py`

```python
DEFAULT_GOLD_FIXTURE: Path  # Path(__file__).parent / "fixtures" / "gold_ranking.json"   (C6)

def evaluate_ranking(ranked_briefs: list[OpportunityBrief], *, fixture_path: str | Path = DEFAULT_GOLD_FIXTURE) -> RankingEvalResult
```

- If the fixture file is missing, return `status="skip"`, `k=0`, `precision_at_k=None`, and a `detail` that names the path. Do not raise.
- Otherwise:
  - `produced_top_k = [b.account for b in ranked_briefs[:k]]`
  - `precision_at_k = len(set(gold_top_k) & set(produced_top_k)) / k`
  - `status = "pass"` iff `precision_at_k >= RANKING_PASS_THRESHOLD`
- Matching is on set membership only; order within the top k does not count.

### `evals/seed_gold_fixture.py`

- Run as `python -m evals.seed_gold_fixture [--input data/sample_accounts.xlsx] [--k 5] [--out <DEFAULT_GOLD_FIXTURE>]`.
- Sort key: `(_STAGE_TIER.get(a.deal_stage, "C"), -(a.deal_size_cad or 0.0), a.name)` (C5).
- Writes the JSON above with `status="provisional"`.

### `evals/consistency.py`

```python
def evaluate_consistency(
    accounts: list[Account],
    *,
    runs: int = 2,
    researcher: Callable[[Account], OpportunityBrief] | None = None,  # default: lazy plugin.research.research_account
) -> EvalSummary  # name="consistency"

def consistency_skipped_summary(reason: str) -> EvalSummary
    # exactly one CheckResult(check="consistency.agreement", account="*", status="skip", detail=reason)
```

- For each account, call `researcher` `runs` times, sequentially.
- The result is `pass` iff `tier` and `urgency` each have exactly one distinct value across all runs. Otherwise it is `fail`, and `detail` names each differing field and its sorted distinct values (e.g. `tier differs: ['A', 'B']`).
- `detail` always also includes `signal_similarity=<min pairwise SequenceMatcher ratio, .3f>`. This is informational only and never decides pass or fail.
- If the researcher raises, the result for that account is `skip` (C8).
- These runs are independent of the main `research_all` pass. The eval does not reuse the brief that pass produced.

### `evals/report.py`

```python
def build_report(*, data_mode, account_count, structural, leakage, citation, ranking, consistency,
                 research_failures: list[ResearchFailure] = ()) -> AggregateEvalReport
def print_report(report: AggregateEvalReport) -> None
def write_report_json(report: AggregateEvalReport, path: str | Path) -> None   # creates parent dirs
```

`build_report` sets `generated_at` to the current UTC time and computes:

```
overall_pass = (structural.failed == 0 and leakage.failed == 0 and citation.failed == 0
                and consistency.failed == 0 and ranking.status != "fail"
                and not research_failures)
```

`print_report` output, in order:

1. One line per category, in the order structural, leakage, citation, consistency: `"<name>: <passed>/<total-skipped> passed (<skipped> skipped), score=<score:.2f>"`
2. `"ranking: precision@<k>=<p:.2f> (<status>)"`, or `"ranking: skipped (<detail>)"`
3. `"research failures: <n>"`, only if `n > 0`
4. `"OVERALL: PASS"` or `"OVERALL: FAIL"`

`write_report_json` writes `report.model_dump_json(indent=2)`.

### `evals/run_evals.py` (CLI)

```
python -m evals.run_evals --mock
python -m evals.run_evals --input data/sample_accounts.xlsx [--sheet NAME] [--limit N] [--workers N]
    [--consistency-runs N=2] [--consistency-sample N=3] [--gold-fixture PATH=DEFAULT_GOLD_FIXTURE]
    [--max-citations-per-brief N=3] [--report-out DIR=evals/out]
```

- `--input` (default `data/sample_accounts.xlsx`), `--sheet` (default `Sample Accounts`), `--limit`, `--workers` (default 4), and `--mock` have the same meaning as in `main.py`.
- Consistency in live mode runs on `accounts[:consistency_sample]`. In `--mock` it is replaced by `consistency_skipped_summary("mock mode is deterministic by design, see plugin/mock.py")`.
- Report files:
  - `<report-out>/report_<YYYYMMDDTHHMMSSZ>.json` (new file each run)
  - `<report-out>/latest.json` (overwritten each run)
- Exit codes:
  - `0` if `overall_pass`
  - `1` if not `overall_pass`, or if zero briefs were produced (C10)

---

## Acceptance criteria

All tests run offline. They need no `ANTHROPIC_API_KEY`, no `TAVILY_API_KEY`, and no network. Network-touching dependencies are injected as stubs.

**AC-4.1 (structural)** — `tests/test_evals_structural.py`, with hand-built `OpportunityBrief`s:

- (a) `evaluate_structural` returns exactly `3 * len(briefs)` results.
- (b) `recommended_action=""` gives `fail` on `structural.required_fields`, with `"recommended_action"` in `detail`.
- (c) `sources=[Source(title="x", url="not-a-url")]` gives `fail` on `structural.source_urls`.
- (d) `confidence="High", sources=[]` gives `fail` on `structural.confidence_vs_sources`.
- (e) A fully populated brief with `confidence="High"` and one `https://example.com/a` source passes all 3 checks.

**AC-4.2 (leakage)** — `tests/test_evals_groundedness.py`:

- (a) A live brief whose `signal_summary` equals its account's hint gives `fail`, and `detail` contains `ratio=1.000`.
- (b) A live brief whose `signal_summary` differs only in case and whitespace from the hint gives `fail`.
- (c) A live brief with an unrelated `signal_summary` gives `pass`.
- (d) A mock brief `"[MOCK] {hint}"` gives `skip`.
- (e) An account with `market_signal_hint=None` gives `skip`.

**AC-4.3 (citation)** — `tests/test_evals_groundedness.py`, with a stub `fetcher` and a stub `judge` that records its calls:

- (a) `supports_claim=True` gives `pass`.
- (b) `supports_claim=False, reasoning="R"` gives `fail`, with `"R"` in `detail`.
- (c) `fetcher` returning `"[fetch failed: X]"` gives `skip`, **and the stub judge's call count for that source is 0**.
- (d) A judge that raises gives `skip`, and does not propagate the exception.
- (e) A brief with 5 sources and `max_sources_per_brief=3` produces exactly 3 results, and `fetcher` is called 3 times.
- (f) A mock brief, or a brief with no sources, produces exactly 1 `skip` result.

**AC-4.4 (ranking)** — `tests/test_evals_ranking.py`, with `tmp_path` fixture files:

- (a) A produced top-k that equals the gold set gives `precision_at_k == 1.0` and `status="pass"`.
- (b) Zero overlap gives `0.0` and `"fail"`.
- (c) A missing file gives `status="skip"`, `precision_at_k is None`, and no exception.
- (d) The checked-in `evals/fixtures/gold_ranking.json` is valid JSON with int `k` and list `gold_top_k` of length `k`. Every name in it exactly matches an `Account.name` loaded from `data/sample_accounts.xlsx`.
- (e) Running the seed script's sort on a list containing an account with `deal_size_cad=None` and one with an unknown `deal_stage` does not raise.

**AC-4.5 (consistency)** — `tests/test_evals_consistency.py`, with a stub `researcher`:

- (a) Returning `tier="A"` and then `tier="B"` gives `fail`, and `detail` contains `"tier"`, `"A"`, and `"B"`.
- (b) Identical `tier` and `urgency` on both calls give `pass`, even when `signal_summary` differs.
- (c) The stub is called exactly `runs` times per account.
- (d) A researcher that raises gives `skip`.
- (e) `consistency_skipped_summary("r")` has `total == 1`, `skipped == 1`, and `results[0].account == "*"`.

**AC-4.6 (report)** — `tests/test_evals_report.py`:

- (a) All-pass summaries give `overall_pass=True`, and the captured stdout contains `"OVERALL: PASS"`.
- (b) The same summaries with structural `failed=1` give `overall_pass=False` and `"OVERALL: FAIL"`.
- (c) `ranking.status="skip"` with everything else passing gives `overall_pass=True`.
- (d) A non-empty `research_failures` gives `overall_pass=False`.
- (e) The output of `write_report_json` round-trips through `json.loads`, and `account_count`, `data_mode`, and `research_failures` are preserved.
- (f) `EvalSummary.from_results` with every result skipped gives `score == 0.0`.

**AC-4.7 (CLI)** — `tests/test_evals_cli.py`, which calls `evals.run_evals.main(["--mock", "--report-out", str(tmp_path)])`:

- (a) With `ANTHROPIC_API_KEY` unset, and `plugin.research` and `anthropic` removed from `sys.modules` via monkeypatch first (C4), `main` returns `0`. Afterwards, neither `plugin.research` nor `anthropic` is in `sys.modules`.
- (b) `tmp_path/latest.json` and exactly one `tmp_path/report_*.json` exist. Both parse with `json.load`, and both have `data_mode == "mock"` and `account_count == 12`.
- (c) In that report:
  - structural has `failed == 0`
  - ranking has `status == "pass"` and `precision_at_k >= 0.6` (C11)
  - leakage and citation have `passed == 0` and `failed == 0`
  - consistency has exactly 1 result, which is a skip
- (d) `--limit 3` gives `account_count == 3`.

**AC-orchestrate (supports 4.7; protects PT3)** — `tests/test_orchestrate.py`:

- (a) `research_all(accounts, mock=True)` returns briefs whose `account` order equals the input order, with `failures == []`.
- (b) `on_result` is called once per account.
- (c) Existing `tests/test_mock_pipeline.py` and all other existing tests still pass without changes.
- (d) `python main.py --mock --output <tmp>` still exits `0` and prints one `"  ok    <name>"` line per account.

---

## Open risks / known limitations (not blocking)

- **Gold fixture is provisional (4.4).** It is seeded from the same deal-stage priority that `plugin/mock.py` uses. So in mock mode precision@k mostly validates the scoring *mechanism*, not true ranking quality. Someone with GTM context should hand-edit `gold_top_k` and set `status: "human-labeled"`; no code change is needed for that.
- **Mock-mode ranking pass is structural, not luck (C11).** If the sample sheet ever has fewer than 3 A-tier accounts, or `k` or the threshold change, AC-4.7(c) may need revisiting.
- **4.3 cost/latency:** each judged source costs one fetch and one LLM call. This is capped by `--max-citations-per-brief` (default 3).
- **4.5 cost:** `runs × consistency_sample` extra live research calls, 6 by default. Consistency is skipped in `--mock`.
- **The LLM judge can be wrong or inconsistent.** Treat citation fails as triggers for a human spot-check, not as ground truth. `reasoning` is kept in `detail`.
- **Leakage threshold 0.9** catches only near-verbatim echoes. Paraphrased leakage passes. The threshold is a module constant, so it can be tuned once live data exists.
- **Live-mode nondeterminism:** web search results change over time. So comparing consistency and citation scores across dated `report_*.json` files mixes model variance with variance in the web content itself.
