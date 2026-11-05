"""Safe no-op optimizer preserving the integration contract."""

import sqlite3
from pathlib import Path
from typing import Any, TypedDict

from .explain import explain_query_plan


class OptimizationResult(TypedDict):
    """Candidate SQL and plan metadata returned by every optimizer."""

    changed: bool
    sql: str
    reason: str
    plan_before: list[list[Any]]
    plan_after: list[list[Any]]


def optimize_sql(
    sql: str,
    question: str,
    schema_context: str,
    *,
    db_path: str | Path | None = None,
) -> OptimizationResult:
    """Inspect a read-only plan and keep the original SQL unchanged."""
    # TODO(feature/optimizer): propose rewrites, gate equality and benchmark.
    reason = "Starter optimizer inspected the plan and kept SQL unchanged."
    try:
        plan = explain_query_plan(sql, db_path=db_path)
    except (ValueError, sqlite3.Error, OSError) as exc:
        plan = []
        reason = f"Starter optimizer kept SQL unchanged; plan unavailable: {exc}"
    return {
        "changed": False,
        "sql": sql,
        "reason": reason,
        "plan_before": plan,
        "plan_after": [list(row) for row in plan],
    }
