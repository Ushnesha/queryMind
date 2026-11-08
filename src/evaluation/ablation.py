"""Controlled node ablation and paired flat-versus-Neo4j experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.evaluation.metrics import summarize_runs
from src.evaluation.runner import run_evaluation
from src.orchestrator import run_querymind


def ablation_variants() -> dict[str, dict[str, bool]]:
    """Return the original boolean node-switch contract for integration callers."""
    enabled = {
        "enable_syntax": True, "enable_semantic": True,
        "enable_optimizer": True, "enable_result_verifier": True,
    }
    return {
        "all_enabled": dict(enabled),
        **{f"without_{flag.removeprefix('enable_')}": {**enabled, flag: False} for flag in enabled},
    }


def experiment_variants(*, include_syntax: bool = False) -> dict[str, dict[str, Any]]:
    """Each experimental variant changes one factor from the Neo4j full arm."""
    switches = ablation_variants()
    full = {"schema_mode": "neo4j", **switches["all_enabled"]}
    variants = {
        "all_enabled": full,
        "without_neo4j": {**full, "schema_mode": "flat"},
        "without_semantic": {"schema_mode": "neo4j", **switches["without_semantic"]},
        "without_result_verifier": {"schema_mode": "neo4j", **switches["without_result_verifier"]},
        "without_optimizer": {"schema_mode": "neo4j", **switches["without_optimizer"]},
    }
    if include_syntax:
        variants["without_syntax"] = {"schema_mode": "neo4j", **switches["without_syntax"]}
    return variants


def run_ablation(
    question: str | Sequence[Mapping[str, Any]],
    *,
    db_path: str | Path | None = None,
    run_options: Mapping[str, Any] | None = None,
    include_syntax: bool = False,
) -> dict[str, Any]:
    """Run a representative suite, retaining the single-question smoke API.

    Read-only safety is never disabled. Suite order is identical in each arm;
    absolute timings are preliminary single runs, not a causal speedup claim.
    """
    if isinstance(question, str):
        variants: dict[str, Any] = {}
        for name, flags in ablation_variants().items():
            options = {"schema_mode": "flat", **(run_options or {}), **flags}
            state = run_querymind(question, db_path=db_path, **options)
            variants[name] = {"flags": flags, "state": state}
        return {
            "scope": "single-question ablation switch smoke test; not a completed experiment",
            "question": question, "variants": variants,
            "metrics": summarize_runs(item["state"] for item in variants.values()),
        }
    variants = {}
    for name, flags in experiment_variants(include_syntax=include_syntax).items():
        report = run_evaluation(question, db_path=db_path, run_options={**(run_options or {}), **flags})
        variants[name] = {"flags": flags, **report}
    return {
        "scope": "Milestone 2 preliminary node-by-node ablation; one factor changed per variant",
        "question_count": len(question),
        "question_ids": [str(item.get("id", index)) for index, item in enumerate(question, start=1)],
        "variants": variants,
        "limitations": [
            "A placeholder or flat fallback cannot establish the value of a real Neo4j graph.",
            "Single-run local timings are descriptive; no causal latency benefit is established.",
        ],
    }


def run_schema_comparison(
    questions: Sequence[Mapping[str, Any]],
    *,
    db_path: str | Path | None = None,
    run_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Hold all pipeline options fixed while switching only schema mode.

    Table/join correctness needs explicit retriever instrumentation and question
    annotations. Missing instrumentation remains null instead of being inferred
    from a successful execution or an unrestricted full-schema dump.
    """
    variants: dict[str, Any] = {}
    for mode in ("flat", "neo4j"):
        report = run_evaluation(questions, db_path=db_path, run_options={**(run_options or {}), "schema_mode": mode})
        states = [case["state"] for case in report["cases"]]
        retrieval_latencies = [
            float(event["latency_ms"]) for state in states for event in state.get("trace", [])
            if event.get("node") == "schema_retriever" and isinstance(event.get("latency_ms"), (int, float))
        ]
        contexts = [len(state["schema_context"]) for state in states if isinstance(state.get("schema_context"), str)]
        table_outcomes, join_outcomes = [], []
        for question, state in zip(questions, states):
            metrics = state.get("metrics", {})
            expected_tables = question.get("expected_tables")
            retrieved_tables = metrics.get("retrieved_tables")
            if expected_tables and isinstance(retrieved_tables, list):
                table_outcomes.append(set(expected_tables).issubset(retrieved_tables))
            expected_paths = question.get("expected_join_paths")
            retrieved_paths = metrics.get("retrieved_join_paths")
            if expected_paths and isinstance(retrieved_paths, list):
                join_outcomes.append(set(expected_paths).issubset(retrieved_paths))
        report["metrics"].update(
            mean_schema_context_chars=_mean(contexts),
            mean_retrieval_latency_ms=_mean(retrieval_latencies),
            correct_tables_rate=_mean(table_outcomes),
            correct_tables_scored=len(table_outcomes),
            correct_join_path_rate=_mean(join_outcomes),
            correct_join_path_scored=len(join_outcomes),
            fallback_runs=sum(any(
                event.get("node") == "schema_retriever" and event.get("status") in {"placeholder", "fallback"}
                for event in state.get("trace", [])
            ) for state in states),
        )
        variants[mode] = report
    comparison = [
        {"metric": key, **{mode: variants[mode]["metrics"].get(key) for mode in variants}}
        for key in (
            "result_accuracy", "correct_tables_rate", "correct_join_path_rate",
            "mean_schema_context_chars", "mean_retrieval_latency_ms", "fallback_runs",
        )
    ]
    return {
        "scope": "Milestone 2 preliminary paired flat-versus-Neo4j schema comparison",
        "question_count": len(questions), "variants": variants, "comparison": comparison,
        "limitations": [
            "Correct tables and join paths are unscored until annotations and retriever metrics are available.",
            "Neo4j placeholder/fallback runs are not measurements of graph retrieval.",
        ],
    }


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None
