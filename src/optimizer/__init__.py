"""Stable public interfaces for plan inspection and future query rewrites."""

from .distinct_guard import check_distinct_guard
from .equality import compare_results
from .explain import explain_query_plan
from .optimizer import optimize_sql

__all__ = ["check_distinct_guard", "compare_results", "explain_query_plan", "optimize_sql"]
