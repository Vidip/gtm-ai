# PT3 — Report generation: Architecture (as-built)

## Status

| Gate | Status |
|---|---|
| Architecture | **approved**: covers 3.1–3.5 |
| Dev | done *(copied from WORKFLOW.md)* |
| Review | approved *(copied from WORKFLOW.md)* |
| QA | passed *(copied from WORKFLOW.md: "manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass")* |

This document records the code as it was built. PT3 existed before the formal Architecture gate. Each gap between the code and [TASKS.md](../TASKS.md) PT3 is listed explicitly below; none was silently dropped.

## Scope

Requirements come from [TASKS.md](../TASKS.md) PT3, which is the source of truth for the checkboxes. This doc does not copy them.

PT3 receives a list of `OpportunityBrief`s from PT2 (live) or `plugin/mock.py` (mock) and produces the PDF the rep reads:

- 3.1 ranking: in scope, built
- 3.2 page-1 summary table: in scope, built
- 3.3 one detail page per account: in scope, built
- 3.4 CLI wiring (`--mock`, `--limit`, `--workers`, `--output`): in scope, built
- 3.5 end-to-end mock pipeline test: in scope, built

Out of scope: ingestion (PT1), research and signal-finding (PT2), quality evaluation (PT4).

## Files / modules

| File | Responsibility | Subtask |
|---|---|---|
| `/Users/vidipmalhotra/SJC/plugin/rank.py` | `rank_briefs()` does a stable sort by `OpportunityBrief.rank_key()` | 3.1 |
| `/Users/vidipmalhotra/SJC/plugin/schema.py` | `OpportunityBrief.rank_key()` defines the tier/urgency ordering. The data contract is shared with PT1 and PT2 | 3.1 |
| `/Users/vidipmalhotra/SJC/plugin/render_pdf.py` | `render_pdf()` builds the ReportLab platypus story: title and subtitle, summary table, `PageBreak`, then one card per brief | 3.2, 3.3 |
| `/Users/vidipmalhotra/SJC/main.py` | argparse CLI, thread-pool research fan-out (mock or live), rank, render, exit codes | 3.4 |
| `/Users/vidipmalhotra/SJC/tests/test_mock_pipeline.py` | Offline load → mock research → rank → render test, asserts a non-trivial PDF exists | 3.5 |

Dependencies: `reportlab` for rendering and `pydantic` for the schema. `--mock` mode imports nothing from the network or the `anthropic` SDK, because `plugin.research` is lazily imported in `main._research_one`.

## Data schemas

Inputs are defined in `plugin/schema.py` (owned by PT2/PT1 and consumed read-only here):

```python
Tier = Literal["A", "B", "C"]
Urgency = Literal["High", "Medium", "Low"]

class Source(BaseModel):
    title: str
    url: str

class OpportunityBrief(BaseModel):
    account: str
    industry: str
    tier: Tier
    urgency: Urgency
    signal_summary: str
    why_now: str
    recommended_action: str
    warm_path: Optional[str] = None
    sources: list[Source] = []
    confidence: Literal["High", "Medium", "Low"] = "Medium"
    data_mode: Literal["live", "mock"] = "live"

    def rank_key(self) -> tuple:  # (tier_rank, urgency_rank); A<B<C, High<Medium<Low
```

Output: a single PDF file at `--output` (default `out/briefs.pdf`), US Letter with 0.75in margins:

- **Page 1:** title "Media-Opportunity Radar". The subtitle reads `Generated <YYYY-MM-DD HH:MM> · data mode: <LIVE (Claude + web search) | MOCK (offline demo, no live data)> · <N> accounts`. Below it is a 6-column table: `#, Account, Industry, Tier, Urgency, Signal (short)`. `Signal (short)` is `signal_summary` cut to 87 characters plus `...` when it is longer than 90 characters.
- **Pages 2..N+1:** one card per brief, in ranked order. Each card has:
  - heading `<i>. <account>`
  - a meta line with colour-coded tier and urgency, plus industry, confidence and data_mode
  - labelled sections: Signal, Why now, Recommended action, Warm path (only if `warm_path` is truthy), and Sources (only if `sources` is non-empty, each rendered as `<link href=url>title</link>`)
  - a `PageBreak` after every card except the last

No new schemas were introduced by PT3.

## Flow

```
 main.py (argparse: --input --sheet --output --limit --workers --mock)
    |
    v
 plugin.loader.load_accounts(input, sheet)  --> list[Account]        [PT1]
    |  (slice to --limit)
    v
 ThreadPoolExecutor(max_workers = 1 if --mock else --workers)
    |   per account: _research_one(account, mock)
    |     mock -> plugin.mock.mock_research_account
    |     live -> plugin.research.research_account (lazy import)      [PT2]
    |   collect via as_completed(): briefs[] / failures[]
    v
 briefs empty? --yes--> stderr "No briefs produced..." ; exit 1
    |
    v
 plugin.rank.rank_briefs(briefs)   sorted by (tier, urgency)          [3.1]
    |
    v
 plugin.render_pdf.render_pdf(ranked, --output)                       [3.2, 3.3]
    |   page 1: title + subtitle + summary table, PageBreak
    |   pages 2..: one detail card per brief
    v
 stdout "Wrote N briefs to <path> in Xs"
 exit 0 (no failures) | exit 2 (some accounts failed, PDF still written)
```

## Interfaces

```python
# plugin/rank.py
def rank_briefs(briefs: list[OpportunityBrief]) -> list[OpportunityBrief]
    # returns a new list, does not mutate input; Python sort is stable

# plugin/render_pdf.py
def render_pdf(briefs: list[OpportunityBrief], output_path: str,
               title: str = "Media-Opportunity Radar") -> None
    # writes the file; raises on I/O or ReportLab markup errors (no internal catch)

# main.py
def parse_args(argv=None) -> argparse.Namespace
def main(argv=None) -> int   # 0 = all ok, 1 = no briefs, 2 = partial failure
```

CLI flags (3.4):

| Flag | Default | Semantics |
|---|---|---|
| `--input` | `data/sample_accounts.xlsx` | workbook path |
| `--sheet` | `Sample Accounts` | sheet name |
| `--output` | `out/briefs.pdf` | PDF path |
| `--limit` | `None` | first N accounts only (`0` is treated as no limit because the check is truthy) |
| `--workers` | `4` | thread-pool size in live mode; forced to 1 in mock mode |
| `--mock` | off | offline deterministic briefs, no API key or network |

Per-account progress goes to stdout as `"  ok    {name}"` and to stderr as `"  FAILED {name}: {err}"`. PT4's architecture depends on these lines and the exit codes staying stable (see WORKFLOW.md PT4, `plugin/orchestrate.py` refactor).

## Acceptance criteria

The review/QA agent checks one criterion per subtask. The "Verified by" line shows whether an existing test covers it.

- **3.1 Ranking.** For any list of briefs, `rank_briefs()` returns every A-tier brief before every B-tier brief, and every B-tier brief before every C-tier brief. Within a tier, High urgency comes before Medium, which comes before Low. Input `[C/Low, A/Low, A/High, B/Medium]` returns `[A/High, A/Low, B/Medium, C/Low]`. The input list is not mutated.
  *Verified by:* `test_mock_pipeline.py` checks tier ordering only (`tiers == sorted(tiers)`). **Gap:** no test checks urgency ordering inside a tier.
- **3.2 Summary page.** In a rendered PDF, the text extracted from page 1 contains the header cells `Account`, `Industry`, `Tier`, `Urgency`, `Signal (short)`, and one row per brief in ranked order. A brief whose `signal_summary` is longer than 90 characters shows exactly its first 87 characters followed by `...` in that row.
  *Verified by:* only indirectly, through "PDF exists and is >1000 bytes". **Gap:** no content assertion.
- **3.3 Detail pages.** For N briefs the PDF has exactly N+1 pages. Page i+1 contains `"{i}. {account}"`, `Signal`, `Why now`, `Recommended action`. It contains `Warm path` iff `warm_path` is truthy, and `Sources` plus each source title iff `sources` is non-empty.
  *Verified by:* only indirectly (the file is produced). **Gap:** no page-count or content assertion.
- **3.4 CLI wiring.** `main.main(["--mock", "--limit", "3", "--output", str(tmp_path/"x.pdf")])` returns `0`, writes `x.pdf`, and prints exactly 3 `"  ok    "` lines. It does not import `plugin.research` (check that `"plugin.research" not in sys.modules`, starting from a clean interpreter). `--workers` is honoured in live mode and ignored (forced to 1) in mock mode.
  *Verified by:* manual run only. **Gap:** no test calls `main.main()`.
- **3.5 End-to-end mock test.** `pytest tests/test_mock_pipeline.py` passes with no `ANTHROPIC_API_KEY` set and no network. It loads `data/sample_accounts.xlsx`, mock-researches every account, ranks them, renders to `tmp_path`, and asserts the PDF exists with size > 1000 bytes and all briefs have `data_mode == "mock"`.
  *Verified by:* `tests/test_mock_pipeline.py::test_full_pipeline_mock_mode`. Met.

## Open risks / gaps vs TASKS.md

1. **Unescaped markup in `Paragraph`.** `render_pdf.py` passes model-generated text (`account`, `signal_summary`, `why_now`, `recommended_action`, `warm_path`, `source.title`, `source.url`) into ReportLab `Paragraph` without escaping. In live mode, a stray `<`, an unbalanced tag, or `&` / `"` inside a URL can make `doc.build()` raise or render wrongly, and the whole PDF is then lost. Recommended fix (small, local): wrap these values with `xml.sax.saxutils.escape` (plus `quote` for the `href`). Add a test that renders a brief containing `R&D <beta>` and a URL with `&` in the query string.
2. **Ties are not deterministic in live mode.** `rank_key()` only uses `(tier, urgency)`. Briefs are appended in `as_completed()` order, so with `--workers > 1` the order of accounts within the same tier and urgency changes from run to run. That affects the PDF and PT4's precision@k. Suggested tie-breaker: `account` name, or `deal_size_cad` desc (which would need it passed through). Mock mode is deterministic only because it uses one worker.
3. **Output directory is not created.** `SimpleDocTemplate` does not create parent directories. `--output new_dir/x.pdf` fails with a raw exception. It works today only because `out/` already exists in the working tree.
4. **Mixed-mode label.** The subtitle says "LIVE" if *any* brief is live. Mixed runs cannot happen through `main.py` today, but a caller of `render_pdf()` could produce one.
5. **Test coverage is thin for 3.2–3.4** (see the "Gap" notes under Acceptance criteria). PDF content checks would need a text extractor, for example `pypdf` as a dev-only dependency. Choosing it is a reasonable default for whoever adds the tests.
6. **`--limit 0`** is treated as "no limit" because of the truthy check. This is minor, but it is undocumented.
7. **Partial-failure UX.** Exit code `2` still writes a PDF, and failed accounts are listed only on stderr. The PDF itself does not mention omitted accounts.

Items 2–4 are concrete defects that could be fixed without design ambiguity. They are recorded here so Dev can pick them up, and they do not block approval of the as-built design.
