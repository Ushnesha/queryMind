"""Stable public interfaces for plan inspection and future query rewrites."""

from .equality import compare_results
from .explain import explain_query_plan
from .optimizer import optimize_sql

__all__ = ["compare_results", "explain_query_plan", "optimize_sql"]
