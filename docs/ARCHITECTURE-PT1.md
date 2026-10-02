# PT1 Architecture: Input ingestion and company profiling

## Status

- Architecture: approved 
- Dev: done *(copied from WORKFLOW.md. Note: TASKS.md 1.6 is still unchecked, so "done" applies to 1.1 to 1.5 only. 1.6 needs a dev pass.)*
- Review: approved *(copied from WORKFLOW.md)*
- QA: passed *(copied from WORKFLOW.md: "manually verified via `pytest`/`ruff` in-session; not yet run as a formal QA pass")*

## Scope

Scope comes from [TASKS.md](../TASKS.md) PT1, subtasks 1.1 to 1.6, and the checkboxes there are the source of truth. PT1 takes an `.xlsx` path and sheet name from the CLI, validates the sheet's header and turns each non-empty row into a normalized `Account` profile that PT2 (research/mock), PT3 (rank/render) and PT4 (evals) all consume.

PT1 does not cover web research, ranking, rendering or any network access. PT1 is fully offline.

| Subtask | State | Where |
|---|---|---|
| 1.1 CLI `--input`, `--sheet` | built | `main.py` `parse_args()` |
| 1.2 Parse workbook, validate header, fail fast | built (header-mismatch path untested, see Gaps) | `plugin/loader.py` |
| 1.3 Normalize row into `Account` | built | `plugin/schema.py`, `plugin/loader.py` |
| 1.4 Optional synthetic fields tolerate `None` | built | `Optional[...]` fields in `Account` |
| 1.5 Unit tests: row count, optional-field presence/absence | built | `tests/test_loader.py` |
| 1.6 Friendly CLI error for a missing file or wrong sheet | **not built**. Designed below | `plugin/loader.py`, `main.py`, `tests/test_loader.py`, `tests/test_cli_errors.py` |

## Files / modules

| File | Responsibility |
|---|---|
| `/Users/vidipmalhotra/SJC/main.py` | `parse_args()` defines `--input` (default `data/sample_accounts.xlsx`) and `--sheet` (default `"Sample Accounts"`). `main()` calls `load_accounts(args.input, sheet_name=args.sheet)` and then applies `--limit` by slicing. |
| `/Users/vidipmalhotra/SJC/plugin/loader.py` | `EXPECTED_HEADER` constant (8 columns). `load_accounts()` opens the workbook with `openpyxl.load_workbook(path, data_only=True)`, selects the sheet, does an exact-list header compare, skips rows whose first cell is falsy and builds `Account` objects. |
| `/Users/vidipmalhotra/SJC/plugin/schema.py` | The `Account` Pydantic model, which is the PT1 output contract. It also holds `Source` and `OpportunityBrief`, which belong to PT2 and PT3. |
| `/Users/vidipmalhotra/SJC/tests/test_loader.py` | Tests that 12 accounts load, that known names are present, that Bell Canada's hint and notes are `None`, and that dentsu Canada's hint is not `None`. |
| `/Users/vidipmalhotra/SJC/data/sample_accounts.xlsx` | The sample input, with 12 data rows. |

## Data schemas

Input sheet header. It must match exactly, in this order, with no extra columns:

| Col | Header | Maps to | Default when the cell is empty |
|---|---|---|---|
| 0 | `Account Name (Real Company)` | `name: str` | the row is skipped |
| 1 | `Industry` | `industry: str` | `"Unknown"` |
| 2 | `Synthetic Deal Stage` | `deal_stage: str` | `"Unknown"` (mock maps this to tier C, urgency Low) |
| 3 | `Synthetic Deal Size (CAD)` | `deal_size_cad: Optional[float]` | `None` |
| 4 | `Synthetic Last Activity` | `last_activity: Optional[str]` | `None` |
| 5 | `Synthetic Rep Notes` | `rep_notes: Optional[str]` | `None` |
| 6 | `Hypothetical Market Signal` | `market_signal_hint: Optional[str]` | `None` |
| 7 | `Hypothetical Relationship Context` | `relationship_context: Optional[str]` | `None` |

```python
class Account(BaseModel):          # plugin/schema.py, the PT1 output contract
    name: str
    industry: str
    deal_stage: str
    deal_size_cad: Optional[float] = None
    last_activity: Optional[str] = None
    rep_notes: Optional[str] = None
    market_signal_hint: Optional[str] = None
    relationship_context: Optional[str] = None
```

These modules depend on `Account` and must not break if it changes: `plugin/mock.py` (uses `deal_stage`, `market_signal_hint`, `last_activity`, `rep_notes` and `relationship_context`), `plugin/research.py` (prompt construction, around lines 84 to 93) and the PT4 evals design in WORKFLOW.md (uses `market_signal_hint` for the leakage check and `name` for brief matching).

## Flow

```
 CLI (main.py)
   --input PATH  --sheet NAME
        |
        v
 load_accounts(path, sheet_name)                          plugin/loader.py
        |
        |-- openpyxl.load_workbook(path, data_only=True)  -> FileNotFoundError / InvalidFileException  [1.6 gap]
        |-- wb[sheet_name]                                -> KeyError                                  [1.6 gap]
        |-- rows[0] == EXPECTED_HEADER ?                  -> ValueError (clear message)                [1.2]
        |       (an empty sheet gives IndexError on rows[0])                                           [gap]
        |
        |-- for each data row:
        |       row[0] falsy?  -> skip
        |       else Account(name, industry or "Unknown", deal_stage or "Unknown",
        |                    deal_size_cad, last_activity, rep_notes,
        |                    market_signal_hint, relationship_context)
        |                       -> pydantic.ValidationError on a type mismatch                         [risk]
        v
 list[Account]  --(main.py: [:limit])-->  PT2 research / mock  -->  PT3 rank / render
                                    \-->  PT4 evals (planned)
```

## Interfaces

As built:

```python
# plugin/loader.py
EXPECTED_HEADER: list[str]   # 8 column names, see table above
def load_accounts(path: str, sheet_name: str = "Sample Accounts") -> list[Account]: ...
```

Errors as built: a header mismatch raises `ValueError` with the expected and actual headers in the message. A missing file, an unknown sheet or an empty sheet raises the raw `FileNotFoundError`, `KeyError` or `IndexError` from openpyxl or Python, and the traceback reaches the user. This is the 1.6 gap.

### 1.6 design (to be built)

1. In `plugin/loader.py`, add `class AccountsInputError(ValueError)`. Because it subclasses `ValueError`, any existing `except ValueError` caller and the header-mismatch behavior keep working.
2. Have `load_accounts()` raise `AccountsInputError` with a one-line, human-readable message in these cases:
   - The path does not exist (check `os.path.exists(path)` before opening): `Input file not found: '<path>'`.
   - openpyxl cannot open the file (`openpyxl.utils.exceptions.InvalidFileException`, `zipfile.BadZipFile`): `Could not read '<path>' as an .xlsx workbook: <exc>`. Chain the original with `raise ... from exc`.
   - The sheet name is not in `wb.sheetnames`: `Sheet '<sheet_name>' not found in '<path>'. Available sheets: [<names>]`.
   - The sheet has no rows: `Sheet '<sheet_name>' in '<path>' is empty`.
   - The header does not match: keep the current message text. Only the exception type changes, from `ValueError` to `AccountsInputError`.
3. In `main.py`, wrap the `load_accounts(...)` call. On `AccountsInputError as exc`, print `error: <exc>` to stderr and `return 3`. Print no traceback. Exit code 3 is new and distinct from the existing codes: 0 means success, 1 means no briefs, 2 means partial failure, and argparse also uses 2 for usage errors. Document the exit codes in the `main.py` module docstring. Do not change any other flag, stdout line or exit code.
4. Do not catch `pydantic.ValidationError` from bad cell types under 1.6. That is a separate risk, listed below, and would need its own subtask.

## Acceptance criteria

The review agent can check each one mechanically.

- **1.1:** `main.parse_args([])` gives `input == "data/sample_accounts.xlsx"` and `sheet == "Sample Accounts"`. `main.parse_args(["--input", "x.xlsx", "--sheet", "S"])` gives `input == "x.xlsx"` and `sheet == "S"`. `main()` passes both values to `load_accounts` (see `main.py:55`).
- **1.2:** `load_accounts("data/sample_accounts.xlsx")` returns without error. A workbook written to `tmp_path` with any header that differs from `EXPECTED_HEADER` (a renamed column, a reordered column or an extra column) raises `ValueError`, and the message contains both the expected and actual header lists. *Gap: there is no test for this today. Add it to `tests/test_loader.py` together with 1.6.*
- **1.3:** Every returned item is an `Account`. For any row with an empty `Industry` cell, `industry == "Unknown"`. For any row with an empty `Synthetic Deal Stage` cell, `deal_stage == "Unknown"`. A row with an empty first cell is not in the output. *(The behavior is built. A tmp_path test for the defaults and the row skip is recommended.)*
- **1.4:** Loading `data/sample_accounts.xlsx` does not raise. At least one account (Bell Canada) has `market_signal_hint is None` and `rep_notes is None`. `mock_research_account()` runs without exception on every loaded account, which `tests/test_mock_pipeline.py` already exercises.
- **1.5:** `pytest tests/test_loader.py` passes. It asserts `len(accounts) == 12`, that `"dentsu Canada"` and `"Bell Canada"` are present, that Bell Canada's `market_signal_hint` and `rep_notes` are `None`, and that dentsu Canada's `market_signal_hint` is not `None`.
- **1.6:** (a) `load_accounts("does/not/exist.xlsx")` raises `AccountsInputError`, and the message contains `"not found"` and the path. (b) `load_accounts("data/sample_accounts.xlsx", sheet_name="Nope")` raises `AccountsInputError`, and the message contains `"Nope"` and `"Sample Accounts"` (the available sheets). (c) A `tmp_path` workbook with an empty sheet raises `AccountsInputError`, not `IndexError`. (d) `issubclass(AccountsInputError, ValueError)` is true. (e) `main.main(["--input", "does/not/exist.xlsx", "--mock"])` returns `3`, captured stderr starts with `"error: "` and contains no `"Traceback"`. (f) `main.main(["--sheet", "Nope", "--mock"])` returns `3`. These live in `tests/test_loader.py` and a new `tests/test_cli_errors.py`, run fully offline.

## Open risks / gaps (documented, not blocking)

- **The WORKFLOW.md status overstates completion.** `Dev: done` and `QA: passed` predate 1.6, which is still unchecked in TASKS.md. Re-run dev, review and QA for 1.6 only. The architect did not edit those lines.
- **`last_activity` type coercion.** `data_only=True` makes openpyxl return real date cells as `datetime`. Pydantic v2 does not coerce `datetime` to `str`, so a workbook whose "Synthetic Last Activity" column is formatted as dates would fail with `ValidationError`. The sample file works today, presumably because it stores text. Possible fix in a future subtask: in the loader, format `datetime` values as `.date().isoformat()`.
- **`deal_size_cad` coercion.** Numeric cells are fine. A text cell such as `"250,000"` or `"$250k"` raises `ValidationError` and stops the whole load. No per-row error isolation exists.
- **Header strictness.** The compare is an exact list match, so trailing blank columns (formatted but empty cells beyond column H, which openpyxl reports as `None`) or stray whitespace in a header fail validation. This is intended fail-fast behavior per 1.2, but it may surprise users with real CRM exports.
- **Name handling.** `name` is not stripped, and a numeric account name fails `str` validation. A whitespace-only name is not skipped, because `" "` is truthy.
- **Resources.** The workbook is opened without `read_only=True` and never closed. This is fine at 12 rows but wasteful for large exports.
- **Coverage of the "6 of 12 rows" claim (1.4).** The tests check one empty row (Bell Canada) and one populated row (dentsu Canada). They do not check the 6/6 split. This is acceptable, but a count assertion would detect drift in the sample data.
