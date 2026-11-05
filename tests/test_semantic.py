"""Starter semantics must make limited verification coverage explicit."""

from src.verifiers import verify_semantics


def test_semantic_contract_marks_placeholder() -> None:
    result = verify_semantics("How many customers?", "SELECT COUNT(*) FROM customers", "customers(id)")
    assert set(result) >= {
        "matches_question", "answerable", "missing_fields", "assumptions", "reason"
    }
    assert result["status"] == "placeholder"
    assert result["assumptions"]
    assert result["matches_question"] is True


def test_semantic_empty_schema_cannot_be_answered() -> None:
    result = verify_semantics("How many customers?", "SELECT 1", "")
    assert result["answerable"] is False
