"""Query optimizer: deterministic triggers, one LLM rewrite, mandatory equality gate."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, TypedDict

from src.db import connect_readonly, validate_readonly
from src.llm import MockProvider, SQLProvider, get_provider
from src.verifiers.syntax import check_syntax

from .equality import TIMEOUT_S, results_equal
from .explain import explain_query_plan, plan_improved, plan_signals

LARGE_TABLE_ROWS = 1000  # a full SCAN only counts as a problem above this size


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


def call_llm(prompt: str) -> str:
    """Use the same configured provider as SQL generation and verification."""
    from src.config import load_settings
    from src.llm import get_provider

    return get_provider(load_settings().model.provider).generate("Optimize this query", prompt)


def find_trigger(sql: str, plan: list[list[Any]], db_path: str | Path | None) -> str | None:
    """Return why the query may be worth rewriting, or None if the plan looks fine."""
    signals = plan_signals(plan)
    details = " ".join(str(row[3]).upper() for row in plan)
    if "CORRELATED" in details:
        return "correlated subquery in plan"
    if re.search(r"\bIN\s*\(\s*SELECT\b", sql, re.IGNORECASE):
        return "IN (SELECT ...) subquery"
    if signals["temp_btrees"] and re.search(r"\bDISTINCT\b", sql, re.IGNORECASE):
        return "DISTINCT needs a temp b-tree"
    with closing(connect_readonly(db_path)) as connection:
        for table in signals["scanned_tables"]:
            try:
                quoted = '"' + table.replace('"', '""') + '"'
                count = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            except sqlite3.Error:  # alias or subquery name, not a real table
                continue
            if count >= LARGE_TABLE_ROWS:
                return f"full scan of large table {table} ({count} rows)"
    return None


def build_prompt(
    question: str, sql: str, schema_context: str, plan: list[list[Any]], trigger: str
) -> str:
    plan_text = "\n".join(str(row[3]) for row in plan)
    return (
        "You optimize SQLite queries. Rewrite the SQL to run faster while returning EXACTLY "
        "the same rows and the same column names. Do not change the meaning.\n"
        f"Question: {question}\nSchema:\n{schema_context}\nOriginal SQL:\n{sql}\n"
        f"Query plan:\n{plan_text}\nWhy it may be slow: {trigger}\n"
        'Reply with only JSON: {"sql": "<one SELECT or WITH statement>", "reason": "<short reason>"}'
    )


def parse_reply(text: str) -> tuple[str, str]:
    """Extract (sql, reason) from the LLM reply. Raise ValueError if unusable."""
    cleaned = re.sub(r"^```(?:json|sql)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
        sql, reason = data["sql"], str(data.get("reason", ""))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("LLM reply was not the expected JSON") from None
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("LLM reply had no SQL")
    return sql.strip(), reason


def optimize_sql(
    sql: str,
    question: str,
    schema_context: str,
    *,
    db_path: str | Path | None = None,
    llm: Callable[[str], str] | None = None,
    provider: SQLProvider | None = None,
    timeout_s: float = TIMEOUT_S,
) -> OptimizationResult:
    """Try one gated rewrite. On any problem return the original SQL. Never raises.

    One LLM attempt per call: the orchestrator calls this at most twice per question.
    """
    started = perf_counter()
    result: OptimizationResult = {
        "changed": False, "sql": sql, "original_sql": sql, "optimized_sql": sql,
        "reason": "", "plan_before": [], "plan_after": [], "equality_ok": None,
        "llm_calls": 0, "latency_ms": 0,
    }
    try:
        plan = explain_query_plan(sql, db_path=db_path)
        result["plan_before"], result["plan_after"] = plan, [list(r) for r in plan]
        trigger = find_trigger(sql, plan, db_path)
        if trigger is None:
            result["reason"] = "Plan already reasonable; no rewrite attempted."
        else:
            if llm is None:
                from src.config import load_settings

                selected = provider or get_provider(load_settings().model.provider)
                if isinstance(selected, MockProvider) or getattr(selected, "is_mock", False):
                    result["reason"] = f"Kept original SQL ({trigger}); offline provider cannot propose rewrites."
                    return result
                llm = lambda prompt: selected.generate("Optimize this query", prompt)
            _attempt(result, question, schema_context, trigger, db_path, llm, timeout_s)
    except Exception as exc:  # ponytail: broad on purpose, the contract says never raise
        result["reason"] = f"Kept original SQL; optimizer error: {exc}"
    result["latency_ms"] = int((perf_counter() - started) * 1000)
    return result


def _attempt(
    result: OptimizationResult,
    question: str,
    schema_context: str,
    trigger: str,
    db_path: str | Path | None,
    llm: Callable[[str], str],
    timeout_s: float,
) -> None:
    """Ask the LLM, validate and gate the rewrite. Fill result only if it is accepted."""
    sql = result["original_sql"]
    result["llm_calls"] = 1
    try:
        prompt = build_prompt(question, sql, schema_context, result["plan_before"], trigger)
        candidate, why = parse_reply(llm(prompt))
        candidate = validate_readonly(candidate)
        syntax = check_syntax(candidate, db_path=db_path)
        if not syntax["ok"]:
            raise ValueError(syntax["error"])
    except Exception as exc:
        result["reason"] = f"Rewrite rejected ({trigger}): {exc}"
        return
    if candidate.rstrip("; \n") == sql.rstrip("; \n"):
        result["reason"] = f"LLM returned the same SQL ({trigger})."
        return
    result["equality_ok"] = results_equal(sql, candidate, db_path, timeout_s)
    if not result["equality_ok"]:
        result["reason"] = f"Rewrite rejected ({trigger}): results differ, errored or timed out."
        return
    # Equality on one database is not proof, so also demand a better plan.
    plan_after = explain_query_plan(candidate, db_path=db_path)
    if not plan_improved(result["plan_before"], plan_after):
        result["reason"] = f"Rewrite rejected ({trigger}): results equal but plan not improved."
        return
    result.update(
        changed=True,
        sql=candidate,
        optimized_sql=candidate,
        plan_after=plan_after,
        reason=f"{trigger}: {why}",
    )
