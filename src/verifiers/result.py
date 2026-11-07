"""Result verifier: deterministic sanity checks on what the executed SQL returned.

Each finding is a warning string ``"CODE: explanation"``. Warnings flag results
worth a second look; they do not by themselves mark a result wrong. ``ok`` is
False only when the table is structurally broken (rows that do not match the
column count), which the orchestrator treats as an execution error.

Checks:
  EMPTY_RESULT, ALL_ZERO_RESULT, NULL_HEAVY_COLUMN, NON_FINITE_VALUE,
  ROW_LIMIT_EXCEEDED, FEWER_ROWS_THAN_REQUESTED, EXPECTED_SINGLE_ROW,
  NON_NUMERIC_AGGREGATE, NEGATIVE_COUNT, DUPLICATE_ROWS, DUPLICATE_COLUMNS,
  UNKNOWN_RESULT_COLUMN (needs ``schema_context``),
  SEMANTIC_CONTRADICTION (needs an LLM judge).
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, TypedDict

from src.llm import SQLProvider

from .cues import parse_intent, parse_schema, parse_sql
from .judge import as_bool, ask_json, resolve_judge

NULL_HEAVY_THRESHOLD = 0.5
SAMPLE_ROWS = 5


class ResultVerification(TypedDict):
    """Result contract: structural ok flag, warnings and JSON-safe statistics."""

    ok: bool
    warnings: list[str]
    statistics: dict[str, Any]
    status: str


JUDGE_INSTRUCTIONS = """You are QueryMind's result verifier.
Given a question, the SQL that ran, and a compact summary of its result, decide whether the result plausibly represents the quantity the question asks for.
Judge plausibility only (units, magnitude, shape, obviously wrong values); you cannot see the full data.

Return ONLY one JSON object, with no Markdown and no commentary:
{"plausible": true or false, "reason": "one sentence"}"""


def _is_null(value: Any) -> bool:
    return value is None


def _is_non_finite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    return isinstance(value, dict) and value.get("type") == "nonfinite_float"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _row_key(row: Any) -> str:
    return json.dumps(row, sort_keys=True, default=str)


def _derivable(column: str, schema_columns: set[str], aliases: frozenset[str]) -> bool:
    name = column.lower()
    if name in schema_columns or name in aliases:
        return True
    # Unaliased expressions keep their text as the column name, e.g. COUNT(*).
    return bool(re.search(r"[()*+\-/|<>=]", column))


def verify_result(
    question: str,
    sql: str,
    rows: list[Any],
    columns: list[str],
    *,
    schema_context: str | None = None,
    provider: SQLProvider | None = None,
    use_llm: bool | None = None,
) -> ResultVerification:
    """Check an executed result against the question; see the module docstring for codes.

    ``schema_context`` enables the result/schema consistency check. ``provider``
    or a non-mock configured provider enables the LLM contradiction check;
    ``use_llm=False`` disables it.
    """
    warnings: list[str] = []
    row_count, column_count = len(rows), len(columns)
    malformed = any(not isinstance(row, (list, tuple)) or len(row) != column_count for row in rows)
    statistics: dict[str, Any] = {"row_count": row_count, "column_count": column_count}
    if malformed:
        warnings.append("MALFORMED_ROWS: At least one result row does not match the column count.")
        return {"ok": False, "warnings": warnings, "statistics": statistics, "status": "deterministic"}

    if len({c.lower() for c in columns}) != column_count:
        warnings.append("DUPLICATE_COLUMNS: The result contains duplicate column names.")

    intent = parse_intent(question)
    cells = [value for row in rows for value in row]

    # 1. Empty result
    if row_count == 0:
        warnings.append("EMPTY_RESULT: The query returned no rows.")

    # 2. All numeric values zero
    numbers = [value for value in cells if _is_number(value) and math.isfinite(value)]
    if numbers and all(value == 0 for value in numbers):
        warnings.append("ALL_ZERO_RESULT: Every numeric value in the result is zero.")

    # 3. NULL-heavy columns
    column_nulls: dict[str, float] = {}
    for index, column in enumerate(columns):
        fraction = sum(_is_null(row[index]) for row in rows) / row_count if row_count else 0.0
        column_nulls[column] = round(fraction, 4)
    heavy = [c for c, fraction in column_nulls.items() if row_count and fraction >= NULL_HEAVY_THRESHOLD]
    if heavy:
        detail = ", ".join(f"{c} ({column_nulls[c]:.0%})" for c in heavy)
        warnings.append(f"NULL_HEAVY_COLUMN: Mostly NULL values in {detail}.")

    # 4. Non-finite numbers
    non_finite = sum(_is_non_finite(value) for value in cells)
    if non_finite:
        warnings.append(f"NON_FINITE_VALUE: {non_finite} value(s) are NaN or infinite.")

    # 5. Question/result shape
    if intent.top_n is not None:
        if row_count > intent.top_n:
            warnings.append(
                f"ROW_LIMIT_EXCEEDED: The question asks for the top {intent.top_n}, "
                f"but {row_count} rows were returned."
            )
        elif 0 < row_count < intent.top_n:
            warnings.append(
                f"FEWER_ROWS_THAN_REQUESTED: The question asks for the top {intent.top_n}, "
                f"but only {row_count} row(s) exist."
            )
    if intent.expects_scalar and row_count not in (0, 1):
        warnings.append(
            f"EXPECTED_SINGLE_ROW: The question asks for a single value, but {row_count} rows were returned."
        )

    # 6. Duplicate rows
    duplicate_count = row_count - len({_row_key(row) for row in rows})
    if duplicate_count:
        warnings.append(f"DUPLICATE_ROWS: {duplicate_count} row(s) repeat an earlier row exactly.")

    # 7. Aggregate sanity
    numeric_columns = [
        column for index, column in enumerate(columns)
        if any(_is_number(row[index]) for row in rows)
        and all(_is_number(row[index]) or row[index] is None or _is_non_finite(row[index]) for row in rows)
    ]
    if intent.wants_aggregate and row_count and not numeric_columns:
        warnings.append("NON_NUMERIC_AGGREGATE: The question asks for a count, total or average, but no column is numeric.")
    if intent.wants_count and intent.expects_scalar and any(_is_number(v) and v < 0 for v in cells):
        warnings.append("NEGATIVE_COUNT: A count question returned a negative number.")

    # 8. Result/schema consistency
    if schema_context:
        schema = parse_schema(schema_context)
        if schema.tables:
            aliases = parse_sql(sql).aliases
            unknown = [c for c in columns if not _derivable(c, schema.columns, aliases)]
            if unknown:
                warnings.append(
                    "UNKNOWN_RESULT_COLUMN: " + ", ".join(unknown)
                    + " is not a schema column, a SQL alias or an expression."
                )

    statistics.update(
        null_fraction=round(sum(_is_null(v) for v in cells) / len(cells), 4) if cells else 0.0,
        duplicate_count=duplicate_count,
        non_finite_count=non_finite,
        numeric_columns=numeric_columns,
        column_null_fractions=column_nulls,
    )

    # 9. Semantic contradiction (LLM, warning only)
    status = "deterministic"
    judge = resolve_judge(provider, use_llm)
    if judge is not None:
        try:
            verdict = _judge_result(question, sql, rows, columns, statistics, judge)
            status = "deterministic+llm"
            if not verdict[0]:
                warnings.append("SEMANTIC_CONTRADICTION: " + (verdict[1] or "The LLM judge found the result implausible."))
        except Exception as exc:
            statistics["llm_judge_error"] = str(exc)

    return {"ok": True, "warnings": warnings, "statistics": statistics, "status": status}


def _judge_result(
    question: str,
    sql: str,
    rows: list[Any],
    columns: list[str],
    statistics: dict[str, Any],
    provider: SQLProvider,
) -> tuple[bool, str]:
    summary = {
        "sql": sql.strip(),
        "row_count": statistics["row_count"],
        "columns": columns,
        "sample_rows": rows[:SAMPLE_ROWS],
        "null_fraction": statistics["null_fraction"],
        "duplicate_count": statistics["duplicate_count"],
    }
    instructions = f"{JUDGE_INSTRUCTIONS}\n\nResult summary:\n{json.dumps(summary, default=str)}"
    data = ask_json(provider, question, instructions)
    if "plausible" not in data:
        raise ValueError("Judge reply is missing 'plausible'.")
    return as_bool(data["plausible"], True), str(data.get("reason") or "").strip()
