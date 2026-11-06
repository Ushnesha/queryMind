"""Contract tests for mechanical metrics and starter evaluation wiring."""

from pathlib import Path

import pytest

from src.evaluation import ablation_variants, load_questions, run_evaluation
from src.evaluation.b2 import run_self_consistency
from src.evaluation.metrics import percentile, summarize_results, summarize_runs


def test_metrics_distinguish_outcomes_and_missing_timing() -> None:
    metrics = summarize_runs(
        [
            {"status": "success", "rows": [[1]], "metrics": {"execution_time_ms": 4.0}},
            {"status": "refused", "rows": [], "metrics": {}},
            {"status": "error", "rows": [], "metrics": {"execution_time_ms": 8.0}},
        ]
    )
    assert metrics["run_count"] == 3
    assert metrics["successful_runs"] == metrics["refused_runs"] == metrics["error_runs"] == 1
    assert metrics["success_rate"] == pytest.approx(1 / 3)
    assert metrics["mean_execution_time_ms"] == 6.0
    assert metrics["mean_total_latency_ms"] is None


def test_empty_metrics_and_unscored_cases_have_defined_denominators() -> None:
    assert summarize_runs([])["success_rate"] == 0.0
    result = summarize_results([{"correct": True}, {"correct": False}, {"correct": None}])
    assert result["scored_cases"] == 2
    assert result["result_accuracy"] == 0.5
    assert summarize_results([])["result_accuracy"] == 0.0


def test_ablation_variants_disable_one_component_at_a_time() -> None:
    variants = ablation_variants()
    assert len(variants) == 5
    assert all(variants["all_enabled"].values())
    assert all(
        sum(not enabled for enabled in flags.values()) == 1
        for name, flags in variants.items()
        if name != "all_enabled"
    )


def test_reference_fixture_runs_offline(db_path: Path) -> None:
    questions = load_questions(Path(__file__).resolve().parents[1] / "eval/questions.yaml")
    report = run_evaluation(questions, db_path=db_path)
    assert report["metrics"]["scored_cases"] == len(questions)
    assert report["metrics"]["result_accuracy"] == 1.0


def test_question_loader_rejects_invalid_contract(tmp_path: Path) -> None:
    fixture = tmp_path / "questions.yaml"
    fixture.write_text("questions: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="questions.*list"):
        load_questions(fixture)


def test_b2_reports_completed_reduced_experiment(db_path: Path) -> None:
    report = run_self_consistency("How many customers are there?", db_path=db_path)
    assert report["implemented"] is True
    assert report["samples"] == 3
    assert report["state"]["rows"] == [[4]]


def test_labelled_metric_denominators() -> None:
    cases = [
        {"difficulty": "easy", "answerable": True, "correct": True, "state": {"status": "success"}},
        {"difficulty": "hard", "answerable": True, "correct": False, "refused": True},
        {"difficulty": "hard", "answerable": False, "correct": True, "refused": True},
        {"difficulty": "hard", "answerable": False, "correct": False, "state": {"status": "success"}},
        {"difficulty": "easy", "answerable": False, "correct": False, "refused": True},
        {"answerable": True, "ambiguous": True, "ambiguity_flagged": True, "correct": None},
        {"answerable": True, "ambiguous": True, "ambiguity_flagged": False, "correct": None},
        {"correct": None},
    ]
    metrics = summarize_results(cases)
    assert metrics["result_accuracy"] == 2 / 5
    assert metrics["easy_accuracy"] == 1 / 2
    assert metrics["hard_accuracy"] == 1 / 3
    assert metrics["fabrication_rate"] == 1 / 3
    assert metrics["unanswerable_refusal_rate"] == 1 / 3
    assert metrics["raw_unanswerable_refusal_rate"] == 2 / 3
    assert metrics["over_refusal_rate"] == 1 / 4
    assert metrics["ambiguity_flagged_rate"] == 1 / 2


def test_missing_labels_are_unmeasured_instead_of_zero() -> None:
    metrics = summarize_results([{"correct": True}])
    for key in ("easy_accuracy", "hard_accuracy", "fabrication_rate", "unanswerable_refusal_rate", "ambiguity_flagged_rate", "over_refusal_rate"):
        assert metrics[key] is None


def test_latency_percentiles_and_call_instrumentation() -> None:
    metrics = summarize_runs([
        {"status": "success", "metrics": {"total_latency_ms": 10, "generation_calls": 1, "llm_calls": 0}},
        {"status": "refused", "metrics": {"total_latency_ms": 20, "generation_calls": 3, "llm_calls": 0}},
        {"status": "error", "metrics": {"total_latency_ms": 100, "llm_calls": None}},
        {"status": "error", "metrics": {"total_latency_ms": float("nan"), "llm_calls": True}},
    ])
    assert metrics["p50_latency_ms"] == 20
    assert metrics["p95_latency_ms"] == pytest.approx(92)
    assert metrics["llm_calls_per_question"] == 0
    assert metrics["llm_call_observations"] == 2
    assert metrics["generation_calls_per_question"] == 2
    assert percentile([], .95) is None
    assert percentile([5], .95) == 5
    with pytest.raises(ValueError):
        percentile([1], 2)
