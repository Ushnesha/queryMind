"""Contract tests for mechanical metrics and starter evaluation wiring."""

from pathlib import Path

import pytest

from src.evaluation import ablation_variants, load_questions, run_evaluation
from src.evaluation.b2 import run_self_consistency
from src.evaluation.metrics import summarize_results, summarize_runs


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


def test_b2_reports_unimplemented_instead_of_results() -> None:
    assert run_self_consistency("A question")["implemented"] is False
