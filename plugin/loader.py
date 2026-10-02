"""Reads the 'Sample Accounts' sheet (.xlsx) or a CSV export of it into Account objects."""
from __future__ import annotations

import csv
from pathlib import Path

import openpyxl

from .schema import Account

EXPECTED_HEADER = [
    "Account Name (Real Company)",
    "Industry",
    "Synthetic Deal Stage",
    "Synthetic Deal Size (CAD)",
    "Synthetic Last Activity",
    "Synthetic Rep Notes",
    "Hypothetical Market Signal",
    "Hypothetical Relationship Context",
]


def _read_rows(path: str, sheet_name: str) -> list[tuple]:
    if Path(path).suffix.lower() == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            # Blank cells become None, matching openpyxl.
            return [tuple(c.strip() or None for c in row) for row in csv.reader(f)]
    wb = openpyxl.load_workbook(path, data_only=True)
    return list(wb[sheet_name].iter_rows(values_only=True))


def load_accounts(path: str, sheet_name: str = "Sample Accounts") -> list[Account]:
    """Load accounts from .xlsx (reads `sheet_name`) or .csv (single table; `sheet_name` ignored)."""
    rows = _read_rows(path, sheet_name)
    header, data_rows = rows[0], rows[1:]
    if list(header) != EXPECTED_HEADER:
        raise ValueError(
            f"Unexpected header in '{sheet_name}'. Expected {EXPECTED_HEADER}, got {list(header)}"
        )

    accounts = []
    for row in data_rows:
        name = row[0]
        if not name:
            continue
        accounts.append(
            Account(
                name=name,
                industry=row[1] or "Unknown",
                deal_stage=row[2] or "Unknown",
                deal_size_cad=row[3],
                last_activity=row[4],
                rep_notes=row[5],
                market_signal_hint=row[6],
                relationship_context=row[7],
            )
        )
    return accounts
