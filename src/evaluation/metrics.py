"""Mechanical metrics with explicit denominators; no LLM judging.

Fabrication is the observable proxy of a successful answer to a labelled
unanswerable question. It is not a judgment of arbitrary generated prose.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
from typing import Any

from src.state import AgentState


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def percentile(values: Iterable[float], quantile: float) -> float | None:
    """Linearly interpolate sorted observations; no samples means None."""
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between 0 and 1")
    ordered = sorted(value for item in values if (value := _number(item)) is not None)
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _state_metric(states: list[AgentState], key: str) -> list[float]:
    return [value for state in states if (value := _number(state.get("metrics", {}).get(key))) is not None]


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
    executions = sum(
        any(event.get("node") in {"executor", "execution"} and event.get("status") == "pass"
            for event in state.get("trace", []))
        or (state.get("status") == "success" and bool(state.get("columns")))
        for state in records
    )
    latencies = _state_metric(records, "total_latency_ms")
    calls = _state_metric(records, "llm_calls")
    generations = _state_metric(records, "generation_calls")
    return {
        "run_count": total,
        "successful_runs": successes,
        "refused_runs": refusals,
        "error_runs": errors,
        "success_rate": successes / total if total else 0.0,
        "completion_rate": successes / total if total else 0.0,
        "executed_runs": executions,
        "execution_success_rate": executions / total if total else 0.0,
        "total_rows": sum(len(state.get("rows", [])) for state in records),
        "mean_total_latency_ms": _mean(latencies),
        "mean_execution_time_ms": _mean(_state_metric(records, "execution_time_ms")),
        "p50_latency_ms": percentile(latencies, 0.5),
        "p95_latency_ms": percentile(latencies, 0.95),
        "latency_observations": len(latencies),
        "llm_calls_per_question": _mean(calls),
        "llm_call_observations": len(calls),
        "generation_calls_per_question": _mean(generations),
        "generation_call_observations": len(generations),
    }


def summarize_results(cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Score boolean comparisons and separately report each labelled subgroup.

    Informed refusal requires a correct refusal, while the raw refusal rate also
    counts generic provider abstentions. Missing subgroup labels produce None.
    """
    records = list(cases)
    scored = [case for case in records if isinstance(case.get("correct"), bool)]
    correct = sum(case["correct"] is True for case in scored)
    answerable = [case for case in records if case.get("answerable") is True]
    unanswerable = [case for case in records if case.get("answerable") is False]
    ambiguous = [case for case in records if case.get("ambiguous") is True]
    fabricated = sum(
        not _refused(case) and case.get("state", {}).get("status") == "success"
        for case in unanswerable
    )
    informed_refusals = sum(_refused(case) and case.get("correct") is True for case in unanswerable)
    raw_refusals = sum(_refused(case) for case in unanswerable)
    over_refusals = sum(_refused(case) for case in answerable)
    ambiguity_flagged = sum(case.get("ambiguity_flagged") is True for case in ambiguous)
    metrics: dict[str, Any] = {
        "case_count": len(records),
        "scored_cases": len(scored),
        "unscored_cases": len(records) - len(scored),
        "reference_error_count": sum(bool(case.get("reference_error")) for case in records),
        "correct_cases": correct,
        "result_accuracy": correct / len(scored) if scored else 0.0,
        "answerable_cases": len(answerable),
        "unanswerable_cases": len(unanswerable),
        "ambiguous_cases": len(ambiguous),
        "fabrication_count": fabricated,
        "fabrication_rate": _rate(fabricated, len(unanswerable)),
        "false_answer_rate": _rate(fabricated, len(unanswerable)),
        "informed_refusal_count": informed_refusals,
        "unanswerable_refusal_rate": _rate(informed_refusals, len(unanswerable)),
        "raw_unanswerable_refusal_rate": _rate(raw_refusals, len(unanswerable)),
        "over_refusal_count": over_refusals,
        "over_refusal_rate": _rate(over_refusals, len(answerable)),
        "ambiguity_flagged_count": ambiguity_flagged,
        "ambiguity_flagged_rate": _rate(ambiguity_flagged, len(ambiguous)),
    }
    for difficulty in ("easy", "hard"):
        group = [case for case in scored if str(case.get("difficulty", "")).lower() == difficulty]
        hits = sum(case["correct"] is True for case in group)
        metrics.update({
            f"{difficulty}_scored_cases": len(group),
            f"{difficulty}_correct_cases": hits,
            f"{difficulty}_accuracy": _rate(hits, len(group)),
        })
    return metrics


def _refused(case: Mapping[str, Any]) -> bool:
    return case.get("refused") is True or case.get("state", {}).get("status") == "refused"


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None
