"""Schema experiment metrics that distinguish completeness from selectivity."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from statistics import mean, median
from typing import Any


def _names(values: Iterable[str]) -> set[str]:
    return {str(value).casefold() for value in values}


def _edge_key(edge: Mapping[str, str]) -> tuple[str, str]:
    endpoints = (
        f"{edge['from_table']}.{edge['from_column']}".casefold(),
        f"{edge['to_table']}.{edge['to_column']}".casefold(),
    )
    return tuple(sorted(endpoints))


def _set_metrics(required: set[Any], retrieved: set[Any]) -> dict[str, Any]:
    hits = len(required & retrieved)
    return {
        "required_count": len(required), "retrieved_count": len(retrieved), "matched_count": hits,
        "recall": hits / len(required) if required else 1.0,
        "precision": hits / len(retrieved) if retrieved else (1.0 if not required else 0.0),
        "exact_set": required == retrieved,
    }


def retrieval_metrics(
    required_tables: Iterable[str],
    required_columns: Iterable[str],
    required_joins: Iterable[Mapping[str, str]],
    retrieved_tables: Iterable[str],
    retrieved_columns: Iterable[str],
    retrieved_relationships: Iterable[Mapping[str, str]],
) -> dict[str, Any]:
    """Score case-insensitive names and undirected, column-qualified FK edges.

    Complete flat contexts should score perfect recall. Precision and exact
    sets separately describe irrelevant context; they are not answer accuracy.
    Join-path coverage requires every required FK edge to be present, including
    bridge edges, and every required table to be present.
    """
    tables = _set_metrics(_names(required_tables), _names(retrieved_tables))
    columns = _set_metrics(_names(required_columns), _names(retrieved_columns))
    joins = _set_metrics({_edge_key(edge) for edge in required_joins}, {_edge_key(edge) for edge in retrieved_relationships})
    return {
        "tables": tables, "columns": columns, "joins": joins,
        "join_path_covered": tables["recall"] == 1.0 and joins["recall"] == 1.0,
    }


def count_context_tokens(context: str, tokenizer: Callable[[str], int] | None = None) -> dict[str, Any]:
    """Use an explicit tokenizer, or label a reproducible lexical estimate."""
    if tokenizer is not None:
        count = tokenizer(context)
        if not isinstance(count, int) or count < 0:
            raise ValueError("tokenizer must return a nonnegative integer")
        return {"count": count, "method": getattr(tokenizer, "tokenizer_name", "configured_tokenizer"), "is_estimate": False}
    return {
        "count": len(re.findall(r"\w+|[^\w\s]", context)),
        "method": "lexical_regex_estimate_words_and_punctuation",
        "is_estimate": True,
    }


def summarize_arm(cases: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    """Macro-average retrieval metrics and separately count generated outcomes."""
    entries = [case["arms"][arm] for case in cases]
    generated = [entry["generation"] for entry in entries if entry["generation"] is not None]
    successful_generation = [entry for entry in generated if entry["sql_generated"]]
    executed = [entry for entry in generated if entry["execution_ok"]]
    comparisons = [entry for entry in generated if isinstance(entry["result_correct"], bool)]
    return {
        "case_count": len(entries),
        "table_recall": mean(entry["retrieval_metrics"]["tables"]["recall"] for entry in entries),
        "table_precision": mean(entry["retrieval_metrics"]["tables"]["precision"] for entry in entries),
        "exact_table_set_rate": mean(entry["retrieval_metrics"]["tables"]["exact_set"] for entry in entries),
        "column_recall": mean(entry["retrieval_metrics"]["columns"]["recall"] for entry in entries),
        "column_precision": mean(entry["retrieval_metrics"]["columns"]["precision"] for entry in entries),
        "join_recall": mean(entry["retrieval_metrics"]["joins"]["recall"] for entry in entries),
        "join_precision": mean(entry["retrieval_metrics"]["joins"]["precision"] for entry in entries),
        "join_path_coverage": mean(entry["retrieval_metrics"]["join_path_covered"] for entry in entries),
        "mean_context_tokens": mean(entry["context_tokens"]["count"] for entry in entries),
        "context_token_method": entries[0]["context_tokens"]["method"],
        "mean_retrieval_latency_ms": mean(value for entry in entries for value in entry["retrieval_latencies_ms"]),
        "median_retrieval_latency_ms": median(value for entry in entries for value in entry["retrieval_latencies_ms"]),
        "generation_attempts": len(generated),
        "sql_generation_success_rate": len(successful_generation) / len(generated) if generated else None,
        "syntax_success_rate": sum(entry["syntax_ok"] for entry in generated) / len(generated) if generated else None,
        "execution_success_rate": len(executed) / len(generated) if generated else None,
        "result_comparisons": len(comparisons),
        "result_accuracy": sum(entry["result_correct"] is True for entry in comparisons) / len(comparisons) if comparisons else None,
        "mean_execution_time_ms": mean(entry["execution_time_ms"] for entry in executed) if executed else None,
    }
