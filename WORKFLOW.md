# Workflow Status

Gate order, per PT (see [TASKS.md](TASKS.md) for subtask detail): **Architecture → Dev →
Review → QA**, enforced in that order:

- The **dev** agent will not start on a PT until that PT's `Architecture: approved`.
- The **review** agent evaluates a PT only once `Dev: done`.
- The **qa** agent runs checks only once `Review: approved`, and only opens a PR if lint +
  unit tests + integration checks all pass.

Each agent updates only its own status line (and its own detail subsection) for the PT it was
asked to work on. Don't hand-edit another agent's line without re-running that agent.

---

## PT1 — Input ingestion & company profiling
- Architecture: approved 
- Dev: done
- Review: approved
- QA: passed *(manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass)*
- Architecture doc: [docs/ARCHITECTURE-PT1.md](docs/ARCHITECTURE-PT1.md)

## PT2 — Web extraction & signal-finding
- Architecture: approved 
- Dev: done
- Review: approved
- QA: passed *(manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass)*
- Architecture doc: [docs/ARCHITECTURE-PT2.md](docs/ARCHITECTURE-PT2.md)

## PT3 — Report generation
- Architecture: approved 
- Dev: done
- Review: approved
- QA: passed *(manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass)*
- Architecture doc: [docs/ARCHITECTURE-PT3.md](docs/ARCHITECTURE-PT3.md)

## PT4 — Evals
- Architecture: approved
- Dev: done
- Review: approved
- QA: passed (PR step skipped: no git repo/remote)

### PT4 Architecture

Moved to [docs/ARCHITECTURE-PT4.md](docs/ARCHITECTURE-PT4.md) (status: approved).

### PT4 Review notes
Verified against docs/ARCHITECTURE-PT4.md by reading code and running tests: `pytest -q` = 64 passed; `python -m evals.run_evals --mock` exits 0 (structural 36/36, ranking precision@5=0.80 pass, leakage/citation/consistency all skip); `main.py --mock` still exits 0 with unchanged `  ok    <name>` lines. Not run: ruff (not installed), live evals.
- AC-4.1 structural: met. 3 results/brief; empty fields named in detail; URL scheme+netloc check; High+no sources fails. Tests (a)-(e) present.
- AC-4.2 leakage: met. casefold/whitespace normalization, ratio>0.9 fails, ratio=<.3f> in detail, mock/no-hint skip. Tests (a)-(e) present.
- AC-4.3 citation: met. One skip for mock/no-sources; fetch-failed skips without calling judge; judge exception or non-bool output skips; cap respected; reasoning in fail detail; default judge imports anthropic/plugin.research lazily (C3). Tests (a)-(f) present, plus bad-judge-output.
- AC-4.4 ranking: met. Set-based precision, missing fixture skips, default path via __file__ (C6), seed key per C5. Fixture has 5 names matching sample accounts (test verifies).
- AC-4.5 consistency: met. Runs sequentially, tier/urgency decide, similarity informational, researcher exception skips, consistency_skipped_summary exposed. Tests (a)-(e) present.
- AC-4.6 report: met. overall_pass formula and print format match spec; write creates parent dirs. Tests (a)-(f) present.
- AC-4.7 CLI: met. Mock never imports plugin.research/anthropic (test purges sys.modules first per C4); latest.json + one report_*.json; zero-brief exit 1; research_failures fail overall (C10). Tests (a)-(d) present.
- AC-orchestrate: met. Input-order briefs (C2), on_result callback with no printing inside (C1), failures collected not raised. main.py output/exit codes unchanged. Tests present, incl. failure case.
- C12: met. evals/out/ is in .gitignore. No plugin/ file imports evals/. No secrets, no unguarded network call (citation fetch goes through plugin.fetch).
Non-blocking nits (no change required):
- evals/ranking.py: a fixture with k=0 or malformed JSON raises (ZeroDivisionError/KeyError/JSONDecodeError) instead of skipping; only the missing-file case is defensive. Consider guarding if the fixture is hand-edited.
- evals/out/ contains stray report files from dev runs (gitignored, harmless).
- _print_result is duplicated in main.py and evals/run_evals.py (a few lines; acceptable).

### PT4 QA notes
1. Lint: `python3 -m ruff check .` ran (ruff 0.15.15 is available, despite the expected-missing note) - All checks passed. `compileall -q evals plugin main.py tests` also exit 0 (pyflakes not installed).
2. Unit tests: `python3 -m pytest -q` - 64 passed, 1 urllib3/LibreSSL warning (unrelated).
3. Integration: `python3 -m evals.run_evals --mock` exit 0 (structural 36/36, ranking precision@5=0.80 pass, leakage/citation/consistency skipped, OVERALL: PASS). `python3 main.py --mock --output out/briefs_mock.pdf` exit 0, wrote 12 briefs, PDF present (14697 bytes). Live evals/research not run (API cost).
4. PR: skipped - directory is not a git repository and has no remote; no git commands run.
