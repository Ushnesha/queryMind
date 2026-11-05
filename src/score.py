"""Small mechanical result comparison shared by evaluation and optimization."""

from __future__ import annotations

import json
from typing import Any


def normalize_result(rows: list[Any], columns: list[str]) -> dict[str, list[str]]:
    """Canonicalize unordered rows while preserving duplicates and column order.

    Row values retain their JSON types. This starter intentionally does not
    claim floating-point tolerance or semantic equivalence of arbitrary SQL.
    """
    return {
        "columns": list(columns),
        "rows": sorted(
            json.dumps(list(row), sort_keys=True, ensure_ascii=False, allow_nan=False)
            for row in rows
        ),
    }


def results_equal(
    rows_before: list[Any],
    columns_before: list[str],
    rows_after: list[Any],
    columns_after: list[str],
) -> bool:
    """Compare result multisets, including duplicate counts and column labels."""
    return normalize_result(rows_before, columns_before) == normalize_result(rows_after, columns_after)
