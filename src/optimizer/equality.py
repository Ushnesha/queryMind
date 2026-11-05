"""Reusable equivalence gate for future optimization candidates."""

from typing import Any

from src.score import results_equal


def compare_results(
    original_rows: list[Any],
    original_columns: list[str],
    candidate_rows: list[Any],
    candidate_columns: list[str],
) -> bool:
    """Compare result multisets and exact column names via the shared scorer.

    Duplicate multiplicity is preserved. Row order is ignored; queries with
    ordering requirements need an additional order-sensitive check before a
    future optimizer can accept a rewrite.
    """
    return results_equal(
        original_rows, original_columns, candidate_rows, candidate_columns
    )
