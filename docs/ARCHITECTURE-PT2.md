# PT2 Architecture: Web extraction & signal-finding

## Status

| Gate | Status |
|---|---|
| **Architecture** | **approved** |
| Dev (from WORKFLOW.md) | done |
| Review (from WORKFLOW.md) | approved |
| QA (from WORKFLOW.md) | passed *(manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass)* |

### Why draft (not approved)

This document describes PT2 as it is actually built. The design is complete, but the code
fails three of the acceptance criteria below, and each failure contradicts something
TASKS.md marks as `[x]`:

1. **AC-2.3 (SSRF guard) is not met for redirects.** `_fetch_via_requests()` calls
   `requests.get()` with the default `allow_redirects=True`. A public URL that 302-redirects
   to `http://127.0.0.1/...` or `http://169.254.169.254/...` gets past `is_safe_url()`,
   because the guard only checks the first URL. This is a real security gap.
2. **AC-2.2a (Tavily fallback) is not met for per-URL failures.** When Tavily returns the
   URL in `failed_results`, `_fetch_via_tavily()` returns a non-`None`
   `"[fetch failed: tavily - ...]"` string, so `fetch_and_extract()` never tries the
   requests+BeautifulSoup fallback. TASKS.md 2.2a says to fall back "if a Tavily call fails".
3. **AC-2.10 / AC-2.9 ("no network needed") are not met.** `fetch_and_extract()` always runs
   `is_safe_url()` first, and that calls `socket.gethostbyname()`. So
   `tests/test_fetch_tavily.py` (which uses `https://example.com/...`) and
   `test_allows_public_https_url` / `test_rejects_localhost` in
   `tests/test_fetch_safety.py` all need real DNS.

**Decision needed (not an architecture default):** do we reopen PT2 Dev to fix items 1–3,
using the remediation designs under "Acceptance criteria"? Or do we accept them as
documented limitations and approve as-is? Fixing them means resetting Dev/Review/QA for PT2,
which is a workflow decision for the user. The recommendation is to fix item 1 at minimum,
because it is a security issue.

---

## Scope

Source of truth: [TASKS.md](../TASKS.md) PT2, subtasks 2.1–2.10 (all marked `[x]`). This
document does not repeat the checkboxes. It maps each one to code and to an acceptance
criterion.

**In scope:** turn one `Account` into one `OpportunityBrief`, either live (Claude +
`web_search` + `fetch_url`) or mock (deterministic, offline). This covers the fetch backend
(Tavily or requests+BS4), the SSRF guard, the tool-use loop, JSON parsing and validation,
retries, and the tests for the fetch layer.

**Out of scope:** loading workbooks (PT1), parallel orchestration across accounts (lives in
`main.py`; PT4 plans to extract it to `plugin/orchestrate.py`), ranking/rendering (PT3), and
evaluating signal quality (PT4).

## Files / modules

| File | Responsibility | Subtasks |
|---|---|---|
| `plugin/research.py` | Tool definitions (`WEB_SEARCH_TOOL`, `FETCH_TOOL`), `SYSTEM_PROMPT`, `_account_prompt()`, `_extract_json()`, `_run_tool_loop()`, `research_account()` | 2.1, 2.4, 2.5, 2.6, 2.7 |
| `plugin/fetch.py` | `is_safe_url()` SSRF guard, `_fetch_via_tavily()`, `_fetch_via_requests()`, `fetch_and_extract()` dispatcher | 2.2, 2.2a, 2.3 |
| `plugin/mock.py` | `mock_research_account()` plus the `_STAGE_TIER` / `_STAGE_URGENCY` tables | 2.8 |
| `plugin/schema.py` | `Account`, `Source`, `OpportunityBrief` (shared with PT1/PT3/PT4) | 2.6 |
| `tests/test_fetch_safety.py` | 6 tests on `is_safe_url()` | 2.9 |
| `tests/test_fetch_tavily.py` | 4 tests on backend selection (Tavily / fallback / no key / blocked) | 2.10 |
| `requirements.txt` | `anthropic`, `requests`, `beautifulsoup4`, `tavily-python` (optional at runtime: an `ImportError` triggers fallback) | 2.2a |
| `.env.example` | `ANTHROPIC_API_KEY`, `OPPORTUNITY_RADAR_MODEL`, `TAVILY_API_KEY` (optional) | 2.1, 2.2a |

Caller: `main.py::_research_one()` lazily imports `plugin.research.research_account`, so
running with `--mock` never imports `anthropic`.

## Configuration / constants

| Name | Where | Value | Meaning |
|---|---|---|---|
| `MODEL` | research.py | env `OPPORTUNITY_RADAR_MODEL`, default `claude-sonnet-4-5` | Model used for research |
| `MAX_TOOL_ROUNDS` | research.py | `4` | Maximum `messages.create` calls per attempt |
| `WEB_SEARCH_TOOL.max_uses` | research.py | `4` | Server-side search cap per request |
| `max_tokens` | research.py | `2000` | Per-call output cap |
| `max_retries` / `sleep_s` | `research_account()` kwargs | `2` / `1.5` | 3 attempts total, with linear backoff of 1.5s then 3.0s |
| `_TIMEOUT_S` | fetch.py | `8` | requests timeout |
| `_MAX_BYTES` | fetch.py | `2_000_000` | Raw HTML read cap |
| `max_chars` | `fetch_and_extract()` kwarg | `6000` | Cap on returned text, both backends |
| `_USER_AGENT` | fetch.py | `OpportunityRadarBot/1.0 (...)` | requests backend only |
| `TAVILY_API_KEY` | env | optional | If present, Tavily is tried first |

## Data schemas

Defined in `plugin/schema.py`. PT2 produces `OpportunityBrief` and does not change the schema.

```python
Tier = Literal["A", "B", "C"]
Urgency = Literal["High", "Medium", "Low"]

class Account(BaseModel):            # input (from PT1)
    name: str; industry: str; deal_stage: str
    deal_size_cad: Optional[float] = None
    last_activity: Optional[str] = None
    rep_notes: Optional[str] = None             # synthetic
    market_signal_hint: Optional[str] = None    # synthetic
    relationship_context: Optional[str] = None  # synthetic

class Source(BaseModel):
    title: str
    url: str                                    # NOT validated as a URL (see risks)

class OpportunityBrief(BaseModel):   # output
    account: str; industry: str               # copied from Account, never from the model
    tier: Tier; urgency: Urgency
    signal_summary: str; why_now: str; recommended_action: str
    warm_path: Optional[str] = None
    sources: list[Source] = []
    confidence: Literal["High", "Medium", "Low"] = "Medium"
    data_mode: Literal["live", "mock"] = "live"
```

**Model reply contract** (from `SYSTEM_PROMPT`): a single JSON object with keys `tier`,
`urgency`, `signal_summary`, `why_now`, `recommended_action`, `warm_path`,
`sources[{title,url}]`, `confidence`. Mapping rules in `research_account()`:

- `account` and `industry` always come from the input `Account`.
- `sources` entries without a truthy `url` are dropped. An entry missing `title` raises,
  which triggers a retry.
- If `confidence` is missing, it defaults to `"Medium"`.
- `data_mode` is always `"live"`.

**`fetch_url` tool result contract:** always a `str`. It is either extracted text of at most
`max_chars`, or a sentinel that starts with `"[fetch failed: "`. Sentinels currently
produced:

- `blocked - <reason>`
- `tavily - <error>`
- `unsupported content-type '<ct>'`
- `no extractable text`
- `<RequestException subclass name>`

PT4 4.3 relies on the `"[fetch failed"` prefix.

## Flow

```
                         main.py::_research_one(account, mock)
                                       |
                    +------------------+------------------+
                 mock=True                             mock=False
                    |                                     |
     plugin/mock.py::mock_research_account     plugin/research.py::research_account
     (stage -> tier/urgency tables,             (lazy `import anthropic`)
      "[MOCK] ..." text, sources=[],                      |
      confidence=Low, data_mode=mock)          for attempt in 0..max_retries:  <-------------+
                    |                                     |                                  |
                    |                          _run_tool_loop(client, account)               |
                    |                            messages=[user: _account_prompt()]          |
                    |                            for round in 0..MAX_TOOL_ROUNDS-1:          |
                    |                              resp = messages.create(                   |
                    |                                system=SYSTEM_PROMPT,                   |
                    |                                tools=[web_search(server), fetch_url])  |
                    |                              append assistant resp.content             |
                    |                              fetch_calls = tool_use blocks             |
                    |                                            named "fetch_url"           |
                    |                              none? -> return joined text blocks ---+   |
                    |                              else for each call:                   |   |
                    |                                fetch_and_extract(url) --+          |   |
                    |                                append user tool_results |          |   |
                    |                            exceeded -> RuntimeError ----|----------|---+ (retry)
                    |                                                         |          |
                    |                         +-------------------------------+          |
                    |                         v                                          v
                    |          plugin/fetch.py::fetch_and_extract(url)      _extract_json(text)
                    |            is_safe_url(url)                            json.loads, else
                    |              scheme in {http,https}?                   greedy {.*} regex
                    |              hostname present, not *.local?                    |
                    |              gethostbyname -> not metadata/private/     OpportunityBrief(...)
                    |                loopback/link-local/reserved/multicast   (Pydantic validates;
                    |              fail -> "[fetch failed: blocked - ...]"     failure -> retry)
                    |            TAVILY_API_KEY set?                                 |
                    |              yes -> _fetch_via_tavily                          |
                    |                     ImportError/exception/no content -> None   |
                    |                     failed_results -> "[fetch failed: tavily]" |
                    |                     (does NOT fall back - gap #2)              |
                    |              None -> _fetch_via_requests                       |
                    |                     GET (follows redirects - gap #1),          |
                    |                     html only, <=2MB, strip script/style/      |
                    |                     nav/footer/header/noscript, <=max_chars    |
                    v                                                                v
              OpportunityBrief(data_mode="mock")               OpportunityBrief(data_mode="live")
                                                     after all retries fail: RuntimeError(... ) from last_err
```

## Interfaces

```python
# plugin/research.py
MODEL: str
MAX_TOOL_ROUNDS: int = 4
WEB_SEARCH_TOOL: dict        # {"type": "web_search_20250305", "name": "web_search", "max_uses": 4}
FETCH_TOOL: dict             # name "fetch_url", input_schema {url: string}, required ["url"]
SYSTEM_PROMPT: str
def _account_prompt(account: Account) -> str
def _extract_json(text: str) -> dict                       # raises ValueError / JSONDecodeError
def _run_tool_loop(client, account: Account) -> str        # raises RuntimeError past MAX_TOOL_ROUNDS
def research_account(account: Account, *, max_retries: int = 2, sleep_s: float = 1.5) -> OpportunityBrief
    # raises RuntimeError("research_account failed for '<name>' after retries") from last_err

# plugin/fetch.py
def is_safe_url(url: str) -> tuple[bool, str]              # (ok, reason); never raises on bad input
def _fetch_via_tavily(url: str, max_chars: int) -> str | None   # None = "fall back"
def _fetch_via_requests(url: str, max_chars: int) -> str
def fetch_and_extract(url: str, max_chars: int = 6000) -> str   # documented never-raise

# plugin/mock.py
def mock_research_account(account: Account) -> OpportunityBrief
```

Downstream dependencies on these interfaces:

- PT4 reuses `fetch_and_extract`, `_extract_json`, `MODEL`, `research_account`,
  `mock._STAGE_TIER`, and the `"[fetch failed"` sentinel prefix.
- `main.py` uses `research_account` and `mock_research_account`.
- Changing any of these signatures is a breaking change for PT4.

## Acceptance criteria (one per subtask)

Status legend: **MET** (code meets it, and a test exists where noted) · **MET (untested)**
(true by inspection, no automated test) · **NOT MET** (gap, with the remediation design).

| # | Acceptance criterion | Status |
|---|---|---|
| 2.1 | Every `client.messages.create` call in `_run_tool_loop` passes `tools` containing a dict with `type == "web_search_20250305"` and `name == "web_search"`. No local crawler/search code exists in `plugin/`. | MET (untested) |
| 2.2 | `FETCH_TOOL["name"] == "fetch_url"` and its `input_schema.required == ["url"]`. For any `str` input, `fetch_and_extract()` returns a `str` that either has `len <= max_chars` or starts with `"[fetch failed: "`, and never raises. | MET for the documented paths. Partial for never-raise: see risk R4 |
| 2.2a | (a) With `TAVILY_API_KEY` unset, `_fetch_via_tavily` is never called. (b) With it set and `_fetch_via_tavily` returning `None`, `_fetch_via_requests` is called once. (c) With it set and Tavily returning the URL in `failed_results`, `_fetch_via_requests` is still called. | (a)(b) MET, tested in `test_fetch_tavily.py`. **(c) NOT MET.** Remediation: `_fetch_via_tavily` returns `None` on `failed_results` (or `fetch_and_extract` treats a `"[fetch failed: tavily"` result as "fall back"), plus one test that stubs `TavilyClient.extract` to return `{"results": [], "failed_results": [{"url": u, "error": "x"}]}` and asserts the requests backend runs. |
| 2.3 | `is_safe_url` rejects non-http(s) schemes, a missing hostname, `*.local`, DNS failure, `169.254.169.254`, and loopback/private/link-local/reserved/multicast IPs. `fetch_and_extract` calls neither backend for a rejected URL. No redirect from an allowed URL can reach a rejected address. | First two parts MET (tested). **Redirect part NOT MET.** Remediation: in `_fetch_via_requests`, use `allow_redirects=False` and follow `Location` manually up to 3 hops, running `is_safe_url()` on each hop. Test: stub a 302 to `http://127.0.0.1/` and assert the result starts with `"[fetch failed: blocked"`. |
| 2.4 | With a stub client whose round 1 response has one `fetch_url` `tool_use` block and round 2 has only a text block, `_run_tool_loop` calls `fetch_and_extract` once, sends a `tool_result` with the matching `tool_use_id`, and returns the round-2 text. A stub that requests `fetch_url` every round raises `RuntimeError` after exactly `MAX_TOOL_ROUNDS` `create` calls. | MET (untested). Recommended test: `tests/test_research_loop.py` |
| 2.5 | `SYSTEM_PROMPT` contains the instruction never to cite synthetic CRM context as a signal. In `_account_prompt()`, every line derived from a CRM field other than name/industry is prefixed `"Synthetic"`. The hint line also says `"not a real fact"`. | MET (untested). Behavioural check is PT4 4.2 (leakage) |
| 2.6 | `_extract_json` parses (a) a bare JSON object and (b) a JSON object surrounded by prose. Given a valid payload, `research_account` returns an `OpportunityBrief` with `account`/`industry` taken from the input `Account`, `data_mode == "live"`, and sources without `url` dropped. An invalid `tier` value causes a retry, not a malformed brief. | MET (untested) |
| 2.7 | With `max_retries=2` and a stub that always fails, `research_account` attempts exactly 3 times, sleeps `sleep_s*1` then `sleep_s*2` between attempts, and raises `RuntimeError` with `__cause__` set to the last exception. A stub that fails once then succeeds returns a brief. | MET (untested) |
| 2.8 | `mock_research_account` needs no network or `anthropic` import, is deterministic, and returns `data_mode == "mock"`, `confidence == "Low"`, `sources == []`, and text fields prefixed `"[MOCK]"`. Tier/urgency follow `_STAGE_TIER`/`_STAGE_URGENCY`, with `"C"`/`"Low"` for unknown stages. | MET, exercised by `tests/test_mock_pipeline.py` |
| 2.9 | `tests/test_fetch_safety.py` asserts rejection of `file://`, `localhost`, `127.0.0.1`, `169.254.169.254`, and `10.0.0.5`, and acceptance of a public https URL, **with no network access**. | Assertions MET. **"No network" NOT MET**: the `localhost` and public-URL tests call real `gethostbyname`. Remediation: monkeypatch `plugin.fetch.socket.gethostbyname` in those tests. |
| 2.10 | `tests/test_fetch_tavily.py` covers Tavily-used, Tavily-returns-None fallback, no-key skip, and blocked-URL-reaches-neither, **with no real key or network**. | Cases MET. **"No network" NOT MET**: the three `example.com` tests resolve DNS through `is_safe_url`. Remediation: patch `plugin.fetch.is_safe_url` to return `(True, "ok")` in those three tests. |

## Open risks / known limitations

- **R1 (security, gap #1): redirect-based SSRF bypass** in the requests backend. See AC-2.3.
- **R2: DNS rebinding / TOCTOU.** `is_safe_url` resolves the hostname once with
  `gethostbyname` (IPv4, first address only), then `requests` resolves it again. A
  rebinding host could return a different IP the second time. The full fix is to connect to
  the already-validated IP with the original Host/SNI. The cost is moderate, so this is
  acceptable for the prototype and documented here. For IPv6-only hosts, `gethostbyname`
  fails, which errs safe (rejected).
- **R3: Tavily per-URL failure does not fall back** (gap #2). See AC-2.2a. The Tavily
  response parsing in `_fetch_via_tavily` (the `results` url matching and `failed_results`)
  has no tests at all, because every test patches the whole function. The
  `extract(urls=..., extract_depth="basic", format="text")` call signature has not been
  checked against the pinned `tavily-python>=0.8.0`.
- **R4: never-raise is not airtight.** `_fetch_via_requests` only catches
  `requests.exceptions.RequestException`. `resp.raw.read()` can raise
  `urllib3.exceptions.ProtocolError`/`DecodeError`, and BeautifulSoup can raise on
  pathological input. Either would escape into `_run_tool_loop` and fail the whole attempt.
  Separately, the `stream=True` response is never closed, which leaks connections under
  parallel workers.
- **R5: `pause_turn` / `stop_reason` are not handled.** `_run_tool_loop` decides "done"
  only by checking for `fetch_url` blocks. If the server-side web_search turn ends with
  `stop_reason == "pause_turn"`, or the output is truncated at `max_tokens=2000`, the
  partial text goes to `_extract_json`. That fails and burns a full retry, i.e. extra
  search spend.
- **R6: the fetch-count cap is enforced only by the prompt.** "At most twice per account"
  lives only in the prompt and tool description. Code allows up to `MAX_TOOL_ROUNDS` rounds
  with any number of parallel `fetch_url` calls per round. If the final answer comes in the
  same round as the 4th tool round, the attempt raises.
- **R7: `_extract_json`'s greedy `\{.*\}` regex** spans from the first `{` to the last `}`.
  If prose contains braces (or there are two JSON objects), parsing fails, which costs a
  retry rather than producing a wrong result.
- **R8: retries don't distinguish failure types.** Auth or invalid-model errors are retried
  3 times for nothing. Backoff is linear, not exponential. The Anthropic SDK's own internal
  retries stack on top of this.
- **R9: source URLs are not validated** in `Source` or in `research_account`. PT4 4.1
  catches malformed URLs after the fact.
- **R10: synthetic/real separation is enforced only by the prompt.** No code-level guard;
  PT4 4.2 (leakage) is the planned detector.
- **R11: no unit tests for `research.py`** (2.4/2.6/2.7). TASKS.md doesn't require them
  explicitly, but those acceptance criteria are currently verified only by inspection.
