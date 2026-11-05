"""Mechanical metrics with explicit denominators; no LLM judging."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.state import AgentState


def summarize_runs(states: Iterable[AgentState]) -> dict[str, Any]:
    """Summarize run outcomes, rows, and recorded timing (empty rates are 0).

    Success means orchestration completed with ``status='success'``. It does
    not mean semantic correctness. Timing means use only runs that recorded
    that metric, so missing instrumentation is not counted as zero latency.
    """
    records = list(states)
    total = len(records)
    successes = sum(state.get("status") == "success" for state in records)
    refusals = sum(state.get("status") == "refused" for state in records)
    errors = sum(state.get("status") == "error" for state in records)
    return {
        "run_count": total,
        "successful_runs": successes,
        "refused_runs": refusals,
        "error_runs": errors,
        "success_rate": successes / total if total else 0.0,
        "total_rows": sum(len(state.get("rows", [])) for state in records),
        "mean_total_latency_ms": _mean_metric(records, "total_latency_ms"),
        "mean_execution_time_ms": _mean_metric(records, "execution_time_ms"),
    }


def summarize_results(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute result accuracy over cases with a boolean reference comparison."""
    records = list(cases)
    scored = [case for case in records if isinstance(case.get("correct"), bool)]
    correct = sum(case["correct"] is True for case in scored)
    return {
        "case_count": len(records),
        "scored_cases": len(scored),
        "correct_cases": correct,
        "result_accuracy": correct / len(scored) if scored else 0.0,
    }


def _mean_metric(states: list[AgentState], key: str) -> float | None:
    values = [
        float(state["metrics"][key])
        for state in states
        if isinstance(state.get("metrics", {}).get(key), (int, float))
    ]
    return sum(values) / len(values) if values else None
