"""Small, deterministic result-shape checks for the starter pipeline."""

from typing import Any, TypedDict


class ResultVerification(TypedDict):
    """Result contract with honest starter coverage and JSON-safe statistics."""

    ok: bool
    warnings: list[str]
    statistics: dict[str, Any]
    status: str


def verify_result(
    question: str,
    sql: str,
    rows: list[Any],
    columns: list[str],
) -> ResultVerification:
    """Check row widths and surface empty results without inventing correctness."""
    # TODO(feature/verifiers): add question-aware result sanity verification.
    warnings = ["Starter result verification checks table shape only."]
    malformed = any(
        not isinstance(row, (list, tuple)) or len(row) != len(columns)
        for row in rows
    )
    if malformed:
        warnings.append("At least one result row does not match the column count.")
    if not rows:
        warnings.append("The query returned no rows.")
    if len(set(columns)) != len(columns):
        warnings.append("The result contains duplicate column names.")
    return {
        "ok": not malformed,
        "warnings": warnings,
        "statistics": {"row_count": len(rows), "column_count": len(columns)},
        "status": "placeholder",
    }
