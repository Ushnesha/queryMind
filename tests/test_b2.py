"""Mechanical result voting, call accounting, and read-only b2 execution."""

from pathlib import Path

import pytest

from src.evaluation.b2 import run_self_consistency, run_single_generation


class SequenceProvider:
    """A deterministic local sequence, not an LLM response-content assertion."""

    is_mock = True

    def __init__(self, outputs: list[str | Exception]) -> None:
        self.outputs = iter(outputs)
        self.calls = 0

    def generate(self, question: str, schema_context: str) -> str:
        self.calls += 1
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


def test_b2_selects_result_majority_across_different_sql(db_path: Path) -> None:
    provider = SequenceProvider([
        "SELECT customer_id FROM customers ORDER BY customer_id",
        "SELECT customer_id FROM customers ORDER BY customer_id DESC",
        "SELECT customer_id FROM customers WHERE customer_id = 1",
    ])
    report = run_self_consistency("IDs", db_path=db_path, provider=provider)
    assert report["implemented"] is True
    assert "preliminary" in report["label"] and "k=3" in report["label"]
    assert report["selected_index"] == 0
    assert report["majority_count"] == 2
    assert report["state"]["rows"] == [[1], [2], [3], [4]]
    assert report["state"]["metrics"]["generation_calls"] == provider.calls == 3
    assert report["state"]["metrics"]["llm_calls"] == 0


def test_b2_tie_abstains_without_selecting_first_candidate(db_path: Path) -> None:
    provider = SequenceProvider([f"SELECT {number} AS n" for number in (1, 2, 3)])
    report = run_self_consistency("Numbers", db_path=db_path, provider=provider)
    assert report["selected_index"] is None
    assert report["state"]["status"] == "refused"
    assert report["state"]["rows"] == []
    assert report["state"]["answerable"] is True
    assert "No strict result majority" in report["state"]["final_answer"]


def test_b2_failed_candidates_cannot_reduce_majority_denominator(db_path: Path) -> None:
    provider = SequenceProvider([
        "SELECT 1 AS n", "SELECT missing FROM customers", RuntimeError("provider failed"),
    ])
    report = run_self_consistency("Numbers", db_path=db_path, provider=provider)
    assert report["required_votes"] == 2
    assert report["majority_count"] == 1
    assert report["selected_index"] is None
    assert report["state"]["metrics"]["successful_candidates"] == 1
    assert provider.calls == 3


def test_b2_does_not_confuse_duplicate_multiplicity(db_path: Path) -> None:
    provider = SequenceProvider([
        "SELECT 1 AS n UNION ALL SELECT 1",
        "SELECT 1 AS n", "SELECT 2 AS n",
    ])
    report = run_self_consistency("Numbers", db_path=db_path, provider=provider)
    assert report["majority_count"] == 1
    assert report["state"]["status"] == "refused"


def test_b2_column_names_and_json_types_remain_part_of_agreement(db_path: Path) -> None:
    provider = SequenceProvider(["SELECT 1 AS n", "SELECT '1' AS n", "SELECT 1 AS other"])
    report = run_self_consistency("Numbers", db_path=db_path, provider=provider)
    assert report["majority_count"] == 1
    assert report["selected_index"] is None


def test_b2_refusal_consensus_names_fields_without_result_vote(db_path: Path) -> None:
    provider = SequenceProvider([
        "NOT_ANSWERABLE: product cost", "NOT_ANSWERABLE: product cost", "SELECT 1 AS n",
    ])
    report = run_self_consistency("Profit margin", db_path=db_path, provider=provider)
    assert report["selected_index"] is None
    assert report["refusal_consensus_count"] == 2
    assert report["state"]["answerable"] is False
    assert report["state"]["missing_fields"] == ["product cost"]
    assert report["state"]["status"] == "refused"


def test_b2_readonly_guard_rejects_every_write(db_path: Path) -> None:
    report = run_self_consistency("Write", db_path=db_path, provider=SequenceProvider([
        "DELETE FROM customers", "UPDATE customers SET name='X'", "DROP TABLE customers",
    ]))
    assert all(candidate["status"] == "error" for candidate in report["candidates"])
    count = run_single_generation("How many customers are there?", db_path=db_path)
    assert count["rows"] == [[4]]


def test_b2_uses_explicit_call_counter_and_preserves_unknown_counts(db_path: Path) -> None:
    class InstrumentedProvider:
        llm_calls = 0

        def generate(self, question: str, schema_context: str) -> str:
            self.llm_calls += 2
            return "SELECT 1 AS n"

    report = run_self_consistency("Calls", db_path=db_path, provider=InstrumentedProvider())
    assert report["state"]["metrics"]["llm_calls"] == 6
    provider = SequenceProvider(["SELECT 1 AS n"])
    provider.is_mock = False
    state = run_single_generation("Calls", db_path=db_path, provider=provider)
    assert state["metrics"]["llm_calls"] is None


def test_single_generation_reports_mock_calls_and_unsupported_abstention(db_path: Path) -> None:
    state = run_single_generation("unsupported", db_path=db_path)
    assert state["status"] == "refused"
    assert state["answerable"] is True
    assert state["missing_fields"] == []
    assert state["final_answer"].startswith("QueryMind cannot reliably answer this question.")
    assert state["metrics"]["generation_calls"] == 1
    assert state["metrics"]["llm_calls"] == 0


@pytest.mark.parametrize("samples", [0, -1, True, 1.5])
def test_b2_rejects_invalid_sample_counts(samples: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        run_self_consistency("Numbers", samples=samples)
