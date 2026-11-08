"""Offline scoring, controlled experiment wiring, and trace replay contracts."""

from pathlib import Path

import pytest
import yaml

from src.evaluation import (
    experiment_variants, load_questions, run_ablation, run_evaluation,
    run_schema_comparison, score_records,
)


def test_loader_retains_annotations_and_aliases(tmp_path: Path) -> None:
    record = {
        "id": "H1", "question": "Question?", "reference_sql": "SELECT 1",
        "difficulty": "hard", "answerable": True, "ambiguous": False,
        "tags": ["b2"], "expected_tables": ["orders"],
        "expected_join_paths": ["orders.customer_id -> customers.customer_id"],
    }
    target = tmp_path / "questions.yaml"
    target.write_text(yaml.safe_dump({"questions": [record]}), encoding="utf-8")
    question = load_questions(target)[0]
    assert question["sql"] == "SELECT 1"
    assert all(question[key] == value for key, value in record.items())


@pytest.mark.parametrize("change", [
    {"id": ""}, {"question": " "}, {"answerable": "false"},
    {"ambiguous": 0}, {"difficulty": "medium"}, {"tags": "b2"},
    {"missing_fields": [1]}, {"sql": ""},
])
def test_loader_rejects_invalid_annotations(tmp_path: Path, change: dict) -> None:
    target = tmp_path / "questions.yaml"
    target.write_text(yaml.safe_dump({"questions": [{"id": "Q1", "question": "Question", **change}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_questions(target)


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    target = tmp_path / "questions.yaml"
    target.write_text("questions:\n- {id: Q1, question: First}\n- {id: Q1, question: Second}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(target)


def test_all_arms_run_offline_with_generation_counts(db_path: Path) -> None:
    questions = [{"id": "E1", "question": "How many customers are there?", "sql": "SELECT COUNT(*) AS customer_count FROM customers"}]
    for arm, count in (("b1", 1), ("b2", 3), ("querymind", 1)):
        report = run_evaluation(questions, db_path=db_path, arm=arm)
        case = report["cases"][0]
        assert case["correct"] is True
        assert case["generation_calls"] == count
        assert case["llm_calls"] == 0
        if arm == "b2":
            assert report["label"] == "b2-small preliminary experiment (k=3)"
            assert len(case["state"]["metrics"]["self_consistency"]["candidates"]) == 3


def test_provider_call_accounting_is_instrumented_not_assumed(db_path: Path) -> None:
    class Provider:
        llm_calls = 0

        def generate(self, question: str, schema_context: str) -> str:
            self.llm_calls += 2
            return "SELECT COUNT(*) AS customer_count FROM customers"

    questions = [{"id": "E1", "question": "Count", "sql": "SELECT COUNT(*) AS customer_count FROM customers"}]
    report = run_evaluation(questions, db_path=db_path, provider=Provider())
    # Generation, both judges and the answer writer use the shared provider.
    assert report["cases"][0]["llm_calls"] == 8
    assert report["cases"][0]["generation_calls"] == 1


def test_reference_failure_is_unscored_and_does_not_stop_suite(db_path: Path) -> None:
    questions = [
        {"id": "bad", "question": "How many customers?", "sql": "SELECT nonexistent FROM customers"},
        {"id": "good", "question": "How many customers?", "sql": "SELECT COUNT(*) AS customer_count FROM customers"},
    ]
    report = run_evaluation(questions, db_path=db_path)
    assert report["cases"][0]["correct"] is None
    assert "reference_error" in report["cases"][0]
    assert report["cases"][1]["correct"] is True
    assert report["metrics"]["scored_cases"] == 1


def test_informed_refusal_cannot_be_generic_unsupported() -> None:
    questions = [{"id": "U1", "question": "Profit?", "answerable": False, "missing_fields": ["product cost"]}]
    generic = {"status": "refused", "semantic_reason": "Unsupported mock question", "missing_fields": []}
    informed = {"status": "refused", "missing_fields": ["cost"], "semantic_reason": "Unavailable cost"}
    assert score_records(questions, [generic])["cases"][0]["correct"] is False
    assert score_records(questions, [informed])["cases"][0]["correct"] is True


def test_placeholder_assumptions_do_not_count_as_ambiguity() -> None:
    question = [{"id": "A1", "question": "Top customers?", "ambiguous": True}]
    state = {"status": "success", "assumptions": ["Unverified alignment"], "trace": [{"node": "semantic_verifier", "status": "placeholder"}]}
    assert score_records(question, [state])["cases"][0]["ambiguity_flagged"] is False
    state["trace"][0]["status"] = "pass"
    assert score_records(question, [state])["cases"][0]["ambiguity_flagged"] is True


def test_replay_matches_ids_handles_missing_and_rejects_extra(db_path: Path) -> None:
    questions = [
        {"id": "Q1", "question": "Count?", "sql": "SELECT 1 AS value"},
        {"id": "Q2", "question": "Count?", "sql": "SELECT 2 AS value"},
    ]
    records = [{"question_id": "Q2", "state": {"status": "success", "rows": [[2]], "columns": ["value"]}}]
    report = score_records(questions, records, db_path=db_path)
    assert report["cases"][0]["correct"] is None
    assert report["cases"][0]["unscored_reason"] == "Missing trace record."
    assert report["cases"][1]["correct"] is True
    with pytest.raises(ValueError, match="unknown"):
        score_records(questions, [{"question_id": "unknown", "state": {}}])
    with pytest.raises(ValueError, match="Duplicate"):
        score_records(questions, [records[0], records[0]])


def test_variants_change_exactly_one_controlled_factor() -> None:
    variants = experiment_variants(include_syntax=True)
    full = variants["all_enabled"]
    assert full["schema_mode"] == "neo4j"
    assert variants["without_neo4j"]["schema_mode"] == "flat"
    assert len(variants) == 6
    for name, options in variants.items():
        if name != "all_enabled":
            assert sum(options[key] != full[key] for key in full) == 1
    assert all("enable_safety" not in options for options in variants.values())


def test_replay_retains_synthetic_fixture_provenance() -> None:
    question = [{"id": "U1", "question": "Profit?", "answerable": False, "missing_fields": ["cost"]}]
    record = {
        "question_id": "U1", "provenance": "Synthetic scoring fixture; not an experimental observation",
        "state": {"status": "refused", "missing_fields": ["cost"]},
    }
    case = score_records(question, [record])["cases"][0]
    assert case["provenance"] == record["provenance"]
    assert case["correct"] is True


def test_ablation_multiquestion_reports_are_paired(db_path: Path) -> None:
    questions = [{"id": "E1", "question": "How many customers?", "sql": "SELECT COUNT(*) AS customer_count FROM customers"}]
    report = run_ablation(questions, db_path=db_path)
    assert len(report["variants"]) == 5
    for variant in report["variants"].values():
        assert variant["cases"][0]["question_id"] == "E1"
        assert variant["metrics"]["result_accuracy"] == 1.0
    assert report["variants"]["without_semantic"]["cases"][0]["state"]["semantic_reason"].startswith("Semantic verification disabled")


def test_schema_comparison_uses_retrieval_metadata(db_path: Path) -> None:
    questions = [{"id": "E1", "question": "How many customers?", "sql": "SELECT COUNT(*) AS customer_count FROM customers", "expected_tables": ["customers"]}]
    report = run_schema_comparison(questions, db_path=db_path)
    assert set(report["variants"]) == {"flat", "neo4j"}
    assert report["variants"]["neo4j"]["metrics"]["fallback_runs"] == 1
    for variant in report["variants"].values():
        assert variant["metrics"]["correct_tables_rate"] == 1.0
        assert variant["metrics"]["correct_tables_scored"] == 1
        assert variant["metrics"]["correct_join_path_rate"] is None
        assert variant["metrics"]["mean_schema_context_chars"] > 0
        assert variant["metrics"]["mean_retrieval_latency_ms"] >= 0
