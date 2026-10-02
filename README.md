# Media-Opportunity Radar

Turns a sheet of accounts into a ranked, rep-ready PDF of media/advertising opportunity briefs. Each brief combines **real web signals** (cited) with **synthetic CRM context** (kept clearly separate).

## 1. Approach and architecture

```
 .xlsx / .csv ──► loader.py ──► Account[]            (header validated, blanks -> None)
                                   │  ThreadPool (--workers, default 4)
                                   ▼
                  research.py: one Claude tool-use loop per account
                    ├─ web_search   (Anthropic server-side, max 4 uses)  discovery + warm path
                    ├─ fetch_url    (fetch.py: Tavily or requests+BS4)   verify one URL in full
                    └─ final JSON   tier, urgency, signal, why_now, action, warm_path, sources, confidence
                                   │  pydantic validation, 2 retries
                                   ▼
                  rank.py (tier, then urgency) ──► render_pdf.py ──► out/briefs.pdf
```

**Why this design**
- **One agentic loop per account, not a fixed RAG pipeline.** Signals are fresh and company-specific, so live search beats a stored corpus. This is why there are no embeddings or vector store.
- **Server-side `web_search` + one narrow `fetch_url`.** Search handles discovery with citations. Fetch is only for verifying a claim on an authoritative page (capped by `MAX_FETCH`).
- **Fact/fiction separation.** CRM data is labelled synthetic in the prompt and may only shape `recommended_action` and `warm_path`. It is never cited as a signal.
- **Structured output, validated.** JSON is parsed and checked against the pydantic schema, so a bad response is retried and then reported, not rendered.
- **Deterministic ranking and rendering.** No LLM in `rank.py` or the PDF, so ordering is reproducible.
- **Per-account isolation.** One failure does not lose the run (exit code `2`, PDF still written).
- **`--mock`** gives an offline, deterministic path for tests and demos.

## 2. How to run

**API keys (put both in `.env`, which is gitignored and loaded automatically)**

| Key | Needed for | Required? | Where to get it |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Research loop and Claude `web_search`; also the LLM judge in live evals | **Yes** for live runs (not for `--mock`) | console.anthropic.com |
| `TAVILY_API_KEY` | `fetch_url` page extraction (better on JavaScript-heavy pages) | Recommended, not strictly required: without it, extraction falls back to local requests + BeautifulSoup | tavily.com |

`TAVILY_ENABLED=false` forces the local extractor even if a key is set. Both services bill per use, so start with `--limit 3`.

```bash
pip install -r requirements.txt
cp .env.example .env        # set ANTHROPIC_API_KEY and TAVILY_API_KEY; optional MAX_FETCH, OPPORTUNITY_RADAR_MODEL

python main.py --input data/accounts.xlsx --sheet "Sample Accounts" --output out/briefs.pdf   # live
python main.py --input accounts.csv --limit 3        # CSV works too (header must match exactly)
python main.py --mock                                 # offline, no key
```

| Exit code | Meaning |
|---|---|
| 0 | all briefs written |
| 1 | no briefs produced |
| 2 | partial: PDF written, failed accounts listed |

### Run as a Claude Code plugin (local): `/sjc-radar:radar`

The repo is itself a plugin: manifest `.claude-plugin/plugin.json` (name `sjc-radar`), skill `skills/radar/SKILL.md`. The skill name becomes the command, so the plugin name plus the skill name gives `/sjc-radar:radar`.

**One-time setup**

```bash
cd /path/to/SJC
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY (optional TAVILY_API_KEY); the app loads it itself
```

**Option A: load for one session (quickest, good for development)**

```bash
cd /path/to/SJC               # start from the repo root so main.py and .env resolve
claude --plugin-dir .         # or an absolute path: claude --plugin-dir /path/to/SJC
```

A plugin can only be added at startup. If a `claude` session is already open, exit it and relaunch with the flag.

**Option B: install persistently through a local marketplace**

1. Add `.claude-plugin/marketplace.json` next to `plugin.json`:
   ```json
   {
     "name": "sjc-local",
     "owner": { "name": "SJC" },
     "plugins": [{ "name": "sjc-radar", "source": "./" }]
   }
   ```
2. In any Claude Code session:
   ```
   /plugin marketplace add /path/to/SJC
   /plugin install sjc-radar@sjc-local
   ```
3. Restart or run `/reload-plugins`. The plugin is now available in every session.

**Use it** (inside the Claude Code session)

```
/sjc-radar:radar data/accounts.xlsx     # live, keys from .env
/sjc-radar:radar accounts.csv           # CSV works too
/sjc-radar:radar --mock                 # offline, no key
```

Claude asks for confirmation before a live run on more than a few accounts. Start with `--limit 3`. The PDF is written to `out/briefs.pdf`.

**Troubleshooting**

| Symptom | Fix |
|---|---|
| `/sjc-radar:radar` doesn't autocomplete | Run `/plugin` and check `sjc-radar` is listed and enabled. For option A, confirm you launched with `--plugin-dir`. |
| Edited `SKILL.md` or the manifest, nothing changed | `/reload-plugins`, or restart `claude` |
| `No such file` or `.env` not found | Start `claude` from the repo root. The skill runs `main.py` in the plugin directory, but your input path is relative to your session's working directory, so use an absolute path if they differ. |
| Skill ran in mock when you wanted live | Say "live". The skill defaults to mock only when no preference is given and no key is set. |
| `command not found: pip` | Use `python3 -m pip install -r requirements.txt` |

Reference run (live, 2 accounts, 4 workers): **~40 s wall time, 2/2 succeeded**.

## 3. Model choice: cost vs performance

| Stage | Best fit | Why |
|---|---|---|
| Query building | Haiku 4.5, or GPT-4o-mini / Llama 3.x 8B | Simple task, so cheap and fast wins |
| Page extraction | No LLM (Tavily / BS4) | Already deterministic and free |
| Analysis + synthesis | **Sonnet** (code default `claude-sonnet-4-5`; recommended upgrade `claude-sonnet-5-5`), or GPT-4.1 / GPT-5-class | Needs strict JSON, fact/CRM separation, calibrated tiering |
| Hard accounts, second-pass review | Opus 5.5 / Fable 5.1 | Only if Sonnet's tiering proves noisy |
| Ranking, PDF | No LLM | Deterministic |

| Option | Cost | Quality on this task | Catch |
|---|---|---|---|
| **Claude Sonnet (current, `claude-sonnet-4-5`)** | Mid | High; native `web_search` + citations | Anthropic-only search tool |
| OpenAI (GPT-4.1 / mini) | Comparable; mini is cheapest | High, with similar JSON reliability | Replace `web_search` with the OpenAI search tool or Tavily, and rework the tool loop |
| Open source (Llama 3.x 70B, Qwen 2.5 72B) | Lowest per token if self-hosted; GPU/ops cost otherwise | Fine for query building; weaker at grounded synthesis and citation discipline | You must supply search and fetch, add JSON-repair, and re-run evals |

**Recommendation:** keep one strong Sonnet-class model for the whole loop. The code runs `claude-sonnet-4-5` by default (`plugin/research.py`); `claude-sonnet-5-5` is the suggested upgrade, untested here, so run the evals first. Split out a cheap model for query building only if cost becomes the bottleneck. Use open-source only where data residency demands it. Re-run the evals (section 5) before any swap. Override the default with `OPPORTUNITY_RADAR_MODEL`.

### Search APIs: why hybrid, and what unnecessary searches cost

```
 discovery (what's new about X?)  ──► Claude web_search   ~4 per account, billed per search + result tokens
 verification (read THIS page)    ──► fetch_url ──► Tavily Extract, or free requests+BS4 fallback
```

| Approach | Strength | Weakness |
|---|---|---|
| Claude `web_search` only | Zero extra integration; cited snippets; model decides queries | Snippets only, so thin evidence; every search is a billed call plus result tokens |
| Tavily / fetch only | Full page text, cheap per call | No discovery; you must build queries and ranking yourself |
| **Hybrid (current)** | Search finds it, fetch confirms it on the company's own page. Higher trust, fewer wrong claims | Two integrations and two bills to watch |

**Why hybrid pays off:** full-page extraction through Tavily is cheaper than another model search round, and it grounds the claim in the source. If Tavily is down or unset, `fetch_url` falls back to local extraction, so the run never depends on one vendor. `TAVILY_ENABLED=false` turns it off.

**Cost of unnecessary Claude searches:** each search adds a per-search fee *and* pushes results back into the context, so every later round re-reads them. Costs grow with the number of searches times the number of rounds, not linearly.

| Lever | Setting | Effect |
|---|---|---|
| Cap searches per account | `max_uses` in `WEB_SEARCH_TOOL` (now 4) | Hard ceiling on search spend |
| Cap rounds | `MAX_TOOL_ROUNDS` (now 4) | Stops loops that never converge |
| Cap fetches | `MAX_FETCH` | Bounds Tavily and parsing cost |
| Skip low-value accounts | Filter early (for example `Discovery` stage, no signal hint) | No search at all |
| Cache per account | 24-72 h (production list) | Re-runs cost nothing |
| Cheap model for queries | Haiku 4.5 | Cuts model tokens, not the per-search fee |

Rule of thumb: start with `--limit 3`, read how many searches the briefs actually used, then tune `max_uses` down until the confidence and groundedness evals start to drop. Check current search pricing before budgeting.

## 4. What to change for production

| Area | Today | Change |
|---|---|---|
| Throughput and rate limits | ThreadPool, simple retries | Job queue, exponential backoff with jitter, per-key concurrency limits |
| Cost control | `MAX_FETCH`, 4 searches, 4 rounds | Per-run token and cost budget, per-account hard stop, prompt caching |
| Caching | None | Cache signals per account for 24-72 h (news barely changes hourly) |
| Observability | Print lines | Structured logs: tokens, latency, searches, fetches, failures per account |
| Resilience | Failed accounts are omitted | Dead-letter list plus retry-failed-only; partial results kept |
| Real CRM | Synthetic xlsx/csv | CRM connector (read-only), PII review, no CRM text in logs |
| Safety | SSRF/redirect guards in `fetch.py` | Domain allow/deny lists, robots/ToS check |
| Delivery | Local PDF | Scheduled runs, store to S3/Drive, Slack/email to rep |
| Model ops | One hard-coded default | Pin model versions, canary before upgrades, fallback model |
| Config | `.env` | Secret manager |

### Production view for Product and Tech (PM summary)

**Prototype today:** a rep or analyst runs one command on a spreadsheet and gets a PDF. **Production:** briefs arrive on a schedule, from the live CRM, inside the tools reps already use.

```
 TODAY      sheet ──► run on demand ──► PDF
 PRODUCTION CRM ──► scheduler/queue ──► research (cached, budgeted) ──► QA gates ──► Slack / email / CRM field
                                              │                                        │
                                       cost + quality dashboard  ◄── rep feedback (useful? accurate?)
```

| Question a PM will ask | Answer today | In production |
|---|---|---|
| **Who is it for and when do they see it?** | Whoever runs the command | Reps and managers, pushed weekly or on a trigger (new signal on a Tier A account) |
| **Where does it live?** | A local PDF | CRM account page or Slack digest, with the PDF as an export |
| **What does it cost?** | Pay per run, uncapped by account | Budget per run and per account, cached results, cost per brief tracked |
| **Can we trust it?** | Evals run by hand | Automated quality gate before delivery: bad briefs are held back, not sent |
| **What if it breaks?** | Failed accounts are skipped, exit code 2 | Retries, alerts, and a visible "could not research" status per account |
| **Who owns it?** | One developer | Named owner, on-call for the pipeline, PM owns the quality metric |
| **Data and compliance** | Synthetic CRM data | Real CRM means PII and access rules: read-only access, no CRM text in logs, legal review of data sources |
| **How do we improve it?** | Re-read the PDF | Thumbs up/down on each brief feeds the gold set and prompt changes |


**Decisions the PM should make early:** which accounts get researched (all, or Tier A/B only, since cost scales with account count); how fresh briefs must be (daily vs weekly drives cache and cost); who sees low-confidence briefs; and the success metric (rep adoption, meetings booked, pipeline influenced).

**Main risks:** confident but wrong claims (mitigated by citations and the groundedness check), reps ignoring output that feels generic (mitigated by feedback loop and `warm_path` specificity), and runaway search cost (mitigated by caps in section 3).

## Trade-offs and known gaps

| Area | Choice made | Gained | Cost / gap |
|---|---|---|---|
| Research | Agentic loop with live search, no embeddings or RAG | Fresh, company-specific signals | Cost and latency scale with accounts times searches |
| Research | CRM/real separation enforced by prompt, checked by eval | No extra code | Can slip through until the leakage eval catches it |
| Report | Deterministic rank (tier, then urgency), no LLM | Reproducible, free | No tie-breaker, so ties reorder when `--workers` > 1 |
| Report | Model text passed straight into ReportLab | Fast to build | A stray `<` or `&` in live output can fail the PDF build |
| Report | Partial failure still writes the PDF (exit 2) | Good briefs are kept | The PDF does not list omitted accounts |
| Evals | LLM judge for citations, capped per brief | Catches unsupported claims | Extra API cost; the judge can be wrong |

Details live in `docs/ARCHITECTURE-PT*.md` under "Open risks". Those notes predate some fixes, so check the code before relying on them.

## 5. Evaluating usefulness and accuracy

Built-in suite: `python -m evals.run_evals --mock` (offline) or `--input <file>` (live).

```
 structural ─► leakage ─► citation judge ─► ranking vs gold ─► run-to-run consistency ─► report
```

| Check | Question | Target |
|---|---|---|
| Structural | Valid schema, non-empty fields, tier/urgency enums | 100% |
| Leakage | Synthetic CRM text not presented as a real signal | 0 leaks |
| Groundedness (LLM judge) | Does the cited page support the claim? | >= 90% supported |
| Source validity | Citation URLs resolve and are non-hallucinated | >= 95% |
| Ranking vs gold fixture | Agreement with hand-labelled tiers | >= 80% exact, >= 95% within one tier |
| Consistency | Same tier/urgency across repeated runs | >= 85% agreement |
| Failure rate | Accounts failing after retries | < 2% |

**Usefulness (needs humans):** have 2-3 reps rate a sample of briefs on a 1-5 scale for "would I act on this?" and "was the warm path real?". Track the share of briefs that led to outreach, and meeting or pipeline rate against unbriefed accounts. Review `confidence: Low` briefs separately to confirm that "no signal found" is reported honestly.

**Cost and latency to track per run:** tokens per account, cost per account, p50/p95 seconds per account (reference ~20 s per account at 4 workers), search and fetch calls per account.

## 6. Implemented evals

Run with `python -m evals.run_evals` (add `--mock` for an offline run with no API key; live runs cost API calls). Each run prints a summary and writes `evals/out/latest.csv` plus a timestamped `report_<UTC>.csv`. Exit code is 0 only if overall PASS.

| Eval | What it checks | How | Pass rule | In `--mock` |
|---|---|---|---|---|
| 4.1 Structural | 3 checks per brief: `recommended_action` not empty, every source URL parses, High confidence has at least one source | Rule-based, no network | All pass | Runs |
| 4.2 Leakage | `signal_summary` is not a near-copy of the synthetic CRM hint | Text similarity ratio against the hint | Ratio below 0.9 | Skipped |
| 4.3 Citation | Each cited page supports the claim (up to 3 sources per brief, `--max-citations-per-brief`) | Fetch the page, then an LLM judge. A failed fetch or a judge error is a skip | Judge says supported | Skipped |
| 4.4 Ranking | Produced top-5 vs `evals/fixtures/gold_ranking.json` | precision@5 = overlap / 5 | precision@5 >= 0.6 (missing fixture = skip) | Runs |
| 4.5 Consistency | Tier and urgency are stable when an account is re-researched (`--consistency-sample 3` accounts, `--consistency-runs 2` extra runs) | Re-run research and compare tier and urgency; wording differences are ignored | Same tier and urgency across runs | Skipped (one skip row) |
| 4.6 Report | Roll-up of all of the above | One CSV row per check result, plus `_summary` rows and a final `overall_pass` row | No failed check and no research failures | Runs |

Notes: a fully skipped category scores 0.0 and does not fail the run. The LLM judge can be wrong, so treat citation failures as a prompt to spot-check. The gold ranking is provisional (seeded from the same deal-stage rule as the mock) until someone with sales context hand-labels it.
