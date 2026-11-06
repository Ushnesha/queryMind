"""Safe no-op optimizer preserving the integration contract."""

import sqlite3
from pathlib import Path
from time import perf_counter
from typing import Any, TypedDict

from .explain import explain_query_plan


class OptimizationResult(TypedDict):
    """Candidate SQL and plan metadata returned by every optimizer."""

    changed: bool
    sql: str
    original_sql: str
    optimized_sql: str
    reason: str
    plan_before: list[list[Any]]
    plan_after: list[list[Any]]
    equality_ok: bool | None
    llm_calls: int
    latency_ms: int


def optimize_sql(
    sql: str,
    question: str,
    schema_context: str,
    *,
    db_path: str | Path | None = None,
) -> OptimizationResult:
    """Inspect a read-only plan and keep the original SQL unchanged."""
    started = perf_counter()
    reason = "Starter optimizer inspected the plan and kept SQL unchanged."
    try:
        plan = explain_query_plan(sql, db_path=db_path)
    except (ValueError, sqlite3.Error, OSError) as exc:
        plan = []
        reason = f"Starter optimizer kept SQL unchanged; plan unavailable: {exc}"
    return {
        "changed": False,
        "sql": sql,
        "original_sql": sql,
        "optimized_sql": sql,
        "reason": reason,
        "plan_before": plan,
        "plan_after": [list(row) for row in plan],
        "equality_ok": None,
        "llm_calls": 0,
        "latency_ms": int((perf_counter() - started) * 1000),
    }
