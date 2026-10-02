---
name: radar
description: Run the Media-Opportunity Radar on an accounts spreadsheet (.xlsx) to produce a ranked PDF of opportunity briefs. Use when the user asks to run the radar, generate opportunity briefs, or rank accounts.
---

# Media-Opportunity Radar

Runs `main.py` from the plugin root (`${CLAUDE_PLUGIN_ROOT}`). Run all commands from that directory.

## Steps

1. Install dependencies if needed: `pip install -r requirements.txt`.
2. Pick a mode:
   - **Mock (default if the user gave no preference or `ANTHROPIC_API_KEY` is unset):** offline, no API key, deterministic stand-in data. Add `--mock`.
   - **Live:** real web research. Requires `ANTHROPIC_API_KEY` in the environment. Optional: `TAVILY_API_KEY`. Live runs cost API calls, so confirm with the user before running on more than a few accounts, and suggest `--limit 3` first.
3. Run:
   ```
   python main.py --input <xlsx> --sheet "<sheet>" --output out/briefs.pdf [--limit N] [--workers N] [--mock]
   ```
   Defaults: `--input data/sample_accounts.xlsx`, `--sheet "Sample Accounts"`, `--output out/briefs.pdf`, `--workers 4`.
4. Report the output PDF path and how many briefs were written. Do not paste the whole PDF contents.

## Exit codes

- `0`: success.
- `1`: no briefs were produced.
- `2`: partial failure. The PDF was still written, but some accounts failed. Say which ones (listed in the script's output).

## Input format

The sheet header must match exactly, in order, with no extra columns. If the script reports a header mismatch, show the user the expected and actual headers.
