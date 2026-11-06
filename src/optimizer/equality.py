"""Equivalence gate: a rewrite is accepted only if its results match the original."""

import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import monotonic
from typing import Any

from src.db import _mask_literals_and_comments, connect_readonly, validate_readonly
from src.score import results_equal as _multiset_equal

TIMEOUT_S = 10.0


def _norm_cell(value: Any) -> Any:
    """Round floats to 6 decimals; tag BLOBs so JSON can compare them. None stays None."""
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else str(value)
    if isinstance(value, bytes):
        return {"type": "blob", "hex": value.hex()}
    return value


def _norm_rows(rows: list[Any]) -> list[list[Any]]:
    return [[_norm_cell(v) for v in row] for row in rows]


def compare_results(
    original_rows: list[Any],
    original_columns: list[str],
    candidate_rows: list[Any],
    candidate_columns: list[str],
    *,
    ordered: bool = False,
) -> bool:
    """Compare results. Unordered multiset by default, in order if ordered=True.

    Column labels must match exactly. To use another scorer, change only this body.
    """
    a, b = _norm_rows(original_rows), _norm_rows(candidate_rows)
    if ordered:
        return list(original_columns) == list(candidate_columns) and a == b
    return _multiset_equal(a, original_columns, b, candidate_columns)


def has_top_level_order_by(sql: str) -> bool:
    """True if ORDER BY appears outside all parentheses (subquery ORDER BY is ignored)."""
    masked = _mask_literals_and_comments(sql)
    depth = 0
    for token in re.finditer(r"[()]|\bORDER\s+BY\b", masked, re.IGNORECASE):
        text = token.group(0)
        if text == "(":
            depth += 1
        elif text == ")":
            depth -= 1
        elif depth == 0:
            return True
    return False


def run_limited(
    sql: str, db_path: str | Path | None = None, timeout_s: float = TIMEOUT_S
) -> tuple[list[list[Any]], list[str]]:
    """Run one read-only query; raise sqlite3.OperationalError if it exceeds timeout_s."""
    guarded = validate_readonly(sql)
    deadline = monotonic() + timeout_s
    with closing(connect_readonly(db_path)) as connection:
        # SQLite calls this every 10000 VM steps; returning 1 aborts the query.
        connection.set_progress_handler(lambda: 1 if monotonic() > deadline else 0, 10000)
        cursor = connection.execute(guarded)
        columns = [d[0] for d in cursor.description or []]
        return [list(r) for r in cursor.fetchall()], columns


def results_equal(
    sql_a: str,
    sql_b: str,
    db_path: str | Path | None = None,
    timeout_s: float = TIMEOUT_S,
) -> bool:
    """Run both queries and compare. Any error or timeout returns False, never raises."""
    try:
        rows_a, cols_a = run_limited(sql_a, db_path, timeout_s)
        rows_b, cols_b = run_limited(sql_b, db_path, timeout_s)
        return compare_results(
            rows_a, cols_a, rows_b, cols_b, ordered=has_top_level_order_by(sql_a)
        )
    except (ValueError, sqlite3.Error, OSError, TypeError):
        return False
